"""Orchestrateur du pipeline de veille.

Usage:
    python -m pipeline.run [--date YYYY-MM-DD] [--hours 24] [--dry-run]

--dry-run : fetch uniquement, sans appel Mistral (pour tester les sources).
Sortie: site/data/days/<date>.json + site/data/index.json mis a jour.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .fetchers import fetch_all

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "site" / "data"

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("veille")


def load_config() -> dict:
    with open(ROOT / "sources.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen_ids(days: int = 14) -> set[str]:
    """Ids deja publies recemment, pour ne pas re-presenter les memes items."""
    seen: set[str] = set()
    days_dir = DATA_DIR / "days"
    if not days_dir.exists():
        return seen
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for f in days_dir.glob("*.json"):
        try:
            if datetime.strptime(f.stem, "%Y-%m-%d").replace(tzinfo=timezone.utc) < cutoff:
                continue
            data = json.loads(f.read_text(encoding="utf-8"))
            seen.update(it["id"] for it in data.get("items", []))
        except Exception:
            continue
    return seen


def update_index(date: str, day_data: dict) -> None:
    index_path = DATA_DIR / "index.json"
    index = {"days": []}
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    index["days"] = [d for d in index.get("days", []) if d["date"] != date]
    index["days"].append(
        {
            "date": date,
            "count": len(day_data["items"]),
            "headline": day_data.get("digest", {}).get("headline", ""),
        }
    )
    index["days"].sort(key=lambda d: d["date"], reverse=True)
    index["generated_at"] = datetime.now(timezone.utc).isoformat()
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--hours", type=int, default=26, help="fenetre de fraicheur des items")
    parser.add_argument("--dry-run", action="store_true", help="fetch seulement, sans Mistral")
    args = parser.parse_args()

    config = load_config()
    settings = config.get("settings", {})
    since = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    log.info("Fetch des sources (depuis %s)...", since.isoformat())
    items = fetch_all(config["sources"], since)
    seen = load_seen_ids()
    items = [it for it in items if it["id"] not in seen]
    log.info("%d items frais apres dedoublonnage", len(items))

    if args.dry_run:
        print(json.dumps(items[:5], ensure_ascii=False, indent=2))
        print(f"\nTotal: {len(items)} items (dry-run, pas d'appel Mistral)")
        return

    from .analyze import deep_analysis, score_items, write_digest
    from .mistral import MistralClient

    client = MistralClient()
    scoring_model = settings.get("scoring_model", "mistral-small-latest")
    writing_model = settings.get("writing_model", "mistral-large-latest")

    log.info("Scoring par Mistral (%s)...", scoring_model)
    scored = score_items(client, scoring_model, items, config.get("interests", []))

    min_rel = settings.get("min_relevance", 5)
    kept = [it for it in scored if it["relevance"] >= min_rel]
    kept.sort(key=lambda it: it["score"], reverse=True)
    kept = kept[: settings.get("max_items_per_day", 30)]
    log.info("%d items retenus (seuil pertinence %d)", len(kept), min_rel)

    digest = {}
    if kept:
        log.info("Redaction du digest (%s)...", writing_model)
        try:
            digest = write_digest(client, writing_model, kept, args.date)
        except Exception as e:
            log.error("Echec digest: %s", e)

    n_deep = settings.get("deep_analysis_count", 4)
    for it in kept[:n_deep]:
        log.info("Analyse profonde: %s", it["title"][:60])
        try:
            it["deep_analysis"] = deep_analysis(client, writing_model, it)
        except Exception as e:
            log.error("Echec analyse profonde: %s", e)

    day_data = {"date": args.date, "digest": digest, "items": kept}
    days_dir = DATA_DIR / "days"
    days_dir.mkdir(parents=True, exist_ok=True)
    out = days_dir / f"{args.date}.json"
    out.write_text(json.dumps(day_data, ensure_ascii=False, indent=1), encoding="utf-8")
    update_index(args.date, day_data)
    log.info("Ecrit: %s", out)


if __name__ == "__main__":
    main()
