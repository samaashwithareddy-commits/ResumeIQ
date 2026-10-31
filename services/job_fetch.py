"""SSRF-safe retrieval of publicly accessible job-description pages.

Only http/https is allowed, hostnames are resolved and checked against private
ranges, redirects are followed manually (each hop re-validated), responses are
size-limited and only HTML/plain text is parsed. If a page needs JavaScript or a
login the caller is told to paste the description instead.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from html.parser import HTMLParser
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests

MAX_BYTES = 2_000_000
TIMEOUT = 12
MAX_REDIRECTS = 3
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml+xml")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 ResumeIQ/1.0"
)
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "host.docker.internal",
}


class FetchError(Exception):
    """Raised with a user-facing explanation when retrieval is not possible."""


class _TextExtractor(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "svg", "iframe", "template", "head", "nav", "footer", "aside", "form"}
    BLOCK_TAGS = {
        "p", "div", "section", "article", "br", "li", "ul", "ol", "tr", "h1", "h2", "h3",
        "h4", "h5", "h6", "header", "main", "table", "td", "th",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: D401 - HTMLParser API
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        if tag in self.BLOCK_TAGS and self.skip_depth == 0:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1
        if tag in self.BLOCK_TAGS and self.skip_depth == 0:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
            return
        if self.skip_depth:
            return
        text = data.strip()
        if text:
            self.parts.append(text + " ")


def _clean_text(raw: str) -> str:
    lines = []
    for line in raw.splitlines():
        line = re.sub(r"[ \t\u00a0]+", " ", line).strip()
        if line:
            lines.append(line)
    # Collapse consecutive duplicates produced by nested markup.
    deduped: list[str] = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
    return "\n".join(deduped)


def _resolve_public_ip(hostname: str) -> str:
    if hostname.lower() in BLOCKED_HOSTNAMES:
        raise FetchError("That host is not allowed. Use a public job page instead.")
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise FetchError("Could not resolve that hostname. Check the URL and try again.") from exc

    addresses = {info[4][0] for info in infos}
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise FetchError("The URL resolved to an invalid address.") from exc
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise FetchError("That URL points to a private or internal address, which is blocked for safety.")
    return sorted(addresses)[0]


def validate_public_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise FetchError("Enter a job posting URL first.")
    if len(url) > 500:
        raise FetchError("That URL is too long.")
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise FetchError("Only http:// and https:// links can be fetched.")
    if parsed.username or parsed.password:
        raise FetchError("URLs with embedded credentials are not allowed.")
    if not parsed.hostname:
        raise FetchError("That URL is missing a hostname.")
    if parsed.port and parsed.port not in (80, 443):
        raise FetchError("Only standard web ports (80/443) are allowed.")
    _resolve_public_ip(parsed.hostname)
    return url


def fetch_job_description(url: str) -> dict:
    """Download and extract readable text from a public job page."""
    current = validate_public_url(url)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
        "Accept-Language": "en-US,en;q=0.8",
    }

    for _ in range(MAX_REDIRECTS + 1):
        try:
            response = requests.get(
                current,
                headers=headers,
                timeout=TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
        except requests.RequestException as exc:
            raise FetchError(
                "The page could not be reached. The site may block automated requests — "
                "open the link in your browser and paste the description instead."
            ) from exc

        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location", "")
            response.close()
            if not location:
                raise FetchError("The site returned a redirect without a destination. Paste the description instead.")
            current = validate_public_url(urljoin(current, location))
            continue

        if response.status_code in (401, 403):
            response.close()
            raise FetchError(
                "The site refused automated access (HTTP 401/403). Open the page in your browser "
                "and paste the description instead."
            )
        if response.status_code >= 400:
            response.close()
            raise FetchError(
                f"The page returned HTTP {response.status_code}. Paste the job description text instead."
            )

        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if content_type and not content_type.startswith(ALLOWED_CONTENT_TYPES):
            response.close()
            raise FetchError(
                "That link is not an HTML page (it may be a PDF or a file). Open it and paste the text instead."
            )

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=65_536):
            total += len(chunk)
            if total > MAX_BYTES:
                response.close()
                raise FetchError("The page is larger than 2 MB. Paste the relevant description text instead.")
            chunks.append(chunk)
        response.close()

        encoding = response.encoding or "utf-8"
        try:
            html = b"".join(chunks).decode(encoding, errors="replace")
        except (LookupError, UnicodeDecodeError):
            html = b"".join(chunks).decode("utf-8", errors="replace")

        if content_type == "text/plain":
            text = _clean_text(html)
            title = ""
        else:
            parser_instance = _TextExtractor()
            parser_instance.feed(html)
            text = _clean_text("".join(parser_instance.parts))
            title = _clean_text(" ".join(parser_instance.title_parts))

        if len(text) < 250:
            raise FetchError(
                "The page returned almost no readable text — it probably needs JavaScript rendering, "
                "or the posting has expired. Paste the description instead."
            )

        return {
            "text": text[:18_000],
            "final_url": current,
            "page_title": title[:200],
            "truncated": len(text) > 18_000,
        }

    raise FetchError("Too many redirects. Open the link in your browser and paste the description instead.")
