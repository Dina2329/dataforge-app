"""In-process WebSocket fan-out for live grid updates (architecture plan,
section 5: "Real-time UI updates"). Payloads are thin ({row_id}) -- the
client re-fetches via TanStack Query invalidation rather than trusting a
replicated diff, so a missed or out-of-order message is harmless.

Deliberately NOT the Redis Stream used for automation dispatch: automations
need durable, replay-safe delivery (a dropped trigger is a real bug), while
this is just a "hey, refetch" nudge for whoever happens to have the table
open -- at-most-once, in-process is the right tool, and it's what keeps this
a single-file, zero-new-infra addition. Revisit if the API is ever run with
more than one replica (each would need its own connections, and a client
could miss updates published while connected to a different replica).

Presence (who's viewing this table right now, who's focused on which cell)
piggybacks on the same connection and the same at-most-once, in-process
tradeoff -- a missed join/leave/focus event self-heals on the next one, and
nothing here is ever the source of truth for anything durable.
"""

import asyncio
import json
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass

from fastapi import WebSocket


@dataclass(frozen=True)
class PresenceUser:
    user_id: str
    name: str
    email: str


class TableConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)
        self._presence: dict[uuid.UUID, dict[WebSocket, PresenceUser]] = defaultdict(dict)
        # This socket's user's last-known focused cell, if any -- cleared
        # implicitly on disconnect along with everything else about it.
        self._focus: dict[uuid.UUID, dict[WebSocket, dict]] = defaultdict(dict)

    def connect(self, table_id: uuid.UUID, websocket: WebSocket) -> None:
        self._connections[table_id].add(websocket)

    def disconnect(self, table_id: uuid.UUID, websocket: WebSocket) -> PresenceUser | None:
        """Synchronous cleanup (mirrors connect()) -- returns the user that
        was present on this socket, if any, so the caller can broadcast a
        presence_leave for them (broadcasting is async, this isn't)."""
        self._connections[table_id].discard(websocket)
        user = self._presence[table_id].pop(websocket, None)
        self._focus[table_id].pop(websocket, None)
        if not self._connections[table_id]:
            del self._connections[table_id]
        if not self._presence[table_id]:
            del self._presence[table_id]
        return user

    async def broadcast(self, table_id: uuid.UUID, message: dict, *, exclude: WebSocket | None = None) -> None:
        payload = json.dumps(message)
        sockets = [ws for ws in self._connections.get(table_id, ()) if ws is not exclude]
        if not sockets:
            return
        # Sending one at a time in a loop makes every write's HTTP response
        # wait on N sequential awaits -- with 20 people in one base that's 19
        # serialized sends per edit, directly on the request path (confirmed
        # via load testing: p50 latency went from ~30ms at 1 user to ~220ms
        # at 20). Concurrent sends turn that into one round-trip's worth of
        # wall-clock time regardless of how many sockets are listening.
        results = await asyncio.gather(*(ws.send_text(payload) for ws in sockets), return_exceptions=True)
        for websocket, result in zip(sockets, results):
            if isinstance(result, Exception):
                self.disconnect(table_id, websocket)

    async def join_presence(self, table_id: uuid.UUID, websocket: WebSocket, user: PresenceUser) -> None:
        """Sends the joining connection the current roster, registers it,
        then tells everyone else it arrived -- in that order, so the joiner
        never receives their own join announcement."""
        roster = list(self._presence[table_id].values())
        await websocket.send_text(json.dumps({"type": "presence_sync", "users": [asdict(u) for u in roster]}))
        self._presence[table_id][websocket] = user
        await self.broadcast(table_id, {"type": "presence_join", "user": asdict(user)}, exclude=websocket)

    async def set_focus(self, table_id: uuid.UUID, websocket: WebSocket, *, row_id: int, field_name: str) -> None:
        user = self._presence[table_id].get(websocket)
        if user is None:
            return
        self._focus[table_id][websocket] = {"row_id": row_id, "field_name": field_name}
        await self.broadcast(
            table_id,
            {"type": "cell_focus", "user_id": user.user_id, "row_id": row_id, "field_name": field_name},
            exclude=websocket,
        )


manager = TableConnectionManager()
