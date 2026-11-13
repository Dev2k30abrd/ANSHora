"""SSRF protection for user-supplied URLs (imports, webhooks)."""
import ipaddress
import socket
from urllib.parse import urlparse

from app.core.config import ALLOW_PRIVATE_URLS


def assert_public_url(url: str, allow_http: bool = False) -> str:
    u = urlparse(url)
    if u.scheme not in (("https", "http") if allow_http else ("https",)):
        raise ValueError("Only https:// URLs are allowed." if not allow_http else "Only http(s) URLs are allowed.")
    if not u.hostname:
        raise ValueError("Invalid URL.")
    if ALLOW_PRIVATE_URLS:
        return url
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80))
    except socket.gaierror:
        raise ValueError("Could not resolve host.")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("URLs pointing to private/internal addresses are blocked.")
    return url
