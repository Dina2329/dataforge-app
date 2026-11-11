"""Elasticsearch connector (architecture plan, section 3) — an index maps to
a DataForge "table" and mapping properties map to columns. Streaming uses a
Point-in-Time + search_after cursor rather than the scroll API, which would
pin cluster resources for the scroll's lifetime.

Two-way table sync (Postgres/MySQL's Stage 1/2) is extended here too --
gated the same way, via WRITABLE_SOURCE_TYPES in service.py. _id is
Elasticsearch's only real equivalent of a primary key: always present,
always unique, but never inside a mapping's `properties` (it's a top-level
document metadata field), so introspect_columns/stream_rows synthesize it
as an extra column/key rather than reading it off `_source`."""

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from elasticsearch import AsyncElasticsearch, NotFoundError as ESNotFoundError

from app.modules.connectors.base import BaseConnector, ColumnDef, ConnectorError, ConnectorRowNotFoundError, TableRef
from app.modules.connectors.registry import register_connector

PIT_KEEP_ALIVE = "2m"
ID_COLUMN = "_id"

# object/nested fields would need flattening to represent as a single scalar
# column -- out of scope for this MVP, so they're skipped rather than
# imported as an incorrect text blob.
_SKIPPED_ES_TYPES = {"object", "nested"}

_ES_TYPE_MAP = {
    "boolean": "boolean",
    "date": "date",
    "date_nanos": "date",
    "long": "number",
    "integer": "number",
    "short": "number",
    "byte": "number",
    "double": "number",
    "float": "number",
    "half_float": "number",
    "scaled_float": "number",
    "unsigned_long": "number",
}


def _map_es_type_to_field_type(es_type: str) -> str:
    return _ES_TYPE_MAP.get(es_type, "text")


