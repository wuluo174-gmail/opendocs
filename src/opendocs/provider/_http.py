"""Minimal HTTP helpers using only stdlib urllib."""

from __future__ import annotations

import json
import urllib.request
import urllib.error


def http_post_json(
    url: str,
    body: dict,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> dict:
    """POST JSON payload via urllib, return parsed JSON response."""
    data = json.dumps(body).encode()
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def http_get_ok(url: str, *, timeout: int = 5) -> bool:
    """GET request, return True if status 2xx."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError):
        return False
