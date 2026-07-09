"""Fetchers generiques : chaque type de source declare dans sources.yaml
correspond a une fonction fetch_<type> qui renvoie une liste d'items normalises.

Item normalise :
{
  "id": str (stable, hash de l'url),
  "title": str,
  "url": str,
  "summary": str (texte brut source, peut etre vide),
  "published": str ISO,
  "source": str (name de la source),
  "source_label": str,
  "source_weight": int,
  "extra": dict (points HN, stars GitHub, upvotes HF...)
}
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timedelta, timezone

import feedparser
import requests

log = logging.getLogger("veille.fetch")

UA = {"User-Agent": "veille-ia/1.0 (personal research digest)"}


def _item_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def _clean(text: str, limit: int = 2000) -> str:
    import re

    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _base(src: dict, title: str, url: str, summary: str, published: str, extra: dict | None = None) -> dict:
    return {
        "id": _item_id(url),
        "title": _clean(title, 300),
        "url": url,
        "summary": _clean(summary),
        "published": published,
        "source": src["name"],
        "source_label": src.get("label", src["name"]),
        "source_weight": int(src.get("weight", 1)),
        "extra": extra or {},
    }


def fetch_rss(src: dict, since: datetime) -> list[dict]:
    feed = feedparser.parse(src["url"], request_headers=UA)
    items = []
    for e in feed.entries[:50]:
        ts = e.get("published_parsed") or e.get("updated_parsed")
        pub = datetime(*ts[:6], tzinfo=timezone.utc) if ts else datetime.now(timezone.utc)
        if pub < since:
            continue
        items.append(_base(src, e.get("title", ""), e.get("link", ""), e.get("summary", ""), pub.isoformat()))
    return items


def fetch_arxiv(src: dict, since: datetime) -> list[dict]:
    cats = " OR ".join(f"cat:{c}" for c in src.get("categories", ["cs.AI"]))
    params = {
        "search_query": cats,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": src.get("max_results", 50),
    }
    r = requests.get("https://export.arxiv.org/api/query", params=params, headers=UA, timeout=30)
    feed = feedparser.parse(r.text)
    items = []
    for e in feed.entries:
        ts = e.get("published_parsed")
        pub = datetime(*ts[:6], tzinfo=timezone.utc) if ts else datetime.now(timezone.utc)
        if pub < since:
            continue
        authors = ", ".join(a.name for a in e.get("authors", [])[:6])
        items.append(
            _base(src, e.get("title", ""), e.get("link", ""), e.get("summary", ""), pub.isoformat(), {"authors": authors})
        )
    return items


def fetch_hf_papers(src: dict, since: datetime) -> list[dict]:
    r = requests.get("https://huggingface.co/api/daily_papers", headers=UA, timeout=30)
    r.raise_for_status()
    items = []
    for entry in r.json()[:40]:
        paper = entry.get("paper", {})
        pid = paper.get("id", "")
        url = f"https://huggingface.co/papers/{pid}" if pid else entry.get("url", "")
        pub = entry.get("publishedAt") or datetime.now(timezone.utc).isoformat()
        items.append(
            _base(
                src,
                paper.get("title", entry.get("title", "")),
                url,
                paper.get("summary", ""),
                pub,
                {"upvotes": paper.get("upvotes", 0), "arxiv_id": pid},
            )
        )
    return items


def fetch_hackernews(src: dict, since: datetime) -> list[dict]:
    # l'API Algolia n'autorise plus le filtre numerique sur points: filtrage cote client.
    # Une requete par mot-cle (Algolia ne gere pas le OR dans query).
    queries = src.get("queries") or [src.get("query", "AI")]
    min_points = src.get("min_points", 50)
    hits: dict[str, dict] = {}
    for q in queries:
        params = {
            "query": q,
            "tags": "story",
            "numericFilters": f"created_at_i>{int(since.timestamp())}",
            "hitsPerPage": 100,
        }
        r = requests.get("https://hn.algolia.com/api/v1/search", params=params, headers=UA, timeout=30)
        r.raise_for_status()
        for h in r.json().get("hits", []):
            hits[h["objectID"]] = h
        time.sleep(0.5)
    items = []
    for h in hits.values():
        if (h.get("points") or 0) < min_points:
            continue
        url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
        items.append(
            _base(
                src,
                h.get("title", ""),
                url,
                "",
                h.get("created_at", ""),
                {"points": h.get("points", 0), "comments": h.get("num_comments", 0)},
            )
        )
    return items


def fetch_github_trending(src: dict, since: datetime) -> list[dict]:
    # l'API de recherche GitHub ne supporte pas OR entre qualifiers: une requete par topic
    created = (datetime.now(timezone.utc) - timedelta(days=src.get("days_back", 30))).strftime("%Y-%m-%d")
    repos: dict[int, dict] = {}
    for topic in src.get("topics", ["llm"]):
        q = f"topic:{topic} created:>{created} stars:>{src.get('min_stars', 100)}"
        r = requests.get(
            "https://api.github.com/search/repositories",
            params={"q": q, "sort": "stars", "order": "desc", "per_page": 15},
            headers={**UA, "Accept": "application/vnd.github+json"},
            timeout=30,
        )
        r.raise_for_status()
        for repo in r.json().get("items", []):
            repos[repo["id"]] = repo
        time.sleep(2)  # rate limit non authentifie: 10 req/min sur search
    items = []
    for repo in repos.values():
        items.append(
            _base(
                src,
                repo["full_name"],
                repo["html_url"],
                repo.get("description") or "",
                repo.get("created_at", ""),
                {"stars": repo.get("stargazers_count", 0), "language": repo.get("language")},
            )
        )
    return items


FETCHERS = {
    "rss": fetch_rss,
    "arxiv": fetch_arxiv,
    "hf_papers": fetch_hf_papers,
    "hackernews": fetch_hackernews,
    "github_trending": fetch_github_trending,
}


def fetch_all(sources: list[dict], since: datetime) -> list[dict]:
    all_items: list[dict] = []
    for src in sources:
        if not src.get("enabled", True):
            continue
        fn = FETCHERS.get(src["type"])
        if fn is None:
            log.warning("Type de source inconnu: %s (%s)", src["type"], src["name"])
            continue
        try:
            items = fn(src, since)
            log.info("%s: %d items", src["name"], len(items))
            all_items.extend(items)
        except Exception as e:  # une source en panne ne bloque pas le pipeline
            log.error("Echec source %s: %s", src["name"], e)
        time.sleep(1)
    # dedoublonnage par id
    seen: set[str] = set()
    unique = []
    for it in all_items:
        if it["id"] not in seen:
            seen.add(it["id"])
            unique.append(it)
    return unique
