"""Translation service implementation (LibreTranslate default)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import aiohttp

try:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import service_account
except ImportError:  # pragma: no cover - optional dependency
    GoogleAuthRequest = None
    service_account = None

@dataclass
class TranslationResult:
    text: str
    translations: Dict[str, str]


class TranslationService:
    """Translate Esperanto transcripts into target languages."""

    def __init__(
        self,
        enabled: bool,
        source_language: str = "eo",
        targets: Optional[Iterable[str]] = None,
        provider: str = "libre",
        libre_url: str = "https://libretranslate.de",
        libre_api_key: Optional[str] = None,
        timeout: float = 8.0,
        google_api_key: Optional[str] = None,
        google_model: Optional[str] = None,
        google_credentials_path: Optional[str] = None,
        cache_ttl_seconds: float = 120.0,
        cache_max_size: int = 128,
    ) -> None:
        self.enabled = enabled and bool(targets)
        self.source_language = source_language
        self.targets = list(targets or [])
        self.provider = provider
        self.libre_url = libre_url.rstrip("/")
        self.libre_api_key = libre_api_key
        self.google_api_key = google_api_key
        self.google_model = google_model
        self.google_credentials_path = Path(google_credentials_path).expanduser() if google_credentials_path else None
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        self._cache: "OrderedDict[Tuple[str, Tuple[str, ...], str, str], Tuple[float, Dict[str, str]]]" = OrderedDict()
        self._cache_ttl = max(cache_ttl_seconds, 0.0)
        self._cache_max_size = max(cache_max_size, 1)
        self._google_credentials = None
        self._google_request = None
        if self.provider == "google" and not self.google_api_key:
            if self.google_credentials_path and service_account and GoogleAuthRequest:
                try:
                    self._google_credentials = service_account.Credentials.from_service_account_file(
                        str(self.google_credentials_path),
                        scopes=["https://www.googleapis.com/auth/cloud-translation"],
                    )
                    self._google_request = GoogleAuthRequest()
                except Exception as exc:  # noqa: BLE001
                    logging.error("Failed to load Google credentials from %s: %s", self.google_credentials_path, exc)
            elif not self.google_credentials_path:
                logging.error("Google translation provider selected but GOOGLE_TRANSLATE_CREDENTIALS_PATH not set.")
            else:
                logging.error(
                    "google-auth not available; install google-auth to use service account credentials."
                )

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def _cache_key(self, text: str) -> Tuple[str, Tuple[str, ...], str, str]:
        return (
            text.strip(),
            tuple(sorted(self.targets)),
            self.provider,
            self.source_language,
        )

    def _get_cached(self, key: Tuple[str, Tuple[str, ...], str, str]) -> Optional[Dict[str, str]]:
        if self._cache_ttl <= 0:
            return None
        now = time.time()
        expired_before = now - self._cache_ttl
        # Remove expired entries lazily.
        while self._cache and next(iter(self._cache.values()))[0] < expired_before:
            self._cache.popitem(last=False)
        cached = self._cache.get(key)
        if not cached:
            return None
        timestamp, translations = cached
        if timestamp < expired_before:
            self._cache.pop(key, None)
            return None
        # Move to end for LRU behaviour.
        self._cache.move_to_end(key)
        return dict(translations)

    def _store_cache(self, key: Tuple[str, Tuple[str, ...], str, str], translations: Dict[str, str]) -> None:
        if self._cache_ttl <= 0:
            return
        while len(self._cache) >= self._cache_max_size:
            self._cache.popitem(last=False)
        self._cache[key] = (time.time(), dict(translations))

    async def translate(self, text: str) -> TranslationResult:
        if not self.enabled or not text.strip():
            return TranslationResult(text=text, translations={})

        translations: Dict[str, str] = {}
        key = self._cache_key(text)
        cached = self._get_cached(key)
        if cached is not None:
            return TranslationResult(text=text, translations=cached)

        async with self._lock:
            cached = self._get_cached(key)
            if cached is not None:
                return TranslationResult(text=text, translations=cached)

            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(timeout=self._timeout)

            tasks = [self._translate_single(text, target) for target in self.targets]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for target, result in zip(self.targets, results):
                if isinstance(result, Exception):
                    logging.error("Translation to %s failed: %s", target, result)
                elif result:
                    translations[target] = result
            self._store_cache(key, translations)

        return TranslationResult(text=text, translations=translations)

    async def _translate_single(self, text: str, target: str) -> Optional[str]:
        if self.provider == "libre":
            return await self._translate_libre(text, target)
        if self.provider == "google":
            return await self._translate_google(text, target)
        logging.error("Unknown translation provider: %s", self.provider)
        return None

    async def _translate_libre(self, text: str, target: str) -> Optional[str]:
        assert self._session
        payload = {
            "q": text,
            "source": self.source_language,
            "target": target,
            "format": "text",
        }
        if self.libre_api_key:
            payload["api_key"] = self.libre_api_key

        url = f"{self.libre_url}/translate"
        async with self._session.post(url, json=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"HTTP {resp.status}: {body}")
            data = await resp.json()
            return data.get("translatedText")

    async def _translate_google(self, text: str, target: str) -> Optional[str]:
        assert self._session
        params = {}
        headers = {}
        if self.google_api_key:
            params["key"] = self.google_api_key
        elif self._google_credentials and self._google_request:
            await self._ensure_google_token()
            if not self._google_credentials.token:
                logging.error("Failed to obtain Google OAuth token for translation.")
                return None
            headers["Authorization"] = f"Bearer {self._google_credentials.token}"
        else:
            logging.error(
                "Google translation requested but neither GOOGLE_TRANSLATE_API_KEY nor valid credentials provided."
            )
            return None
        payload = {
            "q": text,
            "source": self.source_language,
            "target": target,
            "format": "text",
        }
        if self.google_model:
            payload["model"] = self.google_model
        url = "https://translation.googleapis.com/language/translate/v2"
        async with self._session.post(url, params=params, json=payload, headers=headers) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"HTTP {resp.status}: {body}")
            data = await resp.json()
            translations = data.get("data", {}).get("translations", [])
            if translations:
                return translations[0].get("translatedText")
            return None

    async def _ensure_google_token(self) -> None:
        if not self._google_credentials or not self._google_request:
            return
        if self._google_credentials.valid and self._google_credentials.token:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._google_credentials.refresh, self._google_request)
