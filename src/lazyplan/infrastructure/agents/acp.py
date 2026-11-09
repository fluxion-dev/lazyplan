"""Minimal Agent Client Protocol v1 client over stdio.

The transport is deliberately stdlib-only: one subprocess, newline-delimited
JSON-RPC, typed events, and no Textual imports. The workbench and tests build
on this seam.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from .events import AgentEvent, map_server_request, map_session_update

PROTOCOL_VERSION = 1
DEFAULT_TIMEOUT = 30.0
STDERR_LINES = 200


class AcpError(RuntimeError):
    """One protocol or process failure with the JSON-RPC code when known."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class AcpClient:
    """One ACP agent process with streaming events and permission replies."""

    def __init__(
        self,
        command: Sequence[str],
        cwd: str | Path,
        *,
        env: Mapping[str, str] | None = None,
        client_name: str = "lazyplan",
        client_version: str = "0.35.0",
    ) -> None:
        self.command = tuple(str(part) for part in command)
        self.cwd = Path(cwd).expanduser().resolve()
        self.env = dict(env) if env is not None else None
        self.client_name = client_name
        self.client_version = client_version
        self.agent_capabilities: dict[str, Any] = {}
        self.agent_info: dict[str, Any] = {}
        self.auth_methods: tuple[dict[str, Any], ...] = ()
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._events: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 1
        self._write_lock = asyncio.Lock()
        self._stderr: deque[str] = deque(maxlen=STDERR_LINES)
        self._finished = False
        self._closed = False

    @property
    def pid(self) -> int | None:
        return None if self._proc is None else self._proc.pid

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None and not self._closed

    async def __aenter__(self) -> AcpClient:
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def start(self) -> None:
        """Spawn the agent process and start the stdout/stderr readers."""
        if self._proc is not None:
            return
        self._proc = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=str(self.cwd),
            env=self.env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())

    async def initialize(
        self,
        client_capabilities: dict[str, Any] | None = None,
        client_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Negotiate ACP v1 and keep the agent capabilities."""
        info = client_info or {
            "name": self.client_name,
            "title": "lazyplan",
            "version": self.client_version,
        }
        result = await self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "clientCapabilities": client_capabilities or {},
                "clientInfo": info,
            },
        )
        version = result.get("protocolVersion")
        if version != PROTOCOL_VERSION:
            raise AcpError(
                -32000,
                f"agent speaks ACP {version!r}; lazyplan requires {PROTOCOL_VERSION}",
            )
        self.agent_capabilities = _dict(result.get("agentCapabilities"))
        self.agent_info = _dict(result.get("agentInfo"))
        methods = result.get("authMethods")
        self.auth_methods = (
            tuple(item for item in methods if isinstance(item, dict))
            if isinstance(methods, list)
            else ()
        )
        return result

    async def new_session(
        self,
        *,
        cwd: str | Path | None = None,
        mcp_servers: Sequence[dict[str, Any]] = (),
        additional_directories: Sequence[str] = (),
        system_prompt: dict[str, Any] | None = None,
    ) -> str:
        """Create one ACP session and return its id."""
        params: dict[str, Any] = {
            "cwd": str(Path(cwd).expanduser().resolve()) if cwd is not None else str(self.cwd),
            "mcpServers": [dict(server) for server in mcp_servers],
        }
        if additional_directories:
            params["additionalDirectories"] = [
                str(Path(path).resolve()) for path in additional_directories
            ]
        if system_prompt is not None:
            params["systemPrompt"] = system_prompt
        result = await self.request("session/new", params, timeout=60.0)
        session_id = result.get("sessionId")
        if not isinstance(session_id, str) or not session_id:
            raise AcpError(-32000, "session/new returned no sessionId", result)
        return session_id

    async def load_session(
        self,
        session_id: str,
        *,
        cwd: str | Path | None = None,
        mcp_servers: Sequence[dict[str, Any]] = (),
        additional_directories: Sequence[str] = (),
        system_prompt: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Load a saved session; the agent replays it as session updates."""
        if not self.agent_capabilities.get("loadSession"):
            raise AcpError(-32000, "agent does not support session/load")
        params: dict[str, Any] = {
            "sessionId": session_id,
            "cwd": str(Path(cwd).expanduser().resolve()) if cwd is not None else str(self.cwd),
            "mcpServers": [dict(server) for server in mcp_servers],
        }
        if additional_directories:
            params["additionalDirectories"] = [
                str(Path(path).resolve()) for path in additional_directories
            ]
        if system_prompt is not None:
            params["systemPrompt"] = system_prompt
        return await self.request("session/load", params, timeout=60.0)

    async def close_session(self, session_id: str) -> None:
        """Close one ACP session when the agent supports it."""
        if not _capability(self.agent_capabilities, "sessionCapabilities", "close"):
            return
        try:
            await self.request("session/close", {"sessionId": session_id}, timeout=10.0)
        except AcpError as exc:
            if exc.code != -32002:
                raise

    async def prompt(
        self,
        session_id: str,
        text: str,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Send one text prompt and wait for its stop reason."""
        return await self.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": text}],
            },
            timeout=timeout,
        )

    async def cancel(self, session_id: str) -> None:
        """Cancel the active prompt for one session."""
        await self.notify("session/cancel", {"sessionId": session_id})

    async def reply_permission(self, request_id: int | str, option_id: str | None) -> None:
        """Answer a pending permission request; None cancels the turn."""
        outcome: dict[str, Any]
        if option_id is None:
            outcome = {"outcome": "cancelled"}
        else:
            outcome = {"outcome": "selected", "optionId": option_id}
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"outcome": outcome},
            }
        )

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        """Send one JSON-RPC request and await its result."""
        if self._proc is None:
            raise AcpError(-32000, "agent process has not started")
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params or {},
                }
            )
            if timeout is None:
                return await future
            return await asyncio.wait_for(future, timeout)
        except TimeoutError as exc:
            raise AcpError(-32000, f"{method} timed out after {timeout:.0f}s") from exc
        finally:
            self._pending.pop(request_id, None)

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send one JSON-RPC notification."""
        await self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    async def events(self) -> AsyncIterator[AgentEvent]:
        """Yield normalized events until the process exits or closes."""
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

    def last_stderr(self, lines: int = 20) -> str:
        """Return the tail of the agent's stderr for an error notice."""
        return "\n".join(list(self._stderr)[-lines:])

    async def close(self) -> None:
        """Close stdin, stop the process, and release the readers."""
        if self._closed:
            return
        self._closed = True
        proc = self._proc
        if proc is not None:
            if proc.stdin is not None and not proc.stdin.is_closing():
                proc.stdin.close()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
            await self._finish(proc.returncode)
        else:
            await self._finish(None)
        await self._stop_tasks()

    async def _send(self, payload: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.returncode is not None or self._closed:
            raise AcpError(-32000, "agent process is not running")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        try:
            async with self._write_lock:
                proc.stdin.write(data)
                await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise AcpError(-32000, "agent process closed its stdin") from exc

    async def _read_stdout(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stdout is not None
        while True:
            try:
                raw = await proc.stdout.readline()
            except (ConnectionResetError, asyncio.CancelledError):
                break
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self._stderr.append(f"invalid protocol line: {line[:200]}")
                continue
            if isinstance(message, dict):
                await self._handle(message)
        await self._finish(proc.returncode)

    async def _read_stderr(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stderr is not None
        while True:
            try:
                raw = await proc.stderr.readline()
            except (ConnectionResetError, asyncio.CancelledError):
                break
            if not raw:
                break
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                self._stderr.append(line)

    async def _handle(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        params = _dict(message.get("params"))
        if isinstance(method, str) and "id" in message:
            await self._handle_request(message["id"], method, params)
            return
        if isinstance(method, str):
            self._handle_notification(method, params)
            return
        if "id" in message:
            self._resolve(message)

    def _handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "session/update":
            update = _dict(params.get("update"))
            session_id = str(params.get("sessionId") or "")
            self._events.put_nowait(map_session_update(session_id, update))
            return
        self._events.put_nowait(
            AgentEvent(kind="unknown", payload={"method": method, "params": params})
        )

    async def _handle_request(
        self, request_id: int | str, method: str, params: dict[str, Any]
    ) -> None:
        if method == "session/request_permission":
            self._events.put_nowait(map_server_request(request_id, method, params))
            return
        await self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"lazyplan does not implement {method}",
                },
            }
        )

    def _resolve(self, message: dict[str, Any]) -> None:
        raw_id = message.get("id")
        if not isinstance(raw_id, int):
            return
        future = self._pending.get(raw_id)
        if future is None or future.done():
            return
        error = message.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            future.set_exception(
                AcpError(
                    code if isinstance(code, int) else -32000,
                    str(error.get("message") or "agent request failed"),
                    error.get("data"),
                )
            )
            return
        future.set_result(_dict(message.get("result")))

    async def _finish(self, returncode: int | None) -> None:
        if self._finished:
            return
        self._finished = True
        failure = AcpError(returncode or -32000, "agent process exited")
        for future in self._pending.values():
            if not future.done():
                future.set_exception(failure)
        self._pending.clear()
        self._events.put_nowait(AgentEvent(kind="exit", payload={"returncode": returncode}))
        self._events.put_nowait(None)

    async def _stop_tasks(self) -> None:
        for task in (self._reader_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
        for task in (self._reader_task, self._stderr_task):
            if task is not None:
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _capability(capabilities: dict[str, Any], *path: str) -> bool:
    value: Any = capabilities
    for part in path:
        if not isinstance(value, dict):
            return False
        value = value.get(part)
    return bool(value)
