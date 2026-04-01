#!/usr/bin/env python3
"""Ensure the WELCOME invite code exists and is valid for beta testing.

Usage:
    # From project root:
    PYTHONPATH=src python scripts/ensure_welcome_code.py

    # Or via cli.py (if added as a subcommand):
    ./cli.py ensure-welcome

Creates or updates the WELCOME invite code with:
  - active = True
  - max_uses = 9999 (effectively unlimited for beta)
  - expires_at = None (no expiry)
  - doctor_id = None (each use creates a new doctor)
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

CODE = "WELCOME"
MAX_USES = 9999


async def main():
    # Load config so DATABASE_URL is set
    from utils.app_config import load_config_from_json
    _, vals = load_config_from_json()
    for k, v in vals.items():
        if k not in os.environ:
            os.environ[k] = v

    from datetime import datetime, timezone
    from sqlalchemy import select
    from db.engine import AsyncSessionLocal
    from db.models import InviteCode

    async with AsyncSessionLocal() as db:
        invite = (
            await db.execute(
                select(InviteCode).where(InviteCode.code == CODE).limit(1)
            )
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if invite is None:
            # Create new
            db.add(InviteCode(
                code=CODE,
                doctor_name=None,
                doctor_id=None,
                active=True,
                created_at=now,
                expires_at=None,
                max_uses=MAX_USES,
                used_count=0,
            ))
            await db.commit()
            print(f"Created invite code '{CODE}' (max_uses={MAX_USES}, no expiry)")
        else:
            # Update existing to ensure it's valid
            changed = []
            if not invite.active:
                invite.active = True
                changed.append("active=True")
            if invite.max_uses and invite.max_uses < MAX_USES:
                invite.max_uses = MAX_USES
                changed.append(f"max_uses={MAX_USES}")
            if invite.expires_at is not None:
                invite.expires_at = None
                changed.append("expires_at=None")
            # Don't reset doctor_id — allow multi-use (each login creates new doctor)
            if invite.doctor_id is not None:
                invite.doctor_id = None
                changed.append("doctor_id=None (multi-use)")

            if changed:
                await db.commit()
                print(f"Updated invite code '{CODE}': {', '.join(changed)}")
            else:
                print(f"Invite code '{CODE}' already valid (active, {invite.used_count}/{invite.max_uses} uses, no expiry)")


if __name__ == "__main__":
    asyncio.run(main())
