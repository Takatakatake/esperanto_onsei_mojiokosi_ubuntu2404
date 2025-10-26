"""Zoom closed-caption publishing utilities."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import aiohttp

from .config import ZoomCaptionConfig


class ZoomCaptionPublisher:
    """Push transcript updates to Zoom using the Closed Caption API."""

    def __init__(self, config: ZoomCaptionConfig) -> None:
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._sequence = 0
        self._last_post_monotonic = 0.0
        self._pending_payload: Optional[str] = None
        self._post_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "ZoomCaptionPublisher":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        await self.close()

    async def start(self) -> None:
        if not self.config.enabled:
            logging.info("Zoom caption publishing disabled by configuration.")
            return
        if not self.config.caption_post_url:
            logging.warning("Zoom caption URL not configured; captions will not be sent.")
            return
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
        if self._post_task:
            self._post_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._post_task
            self._post_task = None

    async def post_caption(self, text: str) -> None:
        """Post a caption update, respecting rate limits and sequence numbers."""

        if not self.config.enabled or not self.config.caption_post_url:
            return

        if not text.strip():
            logging.debug("Skipping empty caption payload.")
            return

        async with self._lock:
            self._pending_payload = text.strip()
            if not await self._ensure_session():
                return
            await self._schedule_flush_locked()

    def _build_url_with_sequence(self, sequence: int) -> str:
        base_url = str(self.config.caption_post_url)
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query, keep_blank_values=True)
        query["seq"] = [str(sequence)]
        new_query = urlencode(query, doseq=True)
        updated = parsed._replace(query=new_query)
        return urlunparse(updated)

    async def _ensure_session(self) -> bool:
        if self._session is None:
            await self.start()
        if self._session is None:
            logging.error("Zoom caption session could not be initialised.")
            return False
        return True

    async def _schedule_flush_locked(self) -> None:
        if self._post_task and not self._post_task.done():
            return
        now = asyncio.get_running_loop().time()
        elapsed = now - self._last_post_monotonic
        delay = max(self.config.min_post_interval_seconds - elapsed, 0.0)
        self._post_task = asyncio.create_task(self._flush_pending(delay))

    async def _flush_pending(self, delay: float) -> None:
        try:
            if delay > 0:
                await asyncio.sleep(delay)
            async with self._lock:
                payload = self._pending_payload
                self._pending_payload = None
                self._post_task = None
            if not payload:
                return
            if not await self._ensure_session():
                async with self._lock:
                    self._pending_payload = payload
                    await self._schedule_flush_locked()
                return
            url = self._build_url_with_sequence(self._sequence)
            self._sequence += 1
            try:
                async with self._session.post(
                    url,
                    data=payload.encode("utf-8"),
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                ) as response:
                    if response.status != 200:
                        body = await response.text()
                        logging.error(
                            "Zoom caption POST failed: status=%s body=%s", response.status, body
                        )
                        async with self._lock:
                            # Re-queue for a later attempt
                            self._pending_payload = payload
                            await self._schedule_flush_locked()
                        return
                    logging.debug("Caption posted to Zoom (seq=%s).", self._sequence - 1)
                    self._last_post_monotonic = asyncio.get_running_loop().time()
            except Exception as exc:  # pylint: disable=broad-except
                logging.exception("Failed to post caption to Zoom: %s", exc)
                async with self._lock:
                    self._pending_payload = payload
                    await self._schedule_flush_locked()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            logging.exception("Unexpected error in Zoom caption flush: %s", exc)
