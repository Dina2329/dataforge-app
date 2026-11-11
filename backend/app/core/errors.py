class DataForgeError(Exception):
    """Base class for all domain errors; caught centrally in app.main to produce JSON responses."""

    status_code = 400

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(DataForgeError):
    status_code = 404


class ConflictError(DataForgeError):
    """Raised on optimistic-concurrency version mismatches and duplicate-resource conflicts."""

    status_code = 409


class ForbiddenError(DataForgeError):
    status_code = 403


class UnauthorizedError(DataForgeError):
    """Distinct from ForbiddenError: this means "the caller isn't
    authenticated as anyone valid" (missing/expired/malformed access token)
    rather than "authenticated but not allowed to do this." The distinction
    is load-bearing, not cosmetic -- the frontend's axios interceptor only
    attempts a silent refresh-and-retry on 401; collapsing this into 403 (as
    it used to be) meant an expired access token surfaced as a permanent
    "Forbidden" on every request until the user manually logged out and back
    in, instead of a silent token refresh."""

    status_code = 401


class ValidationError(DataForgeError):
    status_code = 422


class ExternalServiceError(DataForgeError):
    """A call to a service outside DataForge's own control (e.g. the
    record_submit "Submit row" POST to an external API) failed after
    retries. Distinct from every other error here -- this one is never about
    the caller's request being wrong, so the frontend should offer a retry
    rather than treat it like a validation/permission mistake."""

    status_code = 502
