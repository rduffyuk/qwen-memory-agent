"""Render the benchmark's context-efficiency curve to a PNG for the README / demo.

Reads the JSON written by ``benchmark.run.run`` and plots B3 (ours) accuracy and
staleness across token budgets, with B1 (full-history) and B2 (naive top-k) as
reference lines. Run AFTER a live benchmark:

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

    b3 = baselines["B3"]
    b3_recall = [b3[str(b)]["recall_accuracy"] for b in budgets]
    b3_stale = [b3[str(b)]["staleness_rate"] for b in budgets]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(budgets, b3_recall, marker="o", label="B3 ours — recall accuracy")
    ax.plot(budgets, b3_stale, marker="o", linestyle="--", label="B3 ours — staleness rate")

    # reference lines for the stateless baselines (budget-independent)
    for name, style in (("B1", ":"), ("B2", "-.")):
        if name in baselines and "recall_accuracy" in baselines[name]:
            ax.axhline(
                baselines[name]["recall_accuracy"],
                linestyle=style,
                alpha=0.6,
                label=f"{name} recall (no budget control)",
            )

    ax.set_xlabel("memory token budget")
    ax.set_ylabel("rate")
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("Context-efficiency: accuracy & staleness vs token budget")
    ax.legend(fontsize=8)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    return out_path


if __name__ == "__main__":
    written = plot()
    print(f"wrote {written}")
