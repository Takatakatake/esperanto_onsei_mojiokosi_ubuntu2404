from __future__ import annotations

import asyncio
import json
import logging
import errno
from pathlib import Path
from typing import Dict, List, Optional, Set

from aiohttp import web, WSMsgType


class CaptionWebUI:
    """Lightweight Web UI for live captions via WebSocket.

    Serves a static page and accepts WS connections on /ws. Use broadcast()
    to push updates: {"type": "partial"|"final", "text": "..."}.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        web_root: Optional[Path] = None,
        max_port_attempts: int = 5,
        translation_targets: Optional[List[str]] = None,
        translation_default_visibility: Optional[Dict[str, bool]] = None,
    ) -> None:
        self.host = host
        self.port = port
        self._base_port = port
        self._max_port_attempts = max(1, max_port_attempts)
        self.web_root = web_root or (Path(__file__).resolve().parent.parent.parent / "web")
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._clients: Set[web.WebSocketResponse] = set()
        self._task: Optional[asyncio.Task] = None
        self._config_payload = {
            "targets": list(translation_targets or []),
            "defaultVisibility": translation_default_visibility or {},
        }

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/ws", self._handle_ws)
        app.router.add_get("/config", self._handle_config)
        app.router.add_static("/static", str(self.web_root / "static"))
        self._app = app
        self._runner = web.AppRunner(app)
        await self._runner.setup()

        attempts = 0
        last_error: Optional[Exception] = None
        while attempts < self._max_port_attempts:
            desired_port = self._base_port + attempts
            try:
                self._site = web.TCPSite(self._runner, self.host, desired_port)
                await self._site.start()
            except OSError as exc:
                last_error = exc
                self._site = None
                if exc.errno == errno.EADDRINUSE:
                    logging.warning(
                        "Caption Web UI port %s already in use; trying next port.", desired_port
                    )
                    attempts += 1
                    continue
                await self._runner.cleanup()
                self._runner = None
                raise
            else:
                self.port = desired_port
                logging.info("Caption Web UI running at http://%s:%d", self.host, self.port)
                return

        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        raise OSError("Caption Web UI could not bind to any available port.") from last_error

    async def stop(self) -> None:
        for ws in list(self._clients):
            await ws.close()
        self._clients.clear()
        if self._site:
            await self._site.stop()
            self._site = None
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._app = None

    async def _handle_index(self, request: web.Request) -> web.Response:
        index_path = self.web_root / "index.html"
        return web.FileResponse(path=str(index_path))

    async def _handle_config(self, request: web.Request) -> web.Response:
        return web.json_response(self._config_payload)

    async def _handle_ws(self, request: web.Request) -> web.StreamResponse:
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        self._clients.add(ws)
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    # Currently we don't expect inbound messages; ignore pings
                    pass
                elif msg.type == WSMsgType.ERROR:
                    logging.warning("WebSocket error: %s", ws.exception())
        finally:
            self._clients.discard(ws)
        return ws

    async def broadcast(self, payload: dict) -> None:
        if not self._clients:
            return
        data = json.dumps(payload)
        coros = [ws.send_str(data) for ws in list(self._clients) if not ws.closed]
        if coros:
            await asyncio.gather(*coros, return_exceptions=True)
