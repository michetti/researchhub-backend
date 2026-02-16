"""Cache helpers for endorsements list responses.

This module centralizes the endorsements list-cache strategy:
- cache only page 1 responses;
- use a short TTL for shared-cache hygiene;
- invalidate all cached list variants by bumping a generation key on writes.
"""

import hashlib
from typing import Any
from urllib.parse import urlencode

from django.core.cache import cache
from rest_framework.request import Request

LIST_CACHE_TIMEOUT = 60 * 5
LIST_CACHE_VERSION_KEY = "endorsements:list:version"
NUM_PAGES_TO_CACHE = 1


def _get_list_cache_version() -> int:
    """Return the current list cache generation, creating it if needed."""
    version = cache.get(LIST_CACHE_VERSION_KEY)
    if version is None:
        version = 1
        cache.set(LIST_CACHE_VERSION_KEY, version, timeout=None)
    return int(version)


def bump_list_cache_version() -> None:
    """Invalidate all list cache variants by advancing the generation key."""
    try:
        cache.incr(LIST_CACHE_VERSION_KEY)
    except Exception:
        # Fall back when the key is missing or backend doesn't support atomic increment.
        current_version = _get_list_cache_version()
        cache.set(
            LIST_CACHE_VERSION_KEY,
            current_version + 1,
            timeout=None,
        )


def _should_use_list_cache(request: Request) -> bool:
    """Return True only for pages that are in the cache budget."""
    try:
        page_num = int(request.query_params.get("page", "1"))
    except (TypeError, ValueError):
        return False

    return page_num <= NUM_PAGES_TO_CACHE


def get_list_cache_key(request: Request) -> str | None:
    """Build a stable cache key for the current list request.

    Keys are request-specific (path + normalized query params) and generation-aware.
    Returning ``None`` means this request should bypass list caching.
    """
    if not _should_use_list_cache(request):
        return None

    query_items = []
    for key in sorted(request.query_params.keys()):
        values = request.query_params.getlist(key)
        for value in values:
            query_items.append((key, value))

    normalized_query = urlencode(query_items, doseq=True)
    request_signature = f"{request.path}?{normalized_query}"
    request_hash = hashlib.sha256(request_signature.encode("utf-8")).hexdigest()
    version = _get_list_cache_version()

    return f"endorsements:list:v{version}:{request_hash}"


def get_cached_list_response(cache_key: str | None) -> Any | None:
    """Fetch a cached list response payload by key."""
    if cache_key is None:
        return None
    return cache.get(cache_key)


def set_cached_list_response(cache_key: str | None, data: Any) -> None:
    """Store a list response payload with the configured list TTL."""
    if cache_key is None:
        return
    cache.set(cache_key, data, timeout=LIST_CACHE_TIMEOUT)
