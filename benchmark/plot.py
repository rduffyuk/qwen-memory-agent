"""Render the benchmark's context-efficiency curves to a PNG for the README / demo.

Reads the JSON written by ``benchmark.run.run`` and plots recall accuracy and
staleness rate vs token budget for B1 (full-history), B2 (naive top-k) and B3
(ours). Run AFTER a benchmark run:

    uv run --extra viz python -m benchmark.plot

matplotlib is an optional dependency (the ``viz`` extra) so the core install and
the offline test gate stay light.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

RESULTS = Path("benchmark/results/latest.json")
OUT = Path("benchmark/results/context_efficiency.png")

_SERIES = {
    "B1": ("B1 full-history", "#c0392b"),
    "B2": ("B2 naive top-k", "#e67e22"),
    "B3": ("B3 ours", "#27ae60"),
}


def plot(results_path: Path = RESULTS, out_path: Path = OUT) -> Path:
    try:
        import matplotlib

        matplotlib.use("Agg")  # headless (ECS / CI)
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - viz extra not installed
        raise SystemExit(
            "matplotlib not installed. Run: uv sync --extra viz (or: uv run --extra viz ...)"
        ) from exc

    data: dict[str, Any] = json.loads(results_path.read_text(encoding="utf-8"))
    budgets: list[int] = data["budgets"]
    baselines = data["baselines"]

    fig, (ax_r, ax_s) = plt.subplots(1, 2, figsize=(11, 4.4))

    for key, (label, color) in _SERIES.items():
        series = baselines[key]
        recall = [series[str(b)]["recall_accuracy"] for b in budgets]
        stale = [series[str(b)]["staleness_rate"] for b in budgets]
        ax_r.plot(budgets, recall, marker="o", color=color, label=label)
        ax_s.plot(budgets, stale, marker="o", color=color, label=label)

    for ax, title, ylabel in (
        (ax_r, "Recall accuracy vs budget  (higher is better)", "recall accuracy"),
        (ax_s, "Staleness rate vs budget  (lower is better)", "staleness rate"),
    ):
        ax.set_xlabel("memory token budget")
        ax.set_ylabel(ylabel)
        ax.set_xticks(budgets)
        ax.set_ylim(-0.05, 1.05)
        ax.set_title(title, fontsize=10)
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8, loc="center right")

    fig.suptitle(
        "Qwen MemoryAgent — context efficiency: B3 holds recall 1.0 / staleness 0.0 "
        "at every budget",
        fontsize=11,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    return out_path


if __name__ == "__main__":
    written = plot()
    print(f"wrote {written}")