@register_connector("elasticsearch")
class ElasticsearchConnector(BaseConnector):
    key = "elasticsearch"

    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._client: AsyncElasticsearch | None = None

    def _client_instance(self) -> AsyncElasticsearch:
        if self._client is None:
            kwargs: dict[str, Any] = {}
            if self.config.get("api_key"):
                kwargs["api_key"] = self.config["api_key"]
            elif self.config.get("username") and self.config.get("password"):
                kwargs["basic_auth"] = (self.config["username"], self.config["password"])
            self._client = AsyncElasticsearch(self.config["url"], **kwargs)
        return self._client

    async def test_connection(self) -> None:
        try:
            await self._client_instance().info()
        except Exception as exc:
            raise ConnectorError(f"Could not connect: {exc}") from exc

    async def list_tables(self) -> list[TableRef]:
        try:
            rows = await self._client_instance().cat.indices(format="json", h="index")
        except Exception as exc:
            raise ConnectorError(f"Could not list indices: {exc}") from exc
        return [TableRef(name=row["index"]) for row in rows if not row["index"].startswith(".")]

    async def introspect_columns(self, table: TableRef) -> list[ColumnDef]:
        try:
            mapping = await self._client_instance().indices.get_mapping(index=table.name)
        except Exception as exc:
            raise ConnectorError(f"Could not introspect index '{table.name}': {exc}") from exc

        index_mapping = mapping.get(table.name) or next(iter(mapping.body.values()), {})
        properties = index_mapping.get("mappings", {}).get("properties", {})
        # _id is never a real mapping property (it's document metadata, not a
        # field) -- synthesized here so the existing "exactly one
        # is_primary_key column" check in ImportService._resolve_sync_pk_column
        # works completely unchanged for Elasticsearch, no ES-specific bypass
        # needed. Also makes _id a normal, visible, always-imported DataForge
        # field -- reserved leading-underscore names can't appear in a real
        # ES mapping, so this can never collide with an actual property.
        columns = [ColumnDef(name=ID_COLUMN, native_type="_id", inferred_field_type="text", is_primary_key=True)]
        for name, spec in properties.items():
            es_type = spec.get("type", "object")
            if es_type in _SKIPPED_ES_TYPES:
                continue
            columns.append(ColumnDef(name=name, native_type=es_type, inferred_field_type=_map_es_type_to_field_type(es_type)))
        return columns

    async def stream_rows(self, table: TableRef, *, batch_size: int = 2000) -> AsyncIterator[list[dict[str, Any]]]:
        client = self._client_instance()
        try:
            pit = await client.open_point_in_time(index=table.name, keep_alive=PIT_KEEP_ALIVE)
        except Exception as exc:
            raise ConnectorError(f"Could not open point-in-time for '{table.name}': {exc}") from exc

        pit_id = pit["id"]
        search_after = None
        try:
            while True:
                body: dict[str, Any] = {
                    "size": batch_size,
                    "query": {"match_all": {}},
                    "pit": {"id": pit_id, "keep_alive": PIT_KEEP_ALIVE},
                    "sort": [{"_shard_doc": "asc"}],
                }
                if search_after is not None:
                    body["search_after"] = search_after
                resp = await client.search(**body)
                hits = resp["hits"]["hits"]
                if not hits:
                    break
                yield [{ID_COLUMN: hit["_id"], **hit["_source"]} for hit in hits]
                if len(hits) < batch_size:
                    break
                search_after = hits[-1]["sort"]
        except Exception as exc:
            raise ConnectorError(f"Could not stream rows from '{table.name}': {exc}") from exc
        finally:
            try:
                await client.close_point_in_time(id=pit_id)
            except Exception:
                pass

    async def stream_changed_rows(
        self, table: TableRef, *, updated_at_column: str, since: datetime, batch_size: int = 2000
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """Like stream_rows, but only documents whose updated_at_column is
        >= since. >=, not > -- a document exactly at the watermark is
        reprocessed once (harmless: the caller's upsert is idempotent by
        _external_pk) rather than risking permanent exclusion, same
        reasoning as the SQL connectors' version of this method."""
        client = self._client_instance()
        try:
            pit = await client.open_point_in_time(index=table.name, keep_alive=PIT_KEEP_ALIVE)
        except Exception as exc:
            raise ConnectorError(f"Could not open point-in-time for '{table.name}': {exc}") from exc

        pit_id = pit["id"]
        search_after = None
        try:
            while True:
                body: dict[str, Any] = {
                    "size": batch_size,
                    "query": {"range": {updated_at_column: {"gte": since.isoformat()}}},
                    "pit": {"id": pit_id, "keep_alive": PIT_KEEP_ALIVE},
                    "sort": [{updated_at_column: "asc"}, {"_shard_doc": "asc"}],
                }
                if search_after is not None:
                    body["search_after"] = search_after
                resp = await client.search(**body)
                hits = resp["hits"]["hits"]
                if not hits:
                    break
                yield [{ID_COLUMN: hit["_id"], **hit["_source"]} for hit in hits]
                if len(hits) < batch_size:
                    break
                search_after = hits[-1]["sort"]
        except Exception as exc:
            raise ConnectorError(f"Could not read changed documents from '{table.name}': {exc}") from exc
        finally:
            try:
                await client.close_point_in_time(id=pit_id)
            except Exception:
                pass

    async def fetch_primary_keys(self, table: TableRef, pk_column: str) -> set[str]:
        """Just document ids, for the deletion diff -- deliberately still
        PIT-backed (not a plain live search): PIT's only real downside here
        is a bounded, self-healing one-cycle lag (a doc deleted after
        PIT-open still appears, cleaned up next cycle); a live search_after
        against a *changing* index risks silently skipping a still-existing
        document mid-pagination if the index shifts underneath it, which
        would wrongly delete that document's still-valid local row -- a
        strictly worse failure than the lag PIT accepts."""
        client = self._client_instance()
        try:
            pit = await client.open_point_in_time(index=table.name, keep_alive=PIT_KEEP_ALIVE)
        except Exception as exc:
            raise ConnectorError(f"Could not open point-in-time for '{table.name}': {exc}") from exc

        pit_id = pit["id"]
        search_after = None
        pks: set[str] = set()
        batch_size = 5000
        try:
            while True:
                body: dict[str, Any] = {
                    "size": batch_size,
                    "query": {"match_all": {}},
                    "pit": {"id": pit_id, "keep_alive": PIT_KEEP_ALIVE},
                    "sort": [{"_shard_doc": "asc"}],
                    "_source": False,
                }
                if search_after is not None:
                    body["search_after"] = search_after
                resp = await client.search(**body)
                hits = resp["hits"]["hits"]
                if not hits:
                    break
                pks.update(hit["_id"] for hit in hits)
                if len(hits) < batch_size:
                    break
                search_after = hits[-1]["sort"]
            return pks
        except Exception as exc:
            raise ConnectorError(f"Could not fetch document ids from '{table.name}': {exc}") from exc
        finally:
            try:
                await client.close_point_in_time(id=pit_id)
            except Exception:
                pass

    async def get_server_time(self) -> datetime:
        """Elasticsearch has no server-side trigger clock the way a SQL
        server does (whatever "last modified" field a user designates is set
        by whatever ingests data into ES, not by ES itself), and no clean
        "ask the server what time it is" query. This is only ever used for
        ONE thing: TableSyncService.configure_pull's initial watermark, a
        one-time approximate cutoff at the moment pull is enabled -- fine to
        approximate with DataForge's own clock here specifically because
        there's no prior poll to derive a real value from yet. It must NOT
        be used for the recurring per-poll watermark (see poll_table_sync,
        which derives that from actually-observed row data instead, for
        every connector) -- using a wall clock there would let ingestion-lag
        (a document whose ES-visible time trails its own timestamp field)
        silently and permanently fall behind an ever-advancing watermark."""
        return datetime.now(timezone.utc)

    # -- Write path (Stage 1/2 table sync). insert/update/delete all accept
    # pk_column for call-site symmetry with the SQL connectors, but it's
    # unused here -- Elasticsearch's identifier is always _id.

    async def insert_row(self, table: TableRef, values: dict[str, Any]) -> Any:
        client = self._client_instance()
        try:
            # No `id=` -- Elasticsearch assigns its own, mirroring "the
            # external side assigns its own new key" for SQL inserts.
            response = await client.index(index=table.name, document=values)
            return response["_id"]
        except Exception as exc:
            raise ConnectorError(f"Could not index a document into '{table.name}': {exc}") from exc

    async def update_row(self, table: TableRef, pk_column: str, pk_value: Any, values: dict[str, Any]) -> None:
        client = self._client_instance()
        try:
            # doc_as_upsert is deliberately never set: left at its default,
            # a missing id raises NotFoundError below, matching SQL's "0
            # rows affected" contract. Setting it would silently resurrect
            # a deleted document under its old id instead.
            await client.update(index=table.name, id=pk_value, doc=values)
        except ESNotFoundError as exc:
            raise ConnectorRowNotFoundError(f"Document _id={pk_value!r} no longer exists in '{table.name}'") from exc
        except Exception as exc:
            # Includes ESConflictError (a real possibility under concurrent
            # writes via update()'s optimistic concurrency) -- retryable,
            # same as any other transient connector failure, never
            # miscategorized as "not found".
            raise ConnectorError(f"Could not update document _id={pk_value!r} in '{table.name}': {exc}") from exc

    async def delete_row(self, table: TableRef, pk_column: str, pk_value: Any) -> None:
        client = self._client_instance()
        try:
            await client.delete(index=table.name, id=pk_value)
        except ESNotFoundError:
            return  # already gone is success, not an error -- matches SQL's delete_row
        except Exception as exc:
            raise ConnectorError(f"Could not delete document _id={pk_value!r} from '{table.name}': {exc}") from exc

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
