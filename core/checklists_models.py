"""Checklisten-Modelle und Alias-Namen (0.28)."""
from __future__ import annotations

from .models import Checklist, ChecklistCompletion, ChecklistItem

ChecklistTemplate = Checklist
ChecklistRun = ChecklistCompletion

__all__ = [
    "Checklist",
    "ChecklistTemplate",
    "ChecklistItem",
    "ChecklistCompletion",
    "ChecklistRun",
]
