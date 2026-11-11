import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.modules.auth.models import User
from app.modules.auth.repository import UserRepository
from app.modules.auth.schemas import TokenResponse


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.users = UserRepository(db)

    async def register(self, *, email: str, name: str, password: str) -> User:
        if await self.users.get_by_email(email) is not None:
            raise ConflictError("An account with this email already exists")
        user = await self.users.create(email=email, name=name, password_hash=hash_password(password))
        await self.db.commit()
        return user

    async def authenticate(self, *, email: str, password: str) -> User:
        user = await self.users.get_by_email(email)
        if user is None or not verify_password(password, user.password_hash):
            raise ForbiddenError("Invalid email or password")
        if not user.is_active:
            raise ForbiddenError("This account has been deactivated")
        return user

    def issue_tokens(self, user: User) -> TokenResponse:
        return TokenResponse(
            access_token=create_access_token(user.id),
            refresh_token=create_refresh_token(user.id),
        )

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            user_id = decode_token(refresh_token, expected_type="refresh")
        except InvalidTokenError as exc:
            raise ForbiddenError(str(exc)) from exc
        user = await self.users.get_by_id(user_id)
        if user is None or not user.is_active:
            raise ForbiddenError("Invalid refresh token")
        return self.issue_tokens(user)

    async def get_current_user(self, access_token: str) -> User:
        try:
            user_id = decode_token(access_token, expected_type="access")
        except InvalidTokenError as exc:
            # 401, not 403 -- this is what tells apiClient's interceptor to
            # silently refresh and retry instead of surfacing a dead-end
            # "Forbidden" (see UnauthorizedError's docstring).
            raise UnauthorizedError(str(exc)) from exc
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user
