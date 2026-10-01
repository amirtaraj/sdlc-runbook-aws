"""Stage schemas live in runbook/RUNBOOK.md; this package only validates against them."""
from .validator import validate

__all__ = ["validate"]
