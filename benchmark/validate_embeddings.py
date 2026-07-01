from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is a runtime convenience
    pass

from memory_agent.qwen import DEFAULT_EMBED_MODEL, QwenClient

OUT = Path("docs/embedding-validation.md")
SUPERSEDE_THRESHOLD = 0.9


@dataclass(frozen=True)
class ValidationCase:
    label: str
    anchor: str
    replacement: str
    distractor: str


CASES = [
    ValidationCase(
        label="Ryan morning drink",
        anchor="Ryan prefers coffee in the morning.",
        replacement="Ryan now prefers tea in the morning.",
        distractor="Ryan uses Python for prototypes.",
    ),
    ValidationCase(
        label="Priya commute",
        anchor="Priya usually commutes by bus.",
        replacement="Priya now commutes by train.",
        distractor="Priya uses Postgres for local databases.",
    ),
    ValidationCase(
        label="Alex cloud provider",
        anchor="Alex deploys prototypes on AWS.",
        replacement="Alex now deploys prototypes on Alibaba Cloud.",
        distractor="Alex writes tests with pytest.",
    ),
    ValidationCase(
        label="Jordan breakfast",
        anchor="Jordan eats oatmeal for breakfast.",
        replacement="Jordan now eats yogurt for breakfast.",
        distractor="Jordan keeps notes in UTC.",
    ),
]


def run(out_path: Path = OUT) -> dict[str, object]:
    client = QwenClient()
    rows = []
    for case in CASES:
        anchor = client.embed(case.anchor)
        replacement = client.embed(case.replacement)
        distractor = client.embed(case.distractor)
        rows.append(
            {
                "label": case.label,
                "anchor": case.anchor,
                "replacement": case.replacement,
                "distractor": case.distractor,
                "replacement_cosine": _cosine(anchor, replacement),
                "distractor_cosine": _cosine(anchor, distractor),
            }
        )

    replacement_values = [float(row["replacement_cosine"]) for row in rows]
    distractor_values = [float(row["distractor_cosine"]) for row in rows]
    summary = {
        "model": DEFAULT_EMBED_MODEL,
        "threshold": SUPERSEDE_THRESHOLD,
        "replacement_min": min(replacement_values),
        "replacement_mean": sum(replacement_values) / len(replacement_values),
        "distractor_max": max(distractor_values),
        "distractor_mean": sum(distractor_values) / len(distractor_values),
        "rows": rows,
    }
    out_path.write_text(_render_markdown(summary), encoding="utf-8")
    return summary


def _cosine(left: list[float], right: list[float]) -> float:
    left_arr = np.array(left, dtype=float)
    right_arr = np.array(right, dtype=float)
    left_norm = np.linalg.norm(left_arr)
    right_norm = np.linalg.norm(right_arr)
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return float(np.dot(left_arr, right_arr) / (left_norm * right_norm))


def _render_markdown(summary: dict[str, object]) -> str:
    rows = list(summary["rows"])  # type: ignore[arg-type]
    replacement_min = float(summary["replacement_min"])
    distractor_max = float(summary["distractor_max"])
    if replacement_min >= SUPERSEDE_THRESHOLD:
        threshold_note = (
            f"The lowest supersession-pair cosine is {replacement_min:.3f}, above the "
            f"{SUPERSEDE_THRESHOLD:.2f} default, so the current threshold is empirically "
            "supported by this live sample."
        )
    else:
        threshold_note = (
            f"The lowest supersession-pair cosine is {replacement_min:.3f}, below the "
            f"{SUPERSEDE_THRESHOLD:.2f} default. This contradicts the threshold on this "
            "live sample; the default is left unchanged and should be revisited with a "
            "larger validation set."
        )

    lines = [
        "# Embedding Threshold Validation",
        "",
        f"Model: `{summary['model']}` via DashScope live embeddings.",
        f"Supersession threshold under review: `{SUPERSEDE_THRESHOLD:.2f}`.",
        "",
        "This is a one-shot live validation of semantic supersession pairs against unrelated "
        "same-person distractors. It is separate from the offline benchmark, which uses a "
        "deterministic keyword embedder to test ranking and budget-packing logic without model "
        "or network variance.",
        "",
        "| Case | Supersession pair | Pair cosine | Distractor | Distractor cosine |",
        "|---|---|---:|---|---:|",
    ]
    for row in rows:
        lines.append(
            "| "
            f"{row['label']} | "
            f"{row['anchor']} -> {row['replacement']} | "
            f"{float(row['replacement_cosine']):.3f} | "
            f"{row['distractor']} | "
            f"{float(row['distractor_cosine']):.3f} |"
        )
    lines.extend(
        [
            "",
            f"Mean supersession cosine: `{float(summary['replacement_mean']):.3f}`.",
            f"Mean distractor cosine: `{float(summary['distractor_mean']):.3f}`.",
            f"Max distractor cosine: `{distractor_max:.3f}`.",
            "",
            threshold_note,
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    result = run()
    print(
        "wrote docs/embedding-validation.md "
        f"(min pair={float(result['replacement_min']):.3f}, "
        f"max distractor={float(result['distractor_max']):.3f})"
    )
