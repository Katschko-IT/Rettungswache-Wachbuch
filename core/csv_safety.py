"""Gemeinsame Regel gegen Formel-Injektion in CSV-Dateien.

Tabellenprogramme führen Zellen, die mit ``=``, ``+``, ``-`` oder ``@`` (oder
einem Tabulator/Zeilenumbruch) beginnen, als Formel aus. Exporte stellen solchen
Werten ein Apostroph voran (``core/coffee_views.py``); der Stammdatenimport
(``core/masterdata_import.py``) weist sie zurück, damit über den Import kein
neuer Formelweg in die übrigen Exporte entsteht.
"""
from __future__ import annotations

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def starts_like_formula(text) -> bool:
    return str(text)[:1] in FORMULA_PREFIXES
