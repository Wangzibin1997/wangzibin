import re
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from readability import Document


@dataclass
class NewsItem:
    url: str
    title: str
    text: str
    fetched_at: float


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def _is_allowed(url: str, allow_domains: set[str]) -> bool:
    d = _domain(url)
    if d.startswith("www."):
        d = d[4:]
    return d in allow_domains


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # Basic prompt-injection hardening: strip common instruction patterns.
    text = re.sub(r"(?i)\b(ignore|disregard)\b.{0,80}\b(instructions|previous)\b", "", text)
    text = re.sub(r"(?i)\b(system prompt|developer message|tool instructions)\b", "", text)
    return text.strip()


def fetch_article(url: str, *, allow_domains: set[str], timeout_s: float = 15.0) -> NewsItem | None:
    if not _is_allowed(url, allow_domains):
        return None

    with httpx.Client(follow_redirects=True, timeout=timeout_s, headers={"User-Agent": "okx-trading-agent/1.0"}) as client:
        r = client.get(url)
        r.raise_for_status()
        html = r.text

    doc = Document(html)
    title = doc.short_title() or ""
    content_html = doc.summary(html_partial=True)

    soup = BeautifulSoup(content_html, "lxml")
    text = soup.get_text(" ", strip=True)

    return NewsItem(url=url, title=_clean_text(title), text=_clean_text(text), fetched_at=time.time())


def summarize_for_trading(item: NewsItem, *, max_chars: int = 2000) -> str:
    # No LLM here yet (that comes later). This is a safe extractive summary.
    t = item.text
    if len(t) > max_chars:
        t = t[:max_chars] + "…"
    return f"Title: {item.title}\nURL: {item.url}\nContent: {t}"


def fetch_and_summarize(urls: Iterable[str], allow_domains: Iterable[str]) -> list[str]:
    allow = {d.lower().lstrip("www.") for d in allow_domains}
    out: list[str] = []
    for u in urls:
        it = fetch_article(u, allow_domains=allow)
        if it:
            out.append(summarize_for_trading(it))
    return out
