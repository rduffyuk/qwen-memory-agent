"""Render the active-use eval results to a PNG for the README / demo.

Reads the live-run summary written by ``scripts/active_use_live.py`` (and the
passive-recall reference from the offline benchmark) and plots the headline:
passive recall saturates at 1.0 while active use lands at 0.60. Run AFTER a
live run:

    uv run --extra viz python -m benchmark.plot_active_use

matplotlib is an optional dependency (the ``viz`` extra) so the core install and
the offline test gate stay light.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ACTIVE = Path("benchmark/results/active_use.json")
PASSIVE = Path("benchmark/results/latest.json")
OUT = Path("benchmark/results/active_use.png")

GREEN = "#27ae60"
ORANGE = "#e67e22"
RED = "#c0392b"
GREY = "#7f8c8d"


def plot(active_path: Path = ACTIVE, passive_path: Path = PASSIVE, out_path: Path = OUT) -> Path:
    try:
        import matplotlib

        matplotlib.use("Agg")  # headless (ECS / CI)
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - viz extra not installed
        raise SystemExit(
            "matplotlib not installed. Run: uv sync --extra viz (or: uv run --extra viz ...)"
        ) from exc

    active: dict[str, Any] = json.loads(active_path.read_text(encoding="utf-8"))
    agg = active["aggregate"]
    passive: dict[str, Any] = json.loads(passive_path.read_text(encoding="utf-8"))
    largest_budget = str(max(passive["budgets"]))
    passive_recall = passive["baselines"]["B3"][largest_budget]["recall_accuracy"]

    fig, (ax_gap, ax_depth) = plt.subplots(1, 2, figsize=(11, 4.4))

    # ---- left: the gap - passive recall vs the three active-use oracles ----
    labels = [
        "passive recall\n(retrieval)",
        "outcome",
        "store",
        "process",
        "task success\n(all three)",
    ]
    values = [
        passive_recall,
        agg["outcome_pass_rate"],
        agg["store_pass_rate"],
        agg["process_pass_rate"],
        agg["task_success_rate"],
    ]
    colors = [GREY, GREEN, GREEN, ORANGE, RED]
    bars = ax_gap.bar(labels, values, color=colors)
    for bar, value in zip(bars, values):
        ax_gap.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.03,
            f"{value:.2f}",
            ha="center",
            fontsize=9,
            fontweight="bold",
        )
    ax_gap.set_ylim(0, 1.12)
    ax_gap.set_ylabel("pass rate")
    ax_gap.set_title(
        "Passive recall vs active use  (live ECS run, real Qwen)",
        fontsize=10,
    )
    ax_gap.tick_params(axis="x", labelsize=8.5)
    ax_gap.grid(True, axis="y", alpha=0.25)

    # ---- right: task success by dependency depth ----
    depths = sorted(agg["by_depth"])
    depth_vals = [agg["by_depth"][d]["task_success"] for d in depths]
    depth_ns = [agg["by_depth"][d]["n"] for d in depths]
    bars = ax_depth.bar([f"depth {d}" for d in depths], depth_vals, color=ORANGE, width=0.55)
    for bar, value, n in zip(bars, depth_vals, depth_ns):
        ax_depth.text(
            bar.get_x() + bar.get_width() / 2,
            value + 0.03,
            f"{value:.2f}\n(n={n})",
            ha="center",
            fontsize=9,
        )
    ax_depth.axhline(agg["task_success_rate"], color=RED, linestyle="--", linewidth=1, alpha=0.7)
    ax_depth.text(
        -0.4,
        agg["task_success_rate"] - 0.09,
        f"overall {agg['task_success_rate']:.2f}",
        fontsize=8,
        color=RED,
    )
    ax_depth.set_ylim(0, 1.12)
    ax_depth.set_ylabel("task success")
    ax_depth.set_title(
        "Task success by dependency depth  (constraints per decision)",
        fontsize=10,
    )
    ax_depth.grid(True, axis="y", alpha=0.25)

    fig.suptitle(
        "Qwen MemoryAgent — the passive/active gap: recall 1.00, task success "
        f"{agg['task_success_rate']:.2f} ({active['provenance']})",
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
