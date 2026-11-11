from fastapi import APIRouter, Depends

from app.core.deps import CurrentUser, DbSession
from app.core.rate_limit import rate_limit
from app.modules.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Both keyed by IP, not account -- an attacker doesn't need a valid email to
# exhaust a per-account limit, so IP is the only key that actually protects
# against credential-stuffing/registration-spam here.
_login_rate_limit = rate_limit(key_prefix="login", max_requests=10, window_seconds=300)
_register_rate_limit = rate_limit(key_prefix="register", max_requests=5, window_seconds=3600)


@router.post("/register", response_model=TokenResponse, status_code=201, dependencies=[Depends(_register_rate_limit)])
async def register(payload: RegisterRequest, db: DbSession) -> TokenResponse:
    service = AuthService(db)
    user = await service.register(email=payload.email, name=payload.name, password=payload.password)
    return service.issue_tokens(user)


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(_login_rate_limit)])
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    service = AuthService(db)
    user = await service.authenticate(email=payload.email, password=payload.password)
    return service.issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenResponse:
    return await AuthService(db).refresh(payload.refresh_token)


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
