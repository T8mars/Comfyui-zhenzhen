"""Route-isolated HTTP retry policy for safe external requests."""

import asyncio
import os
import time
from urllib.parse import urlsplit, urlunsplit

import requests


T8STAR_ROUTE_ATTEMPTS = (
    ("direct", False),
    ("proxy", True),
    ("direct", False),
    ("proxy", True),
)
T8STAR_RETRY_DELAYS = (1, 5, 10)
T8STAR_RETRYABLE_STATUS_CODES = frozenset({429, 502, 503, 504})
T8STAR_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
T8STAR_RETRYABLE_NETWORK_ERRORS = (
    requests.ConnectionError,
    requests.Timeout,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.ContentDecodingError,
)
DEFAULT_MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
DEFAULT_TIMEOUT = (15, 120)


def _url_without_query(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def create_alternating_route_session(route_attempt: int) -> requests.Session:
    """Create one isolated session for a caller-owned retry loop."""
    _mode, trust_env = T8STAR_ROUTE_ATTEMPTS[
        route_attempt % len(T8STAR_ROUTE_ATTEMPTS)
    ]
    session = requests.Session()
    session.trust_env = trust_env
    return session


def _rewind_files(files) -> None:
    if not files:
        return
    values = files.values() if isinstance(files, dict) else files
    for item in values:
        candidate = item
        if isinstance(item, tuple):
            candidate = next(
                (part for part in item if hasattr(part, "seek")), None
            )
        if hasattr(candidate, "seek"):
            candidate.seek(0)


class T8StarRouteSession:
    """Small requests-compatible client with fixed route alternation.

    Idempotent requests start with a fresh direct session. Transient transport
    failures and HTTP 429/502/503/504 then use proxy, direct, and proxy in that
    order, waiting 1/5/10 seconds. Paid or otherwise non-idempotent requests
    are sent once through the direct route so an ambiguous response cannot
    create duplicate work. Environment proxy variables are never changed.
    """

    def request(self, method: str, url: str, **kwargs):
        normalized_method = method.upper()
        consume = kwargs.pop("_consume", None)
        if normalized_method not in T8STAR_IDEMPOTENT_METHODS:
            with create_alternating_route_session(0) as session:
                return session.request(normalized_method, url, **kwargs)

        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)

        safe_url = _url_without_query(url)
        last_error = None
        last_response = None

        for attempt, (mode, trust_env) in enumerate(
            T8STAR_ROUTE_ATTEMPTS, start=1
        ):
            if attempt > 1:
                time.sleep(T8STAR_RETRY_DELAYS[attempt - 2])
            try:
                with create_alternating_route_session(attempt - 1) as session:
                    response = session.request(normalized_method, url, **kwargs)
                    last_error = None
                    if response.status_code not in T8STAR_RETRYABLE_STATUS_CODES:
                        if consume is None:
                            return response
                        try:
                            return consume(response)
                        finally:
                            response.close()

                    last_response = response
                    print(
                        f"[t8star] HTTP {response.status_code} for {safe_url} "
                        f"(attempt {attempt}/{len(T8STAR_ROUTE_ATTEMPTS)}, "
                        f"mode={mode})"
                    )
            except T8STAR_RETRYABLE_NETWORK_ERRORS as error:
                last_error = error
                print(
                    f"[t8star] Request failed for {safe_url} "
                    f"(attempt {attempt}/{len(T8STAR_ROUTE_ATTEMPTS)}, "
                    f"mode={mode}): {type(error).__name__}"
                )

        if last_error is not None:
            raise last_error
        if consume is not None and last_response is not None:
            last_response.raise_for_status()
        return last_response

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def close(self):
        return None


def create_t8star_session() -> T8StarRouteSession:
    return T8StarRouteSession()


def safe_get(url: str, **kwargs):
    return create_t8star_session().get(url, **kwargs)


def safe_get_content(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
    chunk_size: int = 64 * 1024,
    **kwargs,
) -> bytes:
    """Read a complete GET body inside the four-route retry boundary."""
    kwargs.pop("stream", None)

    def consume(response):
        response.raise_for_status()
        content_length = response.headers.get("Content-Length", "")
        if content_length.isdigit() and int(content_length) > max_bytes:
            raise ValueError(f"remote file exceeds {max_bytes} bytes")
        body = bytearray()
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise ValueError(f"remote file exceeds {max_bytes} bytes")
        return bytes(body)

    return create_t8star_session().request(
        "GET", url, _consume=consume, stream=True, **kwargs
    )


