import re


def estimate_to_hours(estimate: str) -> float | None:
    """'4h' -> 4, '2d' / '2 days' -> 16, '1.5d' -> 12. None if unparseable."""
    match = re.match(r"\s*(\d+(?:\.\d+)?)\s*(h|hr|hrs|hours?|d|days?)\b", estimate.lower())
    if not match:
        return None
    value, unit = float(match.group(1)), match.group(2)
    return value if unit.startswith("h") else value * 8
