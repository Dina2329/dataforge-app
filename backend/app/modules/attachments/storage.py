"""Local-disk object storage for attachment fields.

A self-hosted deployment without an S3/MinIO endpoint configured still needs
somewhere to put uploaded files — this stores them under a directory on the
backend's own disk (see docker-compose.yml: the backend container already
bind-mounts the whole ./backend directory, so files land on the host for
free without a separate named volume). Swappable behind this same interface
for a future S3Storage/MinioStorage implementation, same pattern as
SecretsService for connector credentials.
"""

import uuid
from pathlib import Path

from app.config import settings


class LocalFilesystemStorage:
    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or settings.attachments_dir)

    def save(self, *, data: bytes, filename: str) -> str:
        # A random directory per upload avoids collisions between two
        # attachments that happen to share a filename.
        key = f"{uuid.uuid4().hex}/{filename}"
        path = self.base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        return (self.base_dir / key).read_bytes()

    def delete(self, key: str) -> None:
        (self.base_dir / key).unlink(missing_ok=True)


_storage: LocalFilesystemStorage | None = None


def get_storage() -> LocalFilesystemStorage:
    global _storage
    if _storage is None:
        _storage = LocalFilesystemStorage()
    return _storage
