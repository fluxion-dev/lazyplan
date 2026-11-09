#!/usr/bin/env python3
"""Manual smoke for the real `opencode acp` server.

This is intentionally not part of CI: it needs a logged-in OpenCode install and
one model turn. It proves initialize, session/new, prompt streaming, and cancel
against the real binary.

Usage:
  python tools/opencode-acp-smoke.py [--cwd PATH] [--timeout 120]
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from lazyplan.infrastructure.agents import AcpClient, AcpError  # noqa: E402

MESSAGE = "Reply with the single word READY. Do not run tools or edit files."


async def run(command: list[str], cwd: Path, timeout: float, message: str) -> int:
    client = AcpClient(command, cwd)
    async with client:
        await client.initialize()
        session_id = await client.new_session()
        print(f"session: {session_id}")
        prompting = asyncio.create_task(client.prompt(session_id, message))
        seen = ""
        try:
            async with asyncio.timeout(timeout):
                async for event in client.events():
                    if event.kind == "text" and event.text.strip():
                        seen = event.text.strip().replace("\n", " ")[:120]
                        print(f"text: {seen}")
                        await client.cancel(session_id)
                        break
                    if event.kind == "permission" and event.permission is not None:
                        print("permission: rejected to keep the smoke read-only")
                        await client.reply_permission(event.permission.request_id, None)
                    if event.kind == "exit":
                        raise AcpError(-32000, "agent exited before streaming a reply")
        except TimeoutError:
            await client.cancel(session_id)
            print(f"error: no update within {timeout:.0f}s", file=sys.stderr)
            return 1
        result = await asyncio.wait_for(prompting, timeout)
    print(f"stop: {result.get('stopReason')}")
    if not seen:
        print("error: prompt produced no text update", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cwd", default=str(ROOT), metavar="PATH", help="session working directory"
    )
    parser.add_argument("--timeout", type=float, default=120.0, metavar="SECONDS")
    parser.add_argument("--message", default=MESSAGE, help="prompt text")
    parser.add_argument(
        "--command",
        default="opencode",
        help="agent executable (default: opencode)",
    )
    parser.add_argument(
        "--arg",
        action="append",
        default=[],
        dest="args",
        metavar="ARG",
        help="one argument after the command; repeat for each argument",
    )
    args = parser.parse_args()
    command = [args.command, *(args.args or ["acp"])]
    if shutil.which(command[0]) is None:
        print(f"skip: {command[0]} is not on PATH", file=sys.stderr)
        return 0
    try:
        return asyncio.run(run(command, Path(args.cwd).expanduser(), args.timeout, args.message))
    except AcpError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
