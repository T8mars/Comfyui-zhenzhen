"""Requests-compatible transport with failover for the Zhenzhen overseas API."""

from __future__ import annotations

import os
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit, urlunsplit

import requests as _requests


PRIMARY_BASE_URL = "https://ai.t8star.org"
FALLBACK_BASE_URL = "https://ai.t8star.cn"
_ZHENZHEN_HOSTS = {
    urlsplit(PRIMARY_BASE_URL).hostname,
    urlsplit(FALLBACK_BASE_URL).hostname,
}
_IDEMPOTENT_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
_CONNECT_PHASE_FRAMES = {
    "connect",
    "create_connection",
    "do_handshake",
    "_new_conn",
    "_validate_conn",
    "wrap_socket",
    "ssl_wrap_socket",
    "ssl_wrap_socket_impl",
}

try:
    _CACHE_TTL = max(30.0, float(os.environ.get("COMFLY_ZHENZHEN_ENDPOINT_TTL", "600")))
except ValueError:
    _CACHE_TTL = 600.0

_state_lock = threading.RLock()
_active_base_url = PRIMARY_BASE_URL
_checked_at = 0.0


def _is_zhenzhen_url(url):
    if not isinstance(url, str):
        return False
    try:
        return urlsplit(url).hostname in _ZHENZHEN_HOSTS
    except ValueError:
        return False


def _replace_base_url(url, base_url):
    original = urlsplit(url)
    replacement = urlsplit(base_url)
    return urlunsplit(
        (
            replacement.scheme,
            replacement.netloc,
            original.path,
            original.query,
            original.fragment,
        )
    )


def _alternate_base_url(base_url):
    host = urlsplit(base_url).hostname
    return FALLBACK_BASE_URL if host != urlsplit(FALLBACK_BASE_URL).hostname else PRIMARY_BASE_URL


def _probe(base_url, timeout=(2.5, 4.0)):
    response = None
    try:
        response = _requests.get(
            f"{base_url}/v1/models",
            allow_redirects=False,
            stream=True,
            timeout=timeout,
        )
        # Any HTTP response proves DNS, TCP and TLS connectivity. Authentication is
        # intentionally omitted, so a 401 is the expected healthy response.
        return True
    except _requests.exceptions.RequestException:
        return False
    finally:
        if response is not None:
            response.close()


def choose_zhenzhen_base_url(force=False):
    """Return the reachable overseas endpoint, preferring the legacy .org URL."""
    global _active_base_url, _checked_at

    now = time.monotonic()
    with _state_lock:
        if not force and _checked_at and now - _checked_at < _CACHE_TTL:
            return _active_base_url

        for candidate in (PRIMARY_BASE_URL, FALLBACK_BASE_URL):
            if _probe(candidate):
                previous = _active_base_url
                _active_base_url = candidate
                _checked_at = time.monotonic()
                if candidate != previous:
                    print(f"[Comfly] Zhenzhen API endpoint switched to {candidate}")
                return candidate

        # Preserve historical behavior when neither health check is reachable. The
        # real request below will then expose its original transport error.
        _active_base_url = PRIMARY_BASE_URL
        _checked_at = time.monotonic()
        return _active_base_url


def get_active_zhenzhen_base_url(probe=True):
    if probe:
        return choose_zhenzhen_base_url()
    with _state_lock:
        return _active_base_url


def rewrite_zhenzhen_url(url, probe=True):
    """Rewrite only official overseas Zhenzhen URLs; leave every other host intact."""
    if not _is_zhenzhen_url(url):
        return url
    base_url = choose_zhenzhen_base_url() if probe else get_active_zhenzhen_base_url(False)
    return _replace_base_url(url, base_url)


def _exception_chain(error):
    seen = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _failed_during_connection(error):
    if isinstance(
        error,
        (
            _requests.exceptions.ConnectTimeout,
            _requests.exceptions.ProxyError,
            _requests.exceptions.SSLError,
        ),
    ):
        return True

    for item in _exception_chain(error):
        if isinstance(item, (socket.gaierror, ConnectionRefusedError, ssl.SSLCertVerificationError)):
            return True
        traceback = item.__traceback__
        while traceback is not None:
            if traceback.tb_frame.f_code.co_name in _CONNECT_PHASE_FRAMES:
                return True
            traceback = traceback.tb_next
    return False


def _activate(base_url):
    global _active_base_url, _checked_at
    with _state_lock:
        _active_base_url = base_url
        _checked_at = time.monotonic()


def _send_with_failover(send, method, url, **kwargs):
    if not _is_zhenzhen_url(url):
        return send(method, url, **kwargs)

    method = str(method).upper()
    selected_url = rewrite_zhenzhen_url(url)
    selected_base = f"{urlsplit(selected_url).scheme}://{urlsplit(selected_url).netloc}"

    try:
        return send(method, selected_url, **kwargs)
    except _requests.exceptions.RequestException as error:
        can_retry = method in _IDEMPOTENT_METHODS or _failed_during_connection(error)
        if not can_retry:
            raise

        fallback_base = _alternate_base_url(selected_base)
        fallback_url = _replace_base_url(url, fallback_base)
        _activate(fallback_base)
        print(
            f"[Comfly] Zhenzhen API connection failed at {selected_base}; "
            f"retrying once via {fallback_base}"
        )
        return send(method, fallback_url, **kwargs)


def request(method, url, **kwargs):
    return _send_with_failover(_requests.request, method, url, **kwargs)


def get(url, params=None, **kwargs):
    return request("GET", url, params=params, **kwargs)


def options(url, **kwargs):
    return request("OPTIONS", url, **kwargs)


def head(url, **kwargs):
    kwargs.setdefault("allow_redirects", False)
    return request("HEAD", url, **kwargs)


def post(url, data=None, json=None, **kwargs):
    return request("POST", url, data=data, json=json, **kwargs)


def put(url, data=None, **kwargs):
    return request("PUT", url, data=data, **kwargs)


def patch(url, data=None, **kwargs):
    return request("PATCH", url, data=data, **kwargs)


def delete(url, **kwargs):
    return request("DELETE", url, **kwargs)


class Session(_requests.Session):
    def request(self, method, url, **kwargs):
        parent_request = super().request
        return _send_with_failover(parent_request, method, url, **kwargs)


def session():
    return Session()


def reset_endpoint_cache():
    """Reset process-local endpoint state. Intended for tests and manual diagnostics."""
    global _active_base_url, _checked_at
    with _state_lock:
        _active_base_url = PRIMARY_BASE_URL
        _checked_at = 0.0


def __getattr__(name):
    # Preserve requests.exceptions, requests.adapters, requests.packages, and other
    # compatibility attributes used throughout the legacy node collection.
    return getattr(_requests, name)
