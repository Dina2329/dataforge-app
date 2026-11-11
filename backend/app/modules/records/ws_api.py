import json
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.db import SessionLocal
from app.core.errors import DataForgeError
from app.core.ws_manager import PresenceUser, manager
from app.modules.auth.service import AuthService
from app.modules.bases.service import BasesService

router = APIRouter(tags=["records-ws"])


@router.websocket("/ws/tables/{table_id}")
async def table_updates_ws(websocket: WebSocket, table_id: uuid.UUID, token: str = Query(...)) -> None:
    # A browser WebSocket can't set an Authorization header, so the access
    # token travels as a query param here instead -- same bearer token the
    # REST API uses, just carried differently for this one handshake.
    async with SessionLocal() as db:
        try:
            user = await AuthService(db).get_current_user(token)
            await BasesService(db).check_table_access(table_id=table_id, user_id=user.id)
        except DataForgeError:
            await websocket.close(code=4401)
            return

    await websocket.accept()
    manager.connect(table_id, websocket)
    await manager.join_presence(
        table_id, websocket, PresenceUser(user_id=str(user.id), name=user.name, email=user.email)
    )
    try:
        while True:
            # Mostly server->client, but the client also sends its own active
            # cell so peers can see "X is editing this" -- everything else
            # incoming is ignored rather than erroring, so a client on a
            # slightly newer/older message schema never kills the connection.
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except ValueError:
                continue
            if msg.get("type") == "cell_focus" and isinstance(msg.get("row_id"), int) and isinstance(msg.get("field_name"), str):
                await manager.set_focus(table_id, websocket, row_id=msg["row_id"], field_name=msg["field_name"])
    except WebSocketDisconnect:
        pass
    finally:
        left_user = manager.disconnect(table_id, websocket)
        if left_user is not None:
            await manager.broadcast(table_id, {"type": "presence_leave", "user_id": left_user.user_id})
