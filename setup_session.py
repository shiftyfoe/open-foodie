#!/usr/bin/env python3
"""
One-time helper: generate a TG_SESSION string for CI/CD.

Usage:
  pip install telethon cryptg
  TG_API_ID=... TG_API_HASH=... python setup_session.py

Copy the printed session string into GitHub Actions secret TG_SESSION.
"""

import asyncio
import os
import sys

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
except ImportError:
    sys.exit("Run: pip install telethon cryptg")

api_id_raw = os.environ.get("TG_API_ID", "")
api_hash = os.environ.get("TG_API_HASH", "")

if not api_id_raw or not api_hash:
    sys.exit("Set TG_API_ID and TG_API_HASH environment variables first.")


async def main() -> None:
    async with TelegramClient(StringSession(), int(api_id_raw), api_hash) as client:
        session_str = client.session.save()
        print("\n--- Copy this into GitHub secret TG_SESSION ---")
        print(session_str)
        print("-----------------------------------------------\n")


if __name__ == "__main__":
    asyncio.run(main())
