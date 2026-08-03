"""Phase 8c.1 — Real-client-IP extraction behind proxies.

Pods, K8s ingress, AWS ALB, nginx, Cloudflare — none of them put the real
client IP on `request.client.host`.  They put it on `X-Forwarded-For`
(left-most non-private IP) or `X-Real-IP`.  This helper resolves the
real IP for all the call-sites that previously read `request.client.host`
directly (geo gate, audit log, analytics, lead-form dedupe, lobby join).
"""
from __future__ import annotations

import ipaddress
import logging
import os
from typing import Optional

from fastapi import Request

logger = logging.getLogger("bigfm.client_ip")

TRUSTED_PROXIES_ENABLED = (
    os.environ.get("TRUSTED_PROXIES_ENABLED", "true").lower()
    in {"1", "true", "yes", "on"})


def _is_private_or_loopback(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip.strip())
        return (ip_obj.is_private or ip_obj.is_loopback
                  or ip_obj.is_link_local or ip_obj.is_reserved)
    except ValueError:
        return True   # not a valid IP — skip


def get_real_client_ip(request: Request) -> Optional[str]:
    """Returns the best-guess real client IP.

    Order of preference:
      1. Left-most non-private IP in `X-Forwarded-For`
      2. `X-Real-IP`
      3. `request.client.host`
    If `TRUSTED_PROXIES_ENABLED` is False we skip XFF/X-Real-IP entirely
    (use direct connection only — for setups deployed without a proxy)."""
    if TRUSTED_PROXIES_ENABLED:
        xff = request.headers.get("x-forwarded-for") or ""
        if xff:
            # Take left-most non-private
            for raw in xff.split(","):
                ip = raw.strip()
                if ip and not _is_private_or_loopback(ip):
                    return ip
            # If everything was private, fall through to X-Real-IP
        xri = request.headers.get("x-real-ip")
        if xri and not _is_private_or_loopback(xri):
            return xri
    if request.client and request.client.host:
        return request.client.host
    return None