def safe_download_to_path(
    url: str,
    output_path: str,
    *,
    max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
    chunk_size: int = 64 * 1024,
    **kwargs,
) -> int:
    """Download from byte zero after a retryable TLS/stream interruption."""
    kwargs.pop("stream", None)

    def consume(response):
        response.raise_for_status()
        content_length = response.headers.get("Content-Length", "")
        if content_length.isdigit() and int(content_length) > max_bytes:
            raise ValueError(f"remote file exceeds {max_bytes} bytes")
        total = 0
        with open(output_path, "wb") as output:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"remote file exceeds {max_bytes} bytes")
                output.write(chunk)
        return total

    try:
        return create_t8star_session().request(
            "GET", url, _consume=consume, stream=True, **kwargs
        )
    except Exception:
        if os.path.exists(output_path):
            os.remove(output_path)
        raise


def safe_upload_post(url: str, **kwargs):
    """Retry an explicitly non-billable upload POST over all four routes."""
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    safe_url = _url_without_query(url)
    last_error = None
    last_response = None
    for attempt, (mode, _trust_env) in enumerate(T8STAR_ROUTE_ATTEMPTS):
        if attempt > 0:
            time.sleep(T8STAR_RETRY_DELAYS[attempt - 1])
        _rewind_files(kwargs.get("files"))
        try:
            with create_alternating_route_session(attempt) as session:
                response = session.post(url, **kwargs)
                last_error = None
                if response.status_code not in T8STAR_RETRYABLE_STATUS_CODES:
                    return response
                last_response = response
                print(
                    f"[t8star] Upload HTTP {response.status_code} for {safe_url} "
                    f"(attempt {attempt + 1}/4, mode={mode})"
                )
                if attempt + 1 < len(T8STAR_ROUTE_ATTEMPTS):
                    response.close()
        except T8STAR_RETRYABLE_NETWORK_ERRORS as error:
            last_error = error
            print(
                f"[t8star] Upload failed for {safe_url} "
                f"(attempt {attempt + 1}/4, mode={mode}): "
                f"{type(error).__name__}"
            )
    if last_error is not None:
        raise last_error
    return last_response


def safe_idempotent_post(url: str, **kwargs):
    """Retry a documented non-billable, idempotent POST over all routes."""
    return safe_upload_post(url, **kwargs)


def safe_chat_post(url: str, **kwargs):
    """Retry synchronous chat POSTs with an explicit duplicate-billing risk."""
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    safe_url = _url_without_query(url)
    last_error = None
    last_response = None
    for attempt, (mode, _trust_env) in enumerate(T8STAR_ROUTE_ATTEMPTS):
        if attempt > 0:
            time.sleep(T8STAR_RETRY_DELAYS[attempt - 1])
        response = None
        try:
            with create_alternating_route_session(attempt) as session:
                response = session.post(url, **kwargs)
                last_error = None
                if response.status_code not in T8STAR_RETRYABLE_STATUS_CODES:
                    if kwargs.get("stream"):
                        # Read the complete SSE body while failures can still
                        # switch routes and replay the chat request.
                        _ = response.content
                    return response
                last_response = response
                print(
                    f"[t8star] Chat HTTP {response.status_code} for {safe_url} "
                    f"(attempt {attempt + 1}/4, mode={mode}); "
                    "duplicate chat billing is possible"
                )
                if attempt + 1 < len(T8STAR_ROUTE_ATTEMPTS):
                    response.close()
        except T8STAR_RETRYABLE_NETWORK_ERRORS as error:
            last_error = error
            if response is not None:
                response.close()
            print(
                f"[t8star] Chat failed for {safe_url} "
                f"(attempt {attempt + 1}/4, mode={mode}): "
                f"{type(error).__name__}; duplicate chat billing is possible"
            )
    if last_error is not None:
        raise last_error
    return last_response


class _AsyncResponseAdapter:
    def __init__(self, response):
        self._response = response
        self.status = response.status_code

    async def json(self):
        return self._response.json()

    async def text(self):
        return self._response.text


class _AsyncSafeGetContext:
    def __init__(self, url, kwargs, caller=safe_get):
        self.url = url
        self.kwargs = kwargs
        self.caller = caller
        self.response = None

    async def __aenter__(self):
        self.response = await asyncio.to_thread(
            self.caller, self.url, **self.kwargs
        )
        return _AsyncResponseAdapter(self.response)

    async def __aexit__(self, _exc_type, _exc, _traceback):
        if self.response is not None:
            self.response.close()


def async_safe_get(url: str, **kwargs):
    return _AsyncSafeGetContext(url, kwargs)


def async_safe_upload_post(url: str, **kwargs):
    return _AsyncSafeGetContext(url, kwargs, caller=safe_upload_post)
