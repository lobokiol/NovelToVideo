"""Repository-level Python startup customizations.

Psycopg async connections are not compatible with Windows' default
ProactorEventLoop, so set the selector policy before uvicorn creates the loop.
"""

from __future__ import annotations

import asyncio
import sys


if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
