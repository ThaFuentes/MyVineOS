# Fetch a small public-page preview (og:title / og:image) for compose + wall cards.
# Blocks private/loopback hosts so this cannot be used to probe the church LAN.

from __future__ import annotations

import html
import ipaddress
import re
import socket
import ssl
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from app.utils.appearance import sanitize_public_href
from app.utils.html_sanitize import sanitize_plain_text

_MAX_BYTES = 262144
_MAX_IMAGE = 400000
_TIMEOUT = 4
_UA = "MyVineChurchLinkPreview/1.0"
_URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+", re.I)


def looks_like_url(text: str | None) -> bool:
    t = (text or "").strip()
    return t.lower().startswith(("http://", "https://"))


def first_url_in(text: str | None) -> str:
    raw = (text or "").strip()
    if looks_like_url(raw):
        return raw.split()[0]
    m = _URL_IN_TEXT.search(raw)
    return m.group(0) if m else ""


def youtube_id(url: str) -> str:
    href = (url or "").strip()
    if "youtu.be/" in href:
        return href.split("youtu.be/")[1].split("?")[0].split("/")[0][:20]
    if "watch?v=" in href:
        return href.split("watch?v=")[1].split("&")[0][:20]
    if "youtube.com/embed/" in href:
        return href.split("youtube.com/embed/")[1].split("?")[0][:20]
    return ""


def _host_is_public(host: str) -> bool:
    name = (host or "").strip().strip("[]").split("%")[0].rstrip(".")
    if not name or name.lower() in ("localhost", "localhost.localdomain"):
        return False
    try:
        infos = socket.getaddrinfo(name, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except (TypeError, ValueError):
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
        if not ip.is_global:
            return False
    return True


def url_is_safe(url: str) -> bool:
    href = sanitize_public_href(url)
    if not href or href.startswith("/"):
        return False
    parsed = urlparse(href)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    if parsed.port not in (None, 80, 443):
        return False
    return _host_is_public(parsed.hostname)


class _OgParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        d = {str(k).lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            prop = (d.get("property") or d.get("name") or "").lower()
            content = d.get("content") or ""
            if prop in (
                "og:title",
                "twitter:title",
                "og:description",
                "twitter:description",
                "og:image",
                "og:image:url",
                "og:image:secure_url",
                "twitter:image",
                "twitter:image:src",
                "og:site_name",
            ):
                if content and prop not in self.meta:
                    self.meta[prop] = content
        if tag == "title":
            self._in_title = True

    def handle_data(self, data):
        if self._in_title:
            self.title += data

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not url_is_safe(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_link_preview(url: str) -> dict:
    """Return {url, title, description, image, host} or {}."""
    href = sanitize_public_href(url)
    if not url_is_safe(href):
        return {}
    parsed = urlparse(href)
    host = (parsed.hostname or "").lower()
    yid = youtube_id(href)
    if yid:
        return {
            "url": href[:500],
            "title": "YouTube",
            "description": "",
            "image": f"https://i.ytimg.com/vi/{yid}/hqdefault.jpg",
            "host": host,
        }
    try:
        req = urllib.request.Request(
            href,
            headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
            },
            method="GET",
        )
        opener = urllib.request.build_opener(_SafeRedirect())
        with opener.open(req, timeout=_TIMEOUT) as resp:
            final = resp.geturl() or href
            if not url_is_safe(final):
                return {}
            ctype = (resp.headers.get("Content-Type") or "").lower()
            raw = resp.read(_MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError, ssl.SSLError):
        return {"url": href[:500], "title": host, "description": "", "image": "", "host": host}
    if len(raw) > _MAX_BYTES:
        raw = raw[:_MAX_BYTES]
    if "html" not in ctype and not raw.lstrip()[:32].lower().startswith((b"<!doctype", b"<html", b"<head")):
        return {"url": href[:500], "title": host, "description": "", "image": "", "host": host}
    text = raw.decode("utf-8", errors="replace")
    parser = _OgParser()
    try:
        parser.feed(text)
    except Exception:
        pass
    title = sanitize_plain_text(
        parser.meta.get("og:title") or parser.meta.get("twitter:title") or parser.title or host
    )[:180]
    desc = sanitize_plain_text(
        parser.meta.get("og:description") or parser.meta.get("twitter:description") or ""
    )[:280]
    image_raw = (
        parser.meta.get("og:image:secure_url")
        or parser.meta.get("og:image")
        or parser.meta.get("og:image:url")
        or parser.meta.get("twitter:image")
        or parser.meta.get("twitter:image:src")
        or ""
    )
    image = ""
    if image_raw:
        abs_img = urljoin(final, html.unescape(image_raw).strip())
        if url_is_safe(abs_img):
            image = abs_img[:800]
    return {
        "url": href[:500],
        "title": title,
        "description": desc,
        "image": image,
        "host": host,
    }


def _sniff_image(raw: bytes) -> str:
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
        return "image/gif"
    if len(raw) > 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return ""


def fetch_link_image(url: str) -> tuple[bytes | None, str | None]:
    """Fetch a public og:image through us so the browser is not hotlink-blocked."""
    href = sanitize_public_href(url)
    if not url_is_safe(href):
        return None, None
    try:
        req = urllib.request.Request(
            href,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; MyVineChurchLinkPreview/1.0; "
                    "+https://myvineos.poweredby.top/)"
                ),
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
            method="GET",
        )
        opener = urllib.request.build_opener(_SafeRedirect())
        with opener.open(req, timeout=_TIMEOUT) as resp:
            final = resp.geturl() or href
            if not url_is_safe(final):
                return None, None
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            raw = resp.read(_MAX_IMAGE + 1)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError, ssl.SSLError):
        return None, None
    if not raw or len(raw) > _MAX_IMAGE:
        return None, None
    sniffed = _sniff_image(raw)
    if sniffed:
        return raw, sniffed
    if ctype.startswith("image/") and ctype not in ("image/svg+xml", "image/svg"):
        return raw, ctype
    return None, None
