"""One-off: re-encrypts every DataSource's stored config from an old
ENCRYPTION_KEY to a new one.

Run this BEFORE updating .env to the new key -- it uses both keys
explicitly, passed on the command line, not whatever's currently
configured in settings, so the running app's own state doesn't matter
while this runs and there's no window where .env and the actual stored
ciphertext disagree.

Usage:
    python3 scripts/rotate_encryption_key.py <old_key> <new_key>

After this succeeds: set ENCRYPTION_KEY=<new_key> in .env, then restart the
backend and arq worker (both read settings once at process startup).
"""

import asyncio
import sys

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

import app.all_models  # noqa: F401  (registers every ORM model -- needed to resolve FKs on flush)
from app.core.db import SessionLocal
from app.modules.connectors.models import DataSource


async def main(old_key: str, new_key: str) -> None:
    old_fernet = Fernet(old_key.encode())
    new_fernet = Fernet(new_key.encode())

    async with SessionLocal() as db:
        sources = list((await db.execute(select(DataSource))).scalars().all())
        print(f"Found {len(sources)} data source(s).")
        for source in sources:
            try:
                plaintext = old_fernet.decrypt(source.config_encrypted.encode())
            except InvalidToken:
                # Fails loudly rather than silently writing garbage -- a
                # source already on some other key (or already migrated)
                # must be investigated, not steamrolled.
                print(f"  SKIPPED (does not decrypt with the given old key): {source.name} ({source.id})")
                continue
            source.config_encrypted = new_fernet.encrypt(plaintext).decode()
            print(f"  re-encrypted: {source.name} ({source.source_type})")
        await db.commit()

    print("\nDone. Now set ENCRYPTION_KEY to the new key in .env and restart the backend + arq worker.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 scripts/rotate_encryption_key.py <old_key> <new_key>", file=sys.stderr)
        sys.exit(1)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
