"""Speechmatics realtime WebSocket backend."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import AsyncGenerator, Dict, Optional
from urllib.parse import urlparse, urlunparse

import aiohttp

import websockets
from websockets import WebSocketClientProtocol

from ..config import SpeechmaticsConfig
from .base import StreamingTranscriptionBackend, TranscriptSegment


class SpeechmaticsRealtimeError(Exception):
    """Raised when communication with Speechmatics fails."""


class SpeechmaticsRealtimeBackend(StreamingTranscriptionBackend):
    """Manage realtime transcription sessions with Speechmatics."""

    def __init__(self, config: SpeechmaticsConfig) -> None:
        self.config = config
        self._websocket: Optional[WebSocketClientProtocol] = None
        self._listen_task: Optional[asyncio.Task[None]] = None
        self._transcript_queue: "asyncio.Queue[TranscriptSegment]" = asyncio.Queue()
        self._connected = asyncio.Event()
        self._recognition_started = asyncio.Event()

    async def __aenter__(self) -> "SpeechmaticsRealtimeBackend":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        await self.close()

    async def connect(self) -> None:
        """Establish the websocket connection and send the start message."""

        self._connected.clear()
        self._recognition_started.clear()
        max_attempts = max(0, self.config.max_reconnect_attempts)
        backoff = max(self.config.reconnect_backoff_seconds, 0.1)
        attempt = 0
        last_exc: Optional[Exception] = None

        while attempt <= max_attempts:
            if attempt > 0:
                delay = backoff * (2 ** (attempt - 1))
                logging.warning(
                    "Speechmatics connection retry %d/%d in %.1f seconds.",
                    attempt,
                    max_attempts,
                    delay,
                )
                await asyncio.sleep(delay)

            try:
                ws_url, headers = await self._build_connection_params()
                await self._open_connection(ws_url, headers)
                logging.info("Connected to Speechmatics realtime endpoint.")
                return
            except SpeechmaticsRealtimeError as exc:
                last_exc = exc
                logging.error("Speechmatics connection attempt failed: %s", exc)
                await self.close()
            attempt += 1

        raise SpeechmaticsRealtimeError(
            f"Failed to connect to Speechmatics after {max_attempts + 1} attempts."
        ) from last_exc

    async def _authorize_jwt(self) -> Optional[str]:
        """Exchange API key for a short-lived JWT via HTTPS.

        Builds the authorize URL from the configured WebSocket endpoint by
        switching scheme to https and appending the authorize path.
        """

        api_key = (self.config.api_key or "").strip()
        if not api_key:
            return None

        # Management Platform temporary token endpoint (per official SDK semantics)
        # POST https://mp.speechmatics.com/v1/api_keys?type=rt&sm-sdk=python-<ver>
        # Headers: Authorization: Bearer <API_KEY>
        # Body: {"ttl": <seconds>, "region": "eu"|"us"}

        parsed_ws = urlparse(self.config.connection_url)
        region = "eu" if parsed_ws.netloc.startswith("eu") else "us"

        endpoint = "https://mp.speechmatics.com/v1/api_keys"
        params = {"type": "rt", "sm-sdk": "python-custom"}
        payload = {"ttl": int(self.config.jwt_ttl_seconds), "region": region}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        timeout = aiohttp.ClientTimeout(total=10)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, params=params, json=payload, headers=headers) as resp:
                    if resp.status not in (200, 201):
                        text = await resp.text()
                        logging.error("JWT authorize failed (%s): %s", resp.status, text)
                        return None
                    data = await resp.json()
                    token = data.get("key_value") or data.get("token") or data.get("jwt")
                    if not token:
                        logging.error("JWT authorize response missing token: %s", data)
                    return token
        except Exception as exc:  # pylint: disable=broad-except
            logging.exception("JWT authorize error: %s", exc)
            return None

    @staticmethod
    def _augment_ws_url_with_language(base_url: str, language: str) -> str:
        parsed = urlparse(base_url)
        path = parsed.path or "/v2"
        lang = (language or "").strip()
        if not lang:
            return base_url
        if not path.endswith(f"/{lang}"):
            if path.endswith("/"):
                path += lang
            else:
                path += f"/{lang}"
        return urlunparse(parsed._replace(path=path))

    async def _build_connection_params(self) -> tuple[str, Dict[str, str]]:
        token = self.config.jwt_token
        if not token:
            token = await self._authorize_jwt()
        if not token:
            raise SpeechmaticsRealtimeError("Failed to obtain JWT for Speechmatics.")
        headers = {"Authorization": f"Bearer {token}"}
        ws_url = self._augment_ws_url_with_language(self.config.connection_url, self.config.language)
        return ws_url, headers

    async def _open_connection(self, ws_url: str, headers: Dict[str, str]) -> None:
        try:
            self._websocket = await websockets.connect(
                ws_url,
                additional_headers=headers,
                max_size=4 * 1024 * 1024,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
                max_queue=32,
            )
        except Exception as exc:  # pylint: disable=broad-except
            raise SpeechmaticsRealtimeError(f"Failed to connect to Speechmatics: {exc}") from exc

        await self._send_start_message()
        self._connected.set()
        self._listen_task = asyncio.create_task(self._listen_loop(), name="speechmatics-listener")

    async def close(self) -> None:
        """Close the websocket connection gracefully."""

        if self._listen_task:
            self._listen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listen_task
            self._listen_task = None

        if self._websocket:
            try:
                await self._websocket.close()
            finally:
                self._websocket = None
        self._connected.clear()
        self._recognition_started.clear()

    async def send_audio_chunk(self, chunk: bytes) -> None:
        """Send raw PCM audio bytes to the websocket."""

        if self._websocket is None or not self._connected.is_set():
            raise SpeechmaticsRealtimeError("Connection is not established.")
        if not self._recognition_started.is_set():
            try:
                await asyncio.wait_for(self._recognition_started.wait(), timeout=5.0)
            except asyncio.TimeoutError as exc:
                raise SpeechmaticsRealtimeError("Recognition did not start in time.") from exc
        try:
            await self._websocket.send(chunk)
        except Exception as exc:  # pylint: disable=broad-except
            raise SpeechmaticsRealtimeError(f"Failed to stream audio: {exc}") from exc

    async def transcript_results(self) -> AsyncGenerator[TranscriptSegment, None]:
        """Yield transcript results as they arrive."""

        while True:
            result = await self._transcript_queue.get()
            yield result

    async def _send_start_message(self) -> None:
        if self._websocket is None:
            raise SpeechmaticsRealtimeError("Websocket is not connected.")

        diarization_mode = "speaker" if self.config.enable_diarization else None
        start_message = {
            "message": "StartRecognition",
            "transcription_config": {
                "language": self.config.language,
                "enable_partials": True,
            },
            "audio_format": {
                "type": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": self.config.sample_rate,
            },
        }
        if diarization_mode:
            start_message["transcription_config"]["diarization"] = diarization_mode
        await self._websocket.send(json.dumps(start_message))
        logging.debug("Sent Speechmatics StartRecognition: %s", start_message)

    async def _listen_loop(self) -> None:
        """Receive transcript messages and push them into the queue."""

        assert self._websocket is not None  # nosec B101
        try:
            async for message in self._websocket:
                if isinstance(message, bytes):
                    logging.debug("Received binary %d bytes (ignored)", len(message))
                    continue
                payload = json.loads(message)
                msg_type = payload.get("message") or payload.get("type")
                if msg_type == "RecognitionStarted":
                    self._recognition_started.set()
                    logging.info("Recognition started.")
                elif msg_type in ("AddPartialTranscript", "AddTranscript"):
                    transcript = self._parse_transcript(payload)
                    if transcript:
                        await self._transcript_queue.put(transcript)
                elif msg_type in ("Warning",):
                    logging.warning("Speechmatics warning: %s", payload)
                elif msg_type in ("Error", "error"):
                    logging.error("Speechmatics error: %s", payload)
                else:
                    logging.debug("Speechmatics message ignored: %s", payload)
        except asyncio.CancelledError:
            logging.info("Speechmatics listener cancelled.")
            raise
        except Exception as exc:  # pylint: disable=broad-except
            logging.exception("Error while listening to Speechmatics stream: %s", exc)
            raise SpeechmaticsRealtimeError("Listener stopped unexpectedly.") from exc

    def _parse_transcript(self, payload: Dict) -> Optional[TranscriptSegment]:
        md = payload.get("metadata") or {}
        text = (md.get("transcript") or "").strip()
        if not text:
            return None
        is_final = (payload.get("message") == "AddTranscript")
        words = md.get("words") or []
        start_time = words[0].get("start_time") if words else None
        end_time = words[-1].get("end_time") if words else None

        transcript = TranscriptSegment(
            text=text,
            is_final=is_final,
            speaker=md.get("speaker"),
            start_time=start_time,
            end_time=end_time,
            raw=payload,
        )
        logging.debug(
            "Speechmatics transcript: %s (final=%s, speaker=%s)",
            transcript.text,
            transcript.is_final,
            transcript.speaker,
        )
        return transcript
