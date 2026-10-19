"""
Offline-Produkthilfe für Django 5.
Lädt Artikel aus einem JSON-Artefakt und stellt Such- und Abruffunktionen bereit.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

__all__ = [
    "HelpArticle",
    "HelpContentError",
    "get_articles",
    "get_article",
    "search",
    "manifest_revision",
    "reload",
]

class HelpContentError(RuntimeError):
    """Fehler im Hilfsinhaltsformat."""

class _Section(NamedTuple):
    heading: str
    body: str

@dataclass(frozen=True, slots=True)
class HelpArticle:
    """Ein Hilfsartikel in einer bestimmten Sprache."""

    slug: str
    language: str
    title: str
    summary: str
    revision: str
    source: str
    sections: tuple[_Section, ...] = field(repr=False)

    @property
    def plain_text(self) -> str:
        """Volltext des Artikels für Suche."""
        parts = [self.title, self.summary]
        for sec in self.sections:
            parts.append(sec.heading)
            parts.append(sec.body)
        return "\n".join(parts)

def _validate_article(data: dict, seen: set[tuple[str, str]]) -> HelpArticle:
    slug = data.get("slug")
    if not isinstance(slug, str) or not _SLUG_PATTERN.fullmatch(slug):
        raise HelpContentError(f"Ungültiger Slug: {slug!r}")
    language = data.get("language")
    if language not in _LANGUAGES:
        raise HelpContentError(f"Ungültige Sprache: {language!r} (Slug: {slug!r})")
    if (slug, language) in seen:
        raise HelpContentError(f"Doppelter Slug/Sprache: {slug!r}/{language!r}")
    seen.add((slug, language))

    title = data.get("title")
    if not isinstance(title, str) or not title.strip():
        raise HelpContentError(f"Leerer Titel (Slug: {slug!r})")
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise HelpContentError(f"Leere Zusammenfassung (Slug: {slug!r})")

    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        raise HelpContentError(f"Leere Abschnitte (Slug: {slug!r})")
    sec_tuples = []
    for sec in sections:
        if not isinstance(sec, dict):
            raise HelpContentError(f"Ungültiger Abschnitt (Slug: {slug!r})")
        heading = sec.get("heading", "")
        body = sec.get("body", "")
        if not isinstance(heading, str) or not isinstance(body, str) or not heading.strip() or not body.strip():
            raise HelpContentError(f"Ungültiger Abschnittstext (Slug: {slug!r})")
        sec_tuples.append(_Section(heading, body))

    return HelpArticle(
        slug=slug,
        language=language,
        title=title.strip(),
        summary=summary.strip(),
        revision=str(data.get("revision", "")),
        source=str(data.get("source", "")),
        sections=tuple(sec_tuples),
    )

def _load_data(path: Path | None = None) -> tuple[str, list[HelpArticle]]:
    if path is None:
        path = Path(__file__).parent / "help_data" / "articles.json"
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise HelpContentError("Hilfsdaten konnten nicht geladen werden") from e

    if not isinstance(data, dict):
        raise HelpContentError("Ungültiges Wurzelobjekt in Hilfsdaten")
    manifest_rev = data.get("manifest_revision")
    if not isinstance(manifest_rev, str):
        raise HelpContentError("Fehlende oder ungültige Manifest-Revision")

    articles = data.get("articles", [])
    if not isinstance(articles, list):
        raise HelpContentError("Ungültige Artikel-Liste")

    seen = set()
    validated = []
    for art in articles:
        if not isinstance(art, dict):
            raise HelpContentError("Ungültiger Artikel")
        validated.append(_validate_article(art, seen))

    return manifest_rev, validated

_LANGUAGES = frozenset({"de", "en"})
_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")

_override_path: Path | None = None

@lru_cache(maxsize=1)
def _get_data() -> tuple[str, list[HelpArticle]]:
    return _load_data(_override_path)

def reload(path: Path | None = None) -> None:
    """Cache leeren und optional ein Testartefakt setzen (nur fuer Tests)."""
    global _override_path
    _override_path = path
    _get_data.cache_clear()
    _get_data()

def manifest_revision() -> str:
    """Manifest-Revision der Hilfsdaten."""
    rev, _ = _get_data()
    return rev

def get_articles(language: str) -> list[HelpArticle]:
    """Alle Artikel in der angegebenen Sprache, sortiert nach Slug."""
    if language not in _LANGUAGES:
        return []
    _, articles = _get_data()
    return sorted((a for a in articles if a.language == language), key=lambda a: a.slug)

def get_article(slug: str, language: str) -> HelpArticle | None:
    """Artikel mit dem gegebenen Slug und Sprache oder None."""
    if language not in _LANGUAGES:
        return None
    _, articles = _get_data()
    for a in articles:
        if a.slug == slug and a.language == language:
            return a
    return None

def search(query: str, language: str, limit: int = 20) -> list[HelpArticle]:
    """Artikel durchsuchen (Volltext, case-insensitive)."""
    if not query:
        return []
    query = query.strip()[:120].casefold()
    if not query or language not in _LANGUAGES:
        return []

    _, articles = _get_data()
    candidates = []
    for art in articles:
        if art.language != language:
            continue
        text = art.plain_text.casefold()
        if query not in text:
            continue
        # Ranking: Titel > Zusammenfassung > Abschnitte
        rank = 0
        if query in art.title.casefold():
            rank = 3
        elif query in art.summary.casefold():
            rank = 2
        else:
            for sec in art.sections:
                if query in sec.heading.casefold() or query in sec.body.casefold():
                    rank = 1
                    break
        candidates.append((-rank, art.slug, art))

    candidates.sort()
    return [art for _, _, art in candidates[: max(1, min(limit, 50))]]