"""Analyse des items par Mistral : scoring pertinence/fiabilite, tags, resumes,
digest du jour et analyses profondes des tops items."""

from __future__ import annotations

import json
import logging

from .mistral import MistralClient

log = logging.getLogger("veille.analyze")

BATCH_SIZE = 10

TAGS = [
    "optimisation",
    "llm",
    "agents",
    "rag",
    "architecture",
    "interpretabilite",
    "vision",
    "audio",
    "robotique",
    "produit",
    "regulation",
    "outils",
    "benchmark",
    "autre",
]


def score_items(client: MistralClient, model: str, items: list[dict], interests: list[str]) -> list[dict]:
    """Score chaque item (pertinence, fiabilite, tags, resume court FR) par lots."""
    scored: list[dict] = []
    interests_txt = "\n".join(f"- {i}" for i in interests)
    for i in range(0, len(items), BATCH_SIZE):
        batch = items[i : i + BATCH_SIZE]
        listing = "\n\n".join(
            f"[{j}] TITRE: {it['title']}\nSOURCE: {it['source_label']} (poids credibilite {it['source_weight']}/2)\n"
            f"SIGNAUX: {json.dumps(it['extra'], ensure_ascii=False)}\nCONTENU: {it['summary'][:1200] or '(pas de resume)'}"
            for j, it in enumerate(batch)
        )
        prompt = f"""Tu es un analyste de veille IA exigeant. Voici les centres d'interet de l'utilisateur:
{interests_txt}

Pour chaque item ci-dessous, evalue:
- relevance (0-10): pertinence par rapport aux centres d'interet. Penalise le contenu marketing creux, les listicles, le garbage.
- reliability (0-10): fiabilite/serieux (papier peer-reviewed ou arXiv solide, gros labo, signaux communautaires forts = eleve; blog inconnu, claims extraordinaires sans preuve = bas).
- tags: 1-3 tags parmi {json.dumps(TAGS)}.
- tldr: resume en francais, 1-2 phrases, factuel et dense (ce que c'est + pourquoi c'est interessant).

Items:
{listing}

Reponds en JSON: {{"items": [{{"index": 0, "relevance": 7, "reliability": 8, "tags": ["llm"], "tldr": "..."}}, ...]}}"""
        try:
            result = client.chat_json(model, [{"role": "user", "content": prompt}])
            for entry in result.get("items", []):
                idx = entry.get("index")
                if idx is None or not (0 <= idx < len(batch)):
                    continue
                it = dict(batch[idx])
                it["relevance"] = min(10, max(0, int(entry.get("relevance", 0))))
                it["reliability"] = min(10, max(0, int(entry.get("reliability", 0))))
                it["tags"] = [t for t in entry.get("tags", []) if t in TAGS] or ["autre"]
                it["tldr"] = str(entry.get("tldr", ""))[:600]
                # score global: pertinence dominante, fiabilite et poids source en appui
                it["score"] = round(it["relevance"] * 0.6 + it["reliability"] * 0.3 + it["source_weight"] * 0.5, 1)
                scored.append(it)
        except Exception as e:
            log.error("Echec scoring lot %d: %s", i // BATCH_SIZE, e)
        log.info("Scoring: %d/%d", min(i + BATCH_SIZE, len(items)), len(items))
    return scored


def write_digest(client: MistralClient, model: str, items: list[dict], date: str) -> dict:
    """Redige le digest du jour a partir des items retenus."""
    listing = "\n\n".join(
        f"- [{it['source_label']}] {it['title']} (pertinence {it['relevance']}/10, fiabilite {it['reliability']}/10, tags: {', '.join(it['tags'])})\n  {it['tldr']}"
        for it in items[:20]
    )
    prompt = f"""Tu rediges la veille IA quotidienne du {date} pour un lecteur technique (etudiant/ingenieur IA).
Voici les items retenus aujourd'hui:

{listing}

Redige en francais:
- headline: une phrase qui capture l'info du jour la plus importante.
- overview: 2-3 phrases de mise en contexte de la journee.
- highlights: 3-6 points, chacun avec "title" (court) et "text" (2-4 phrases expliquant l'essentiel et pourquoi c'est important). Couvre les items les plus significatifs, regroupe ceux qui se recoupent.
- trend: 1-2 phrases sur la tendance de fond que suggerent ces nouvelles.

Ton: direct, technique, sans hype. Pas de superlatifs vides.
JSON: {{"headline": "...", "overview": "...", "highlights": [{{"title": "...", "text": "..."}}], "trend": "..."}}"""
    return client.chat_json(model, [{"role": "user", "content": prompt}], temperature=0.4)


def deep_analysis(client: MistralClient, model: str, item: dict) -> dict:
    """Analyse detaillee d'un item (pre-generee pour les tops du jour)."""
    prompt = f"""Analyse en profondeur cette publication IA pour un lecteur technique francophone.

TITRE: {item['title']}
SOURCE: {item['source_label']}
URL: {item['url']}
CONTENU DISPONIBLE: {item['summary'][:4000] or item['tldr']}

Redige en francais, en JSON:
{{
  "probleme": "quel probleme c'est cense resoudre (2-3 phrases)",
  "methode": "l'approche/methode, avec les details techniques disponibles (3-6 phrases)",
  "resultats": "resultats et chiffres cles si disponibles (2-4 phrases)",
  "limites": "limites, zones d'ombre, ce qui merite scepticisme (2-3 phrases)",
  "verdict": "pourquoi (ou pas) y preter attention, en une phrase directe"
}}
Si le contenu disponible est trop mince pour une section, dis-le honnetement plutot que d'inventer."""
    return client.chat_json(model, [{"role": "user", "content": prompt}], temperature=0.3)
