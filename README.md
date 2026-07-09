# Veille IA

Veille quotidienne automatisée sur l'IA : papiers de recherche, nouveaux modèles, outils et méthodes d'optimisation. Un pipeline Python collecte les sources, l'API Mistral filtre le bruit, score la pertinence et la fiabilité, rédige un digest en français et analyse en profondeur les items les plus importants. Le tout est publié sur un site statique via GitHub Pages.

## Architecture

```
sources.yaml          Declaration des sources, centres d'interet, reglages
pipeline/
  fetchers.py         Recuperation generique (rss, arxiv, hf_papers, hackernews, github_trending)
  mistral.py          Client API Mistral minimal
  analyze.py          Scoring, resumes, digest, analyses profondes
  run.py              Orchestrateur
site/
  index.html/css/js   Site statique (mobile-first, dark mode)
  data/               JSON generes par le pipeline (index.json + days/YYYY-MM-DD.json)
.github/workflows/
  veille.yml          Cron quotidien : pipeline -> commit des donnees -> deploiement Pages
```

## Ajouter une source

Ajouter un bloc dans `sources.yaml` :

```yaml
  - name: mon-blog
    label: Mon Blog
    type: rss
    url: https://exemple.com/feed.xml
    weight: 1        # bonus credibilite 0-2
    enabled: true
```

Types disponibles : `rss`, `arxiv`, `hf_papers`, `hackernews`, `github_trending`. Pour un nouveau type, ajouter une fonction `fetch_<type>` dans `pipeline/fetchers.py` et l'enregistrer dans le dict `FETCHERS`.

## Lancer en local

```bash
pip install -r requirements.txt

# Tester les sources sans consommer l'API Mistral
python -m pipeline.run --dry-run

# Pipeline complet
export MISTRAL_API_KEY=...
python -m pipeline.run

# Servir le site
python -m http.server 8000 -d site
```

## Déploiement (une seule fois)

1. Créer un dépôt GitHub et pousser ce projet sur `main`.
2. Dans **Settings > Secrets and variables > Actions**, ajouter le secret `MISTRAL_API_KEY`.
3. Dans **Settings > Pages**, choisir **Source : GitHub Actions**.
4. Lancer le workflow **Veille quotidienne** manuellement (onglet Actions) pour la première génération.

Ensuite le pipeline tourne chaque jour à 06h30 UTC et le site se met à jour tout seul.

## Réglages

Dans `sources.yaml`, section `settings` :

- `min_relevance` : seuil de pertinence (les items en dessous sont écartés)
- `max_items_per_day` : taille max du flux quotidien
- `deep_analysis_count` : nombre de tops items analysés en profondeur
- `scoring_model` / `writing_model` : modèles Mistral utilisés

La section `interests` pilote le scoring de pertinence : la modifier ajuste directement ce que Mistral considère comme important pour toi.
