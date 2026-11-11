from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.modules.auth.models import User
from app.modules.auth.service import AuthService

_bearer_scheme = HTTPBearer()

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    db: DbSession,
) -> User:
    return await AuthService(db).get_current_user(credentials.credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]
