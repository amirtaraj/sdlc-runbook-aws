"""Structured dataset: historical estimate-vs-actual effort by task category.

Summarised per category and given to the Tasks agent so its estimates reflect how
long similar work has actually taken.
"""
import csv
from pathlib import Path
from statistics import median


class EstimationBaseline:
    def __init__(self, csv_path: Path):
        self._rows = self._load(csv_path)

    @staticmethod
    def _load(path: Path) -> list[dict]:
        if not path.is_file():
            return []
        with path.open(newline="", encoding="utf-8") as f:
            return [
                {"category": r["category"].strip(), "estimate": float(r["estimate_days"]), "actual": float(r["actual_days"])}
                for r in csv.DictReader(f)
            ]

    def summary(self) -> list[dict]:
        """One row per category: sample size, median actual days, average overrun vs estimate."""
        result = []
        for category in sorted({r["category"] for r in self._rows}):
            rows = [r for r in self._rows if r["category"] == category]
            overrun = sum(r["actual"] for r in rows) / sum(r["estimate"] for r in rows) - 1
            result.append({
                "category": category,
                "sample_size": len(rows),
                "median_actual_days": round(median(r["actual"] for r in rows), 2),
                "average_overrun_pct": round(overrun * 100),
            })
        return result
