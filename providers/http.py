"""Bounded HTTP, sanitized observable events, TTL cache and SerpApi accounting."""

import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from time import sleep, time
from typing import Callable

import httpx

from config import ROOT, Settings
from tools.common import ToolFailure
from tracing import now, redact


class ProviderClient:
    def __init__(
        self,
        settings: Settings,
        on_event: Callable | None = None,
        client: httpx.Client | None = None,
        cache_path: Path | None = None,
    ):
        self.settings = settings
        # Provider URLs carry api_key query parameters; suppress wire/request logging.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        self.client = client or httpx.Client(timeout=settings.http_timeout, follow_redirects=False)
        self.on_event = on_event
        self.cache_path = cache_path or ROOT / ".cache" / "providers.sqlite3"
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, expires REAL, payload TEXT)"
            )
            conn.execute("DELETE FROM responses WHERE expires < ?", (time(),))
        self.serpapi_requests = 0
        self.cache_hits = 0
        self.http_requests = 0
        self.account_requests = 0
        self.account_checked = False
        self.account_remaining: int | None = None
        self.memory: dict[str, dict] = {}
        self.errors: dict[str, object] = {}
        self.disabled_error = None

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.cache_path, timeout=10)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def emit(self, kind: str, **values):
        if self.on_event:
            self.on_event(kind, **redact(values))

    def close(self):
        self.client.close()

    def stats(self) -> dict:
        return dict(
            serpapi_requests=self.serpapi_requests,
            provider_cache_hits=self.cache_hits,
            http_requests=self.http_requests,
            account_api_requests=self.account_requests,
            account_searches_left=self.account_remaining,
            max_serpapi_requests=self.settings.max_serpapi_requests,
        )

    def get_json(
        self,
        url: str,
        params: dict,
        *,
        ttl: int = 3600,
        serp: bool = False,
        account: bool = False,
        refresh: bool = False,
    ) -> dict:
        clean_params = {k: v for k, v in params.items() if v is not None}
        namespace = (
            hashlib.sha256(self.settings.serpapi_api_key.encode()).hexdigest()
            if serp or account
            else "public"
        )
        key = hashlib.sha256(
            (namespace + url + json.dumps(clean_params, sort_keys=True, default=str)).encode()
        ).hexdigest()
        if key in self.memory and not refresh:
            self.cache_hits += 1
            self.emit(
                "provider_cache_hit",
                provider="SerpApi" if serp else "Open-Meteo",
                parameters=clean_params,
            )
            return self.memory[key]
        with self.connection() as conn:
            row = conn.execute(
                "SELECT payload FROM responses WHERE key=? AND expires>?", (key, time())
            ).fetchone()
        if row and not refresh:
            self.cache_hits += 1
            self.memory[key] = json.loads(row[0])
            self.emit(
                "provider_cache_hit",
                provider="SerpApi" if serp or account else "Open-Meteo",
                parameters=clean_params,
            )
            return self.memory[key]
        if key in self.errors:
            error = self.errors[key]
            raise ToolFailure(error.code, error.message, error.suggestions)
        if (serp or account) and self.disabled_error:
            error = self.disabled_error
            raise ToolFailure(error.code, error.message, error.suggestions)
        if (serp or account) and not self.settings.serpapi_api_key:
            raise ToolFailure(
                "missing_api_key",
                "SERPAPI_API_KEY is missing. Configure .env; Live Mode never falls back to demo data.",
                ["Add your SerpApi key and restart the application."],
            )
        wire_params = dict(clean_params)
        if serp or account:
            wire_params["api_key"] = self.settings.serpapi_api_key
        for attempt in range(2):
            if serp:
                if self.serpapi_requests >= self.settings.max_serpapi_requests:
                    raise ToolFailure(
                        "request_limit",
                        "The SerpApi request limit for this run has been reached.",
                        [
                            "Reuse already retrieved options or finish with an explanation. Do not repeat searches."
                        ],
                    )
                if self.account_remaining is not None and self.account_remaining <= 0:
                    raise ToolFailure(
                        "quota_exhausted",
                        "No SerpApi searches remain on the configured account.",
                        [
                            "Wait for the quota renewal or use cached results. No subscription is changed by this app."
                        ],
                    )
                self.serpapi_requests += 1  # Count attempts conservatively, even failures.
                if self.account_remaining is not None:
                    self.account_remaining -= 1
            if account:
                self.account_requests += 1
            self.http_requests += 1
            self.emit(
                "provider_request",
                provider="SerpApi" if serp or account else "Open-Meteo",
                endpoint=url,
                parameters=clean_params,
                attempt=attempt + 1,
                counters=self.stats(),
            )
            try:
                response = self.client.get(
                    url, params=wire_params, timeout=self.settings.http_timeout
                )
            except httpx.RequestError:
                self.emit(
                    "provider_error",
                    code="timeout_or_connection",
                    endpoint=url,
                    attempt=attempt + 1,
                )
                if attempt == 0:
                    sleep(0.25)
                    continue
                raise ToolFailure(
                    "provider_timeout",
                    "The data provider timed out or could not be reached.",
                    ["Retry later; cached results may still be available."],
                ) from None
            if response.status_code in (401, 403):
                failure = ToolFailure(
                    "invalid_api_key",
                    "The data provider rejected the API credentials or account permissions.",
                    ["Check SERPAPI_API_KEY and account status."],
                )
                self.disabled_error = failure.error
                raise failure
            if response.status_code == 429:
                failure = ToolFailure(
                    "quota_or_rate_limit",
                    "The provider's quota or rate limit was reached.",
                    ["Reuse cached data, stop searching, or wait for renewal."],
                )
                self.disabled_error = failure.error
                raise failure
            if response.status_code >= 500 and attempt == 0:
                sleep(0.25)
                continue
            if response.status_code >= 400:
                raise ToolFailure(
                    "provider_http_error",
                    f"Provider returned HTTP {response.status_code}.",
                    ["Check the tool arguments or try a different route/date."],
                )
            try:
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Expected object")
            except (ValueError, TypeError):
                raise ToolFailure(
                    "invalid_provider_response",
                    "The provider did not return a JSON object.",
                    ["Retry later."],
                ) from None
            if payload.get("error"):
                error = str(payload["error"]).lower()
                code = (
                    "no_results"
                    if any(
                        word in error
                        for word in (
                            "no results",
                            "hasn't returned",
                            "has not returned",
                            "not returned any",
                        )
                    )
                    else "provider_error"
                )
                if "api key" in error or "api_key" in error:
                    code = "invalid_api_key"
                if "limit" in error or "credits" in error:
                    code = "quota_or_rate_limit"
                # Never persist raw provider error bodies, which may echo credential-bearing URLs.
                failure = ToolFailure(
                    code,
                    f"The provider returned {code.replace('_', ' ')}.",
                    ["Adjust search filters or dates; check credentials/quota if applicable."],
                )
                self.errors[key] = failure.error
                if code in {"invalid_api_key", "quota_or_rate_limit"}:
                    self.disabled_error = failure.error
                raise failure
            if account:
                # The Account API includes api_key/email. Keep only quota fields.
                payload = {
                    k: payload[k]
                    for k in ("total_searches_left", "plan_searches_left", "account_status")
                    if k in payload
                }
            payload = redact(payload)
            payload["_retrieved_at"] = now()
            self.memory[key] = payload
            with self.connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO responses VALUES (?,?,?)",
                    (key, time() + ttl, json.dumps(payload)),
                )
            self.emit(
                "provider_result",
                endpoint=url,
                parameters=clean_params,
                result=payload,
                counters=self.stats(),
            )
            return payload
        raise ToolFailure(
            "provider_unavailable", "The external data provider is unavailable.", ["Retry later."]
        )

    def account(self, refresh: bool = False) -> dict:
        if self.account_checked and not refresh:
            return {"total_searches_left": self.account_remaining}
        result = self.get_json(
            "https://serpapi.com/account.json", {}, ttl=300, account=True, refresh=refresh
        )
        remaining = result.get("total_searches_left", result.get("plan_searches_left"))
        self.account_remaining = int(remaining) if remaining is not None else None
        self.account_checked = True
        return result

    def search(self, engine: str, **params) -> dict:
        if not self.account_checked:
            try:
                self.account()
            except ToolFailure as exc:
                if exc.error.code in {"invalid_api_key", "missing_api_key", "quota_or_rate_limit"}:
                    raise
                self.account_checked = True
                self.emit("account_check_unavailable", error=exc.error.model_dump())
        return self.get_json(
            "https://serpapi.com/search.json",
            {"engine": engine, "hl": "en", **params},
            serp=True,
            ttl=3600,
        )
