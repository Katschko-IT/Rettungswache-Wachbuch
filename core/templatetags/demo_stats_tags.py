"""Demo-Kennzahlen als Karte im Feedback-Posteingang (core/demo_stats.py)."""
from django import template

from core.demo_stats import operator_summary

register = template.Library()


@register.inclusion_tag("core/_demo_stats_card.html")
def demo_stats_card():
    return {"stats": operator_summary()}
