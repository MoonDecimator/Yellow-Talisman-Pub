"""Minimal read-only GitHub REST API client."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


DEFAULT_API_URL = "https://api.github.com"
DEFAULT_API_VERSION = "2022-11-28"


class GitHubApiError(RuntimeError):
    """A failed GitHub REST API request."""

    def __init__(
        self,
        status: int | None,
        url: str,
        message: str,
        *,
        rate_limited: bool = False,
    ) -> None:
        status_label = str(status) if status is not None else "transport"
        super().__init__(
            f"GitHub API GET failed ({status_label}) for {url}: {message}"
        )
        self.status = status
        self.url = url
        self.rate_limited = rate_limited


class GitHubNotFoundError(GitHubApiError):
    """A GitHub REST resource that does not exist."""


Transport = Callable[[Request], Any]
Sleep = Callable[[float], None]
Clock = Callable[[], float]


@dataclass(frozen=True, slots=True)
class ApiTelemetry:
    """Read-only snapshot of API usage and observed rate-limit headers."""

    requests: int
    retries: int
    rate_limit_remaining: int | None
    rate_limit_reset: int | None


class GitHubApi:
    """Perform authenticated GitHub API GET requests and pagination."""

    def __init__(
        self,
        token: str,
        *,
        api_url: str = DEFAULT_API_URL,
        transport: Transport = urlopen,
        max_attempts: int = 3,
        backoff_base_seconds: float = 1.0,
        sleep: Sleep = time.sleep,
        clock: Clock = time.time,
    ) -> None:
        if not token:
            raise ValueError("A GitHub token is required.")
        self._token = token
        self._api_url = api_url.rstrip("/") + "/"
        self._transport = transport
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")
        if backoff_base_seconds < 0:
            raise ValueError("backoff_base_seconds cannot be negative.")
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds
        self._sleep = sleep
        self._clock = clock
        self._requests = 0
        self._retries = 0
        self._rate_limit_remaining: int | None = None
        self._rate_limit_reset: int | None = None

    @property
    def telemetry(self) -> ApiTelemetry:
        """Return current request, retry, and rate-limit counters."""

        return ApiTelemetry(
            requests=self._requests,
            retries=self._retries,
            rate_limit_remaining=self._rate_limit_remaining,
            rate_limit_reset=self._rate_limit_reset,
        )

    def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
    ) -> Any:
        """GET and decode one JSON response."""

        payload, _ = self._get(path, params=params)
        return json.loads(payload.decode("utf-8"))

    def get_text(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        accept: str = "application/vnd.github.raw+json",
    ) -> str:
        """GET and decode a text response, normally raw repository content."""

        payload, _ = self._get(path, params=params, accept=accept)
        return payload.decode("utf-8")

    def get_paginated(
        self,
        path: str,
        *,
        item_key: str | None = None,
        params: Mapping[str, str | int] | None = None,
    ) -> Iterator[Any]:
        """Yield items from every page linked with rel=next."""

        query = dict(params or {})
        query.setdefault("per_page", 100)
        next_url: str | None = path
        first_page = True

        while next_url is not None:
            payload, headers = self._get(
                next_url,
                params=query if first_page else None,
            )
            first_page = False
            document = json.loads(payload.decode("utf-8"))
            items = document[item_key] if item_key is not None else document
            if not isinstance(items, list):
                raise TypeError("Paginated GitHub API response must contain a list.")
            yield from items
            next_url = _next_link(headers.get("Link", ""))

    def _get(
        self,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        accept: str = "application/vnd.github+json",
    ) -> tuple[bytes, Mapping[str, str]]:
        url = self._build_url(path, params)
        request = Request(
            url,
            method="GET",
            headers={
                "Accept": accept,
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": DEFAULT_API_VERSION,
                "User-Agent": "Yellow-Talisman",
            },
        )
        for attempt in range(self._max_attempts):
            self._requests += 1
            try:
                with self._transport(request) as response:
                    self._record_rate_limit(response.headers)
                    return response.read(), response.headers
            except HTTPError as error:
                headers = error.headers or {}
                self._record_rate_limit(headers)
                message = _http_error_message(error)
                rate_limited = _is_rate_limit_response(
                    error.code, headers, message
                )
                if self._should_retry(error.code, rate_limited, attempt):
                    self._wait_before_retry(headers, attempt)
                    continue
                error_type = (
                    GitHubNotFoundError
                    if error.code == 404
                    else GitHubApiError
                )
                raise error_type(
                    error.code,
                    url,
                    message,
                    rate_limited=rate_limited,
                ) from error
            except (TimeoutError, URLError) as error:
                if attempt + 1 < self._max_attempts:
                    self._wait_before_retry({}, attempt)
                    continue
                reason = getattr(error, "reason", None) or str(error)
                raise GitHubApiError(None, url, str(reason)) from error

        raise AssertionError("retry loop ended unexpectedly")

    def _should_retry(
        self, status: int, rate_limited: bool, attempt: int
    ) -> bool:
        if attempt + 1 >= self._max_attempts:
            return False
        return status == 429 or 500 <= status <= 599 or (
            status == 403 and rate_limited
        )

    def _wait_before_retry(
        self, headers: Mapping[str, str], attempt: int
    ) -> None:
        delay = _retry_delay(
            headers,
            attempt=attempt,
            backoff_base_seconds=self._backoff_base_seconds,
            now=self._clock(),
        )
        self._retries += 1
        self._sleep(delay)

    def _record_rate_limit(self, headers: Mapping[str, str]) -> None:
        remaining = _header_int(headers, "X-RateLimit-Remaining")
        reset = _header_int(headers, "X-RateLimit-Reset")
        if remaining is not None and (
            self._rate_limit_remaining is None
            or remaining <= self._rate_limit_remaining
        ):
            self._rate_limit_remaining = remaining
            self._rate_limit_reset = reset

    def _build_url(
        self,
        path: str,
        params: Mapping[str, str | int] | None,
    ) -> str:
        url = path if path.startswith(("https://", "http://")) else urljoin(
            self._api_url, path.lstrip("/")
        )
        if params:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(params)}"
        return url


def _next_link(link_header: str) -> str | None:
    for entry in link_header.split(","):
        parts = [part.strip() for part in entry.split(";")]
        if len(parts) >= 2 and 'rel="next"' in parts[1:]:
            return parts[0].removeprefix("<").removesuffix(">")
    return None


def is_fatal_api_error(error: GitHubApiError) -> bool:
    """Return whether a scoped operation must abort the complete audit."""

    return (
        error.status is not None
        and 400 <= error.status <= 499
        and error.status != 404
    )


def _http_error_message(error: HTTPError) -> str:
    try:
        document = json.loads(error.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return error.reason or "request failed"
    return str(document.get("message", error.reason or "request failed"))


def _is_rate_limit_response(
    status: int, headers: Mapping[str, str], message: str
) -> bool:
    if status == 429:
        return True
    if status != 403:
        return False
    return (
        _header_int(headers, "X-RateLimit-Remaining") == 0
        or bool(headers.get("Retry-After"))
        or "rate limit" in message.casefold()
    )


def _retry_delay(
    headers: Mapping[str, str],
    *,
    attempt: int,
    backoff_base_seconds: float,
    now: float,
) -> float:
    retry_after = headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after).timestamp()
            except (TypeError, ValueError, OverflowError):
                pass
            else:
                return max(0.0, retry_at - now)

    reset = _header_int(headers, "X-RateLimit-Reset")
    if reset is not None:
        return max(0.0, reset - now)
    return backoff_base_seconds * (2**attempt)


def _header_int(headers: Mapping[str, str], name: str) -> int | None:
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
