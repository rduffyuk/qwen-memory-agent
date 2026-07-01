# Author: Ryan Duffy <ryanduffy.uk@gmail.com>
# ORCID: 0009-0009-6464-0617
# Generated with: Claude Code
"""Render the Qwen MemoryAgent architecture diagram to docs/architecture.png."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# palette
INK = "#1b2330"
CLOUD = "#e8f0fe"
CLOUD_EDGE = "#4285f4"
ECS = "#fff4e6"
ECS_EDGE = "#ff7a1a"
COMP = "#ffffff"
COMP_EDGE = "#9aa7b8"
ENGINE = "#eafaf1"
ENGINE_EDGE = "#28a745"
QD = "#f3ecff"
QD_EDGE = "#7b3fe4"
CLIENT = "#eef1f5"
CLIENT_EDGE = "#5a6b82"

fig, ax = plt.subplots(figsize=(15, 10), dpi=150)
ax.set_xlim(0, 150)
ax.set_ylim(0, 100)
ax.axis("off")


def box(x, y, w, h, face, edge, title, subtitle="", tsize=13, ssize=9.5, radius=2.2, lw=2):
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle=f"round,pad=0.02,rounding_size={radius}",
            facecolor=face,
            edgecolor=edge,
            linewidth=lw,
            mutation_aspect=1,
        )
    )
    cx = x + w / 2
    if subtitle:
        ax.text(
            cx,
            y + h * 0.62,
            title,
            ha="center",
            va="center",
            fontsize=tsize,
            fontweight="bold",
            color=INK,
        )
        ax.text(
            cx, y + h * 0.30, subtitle, ha="center", va="center", fontsize=ssize, color="#42505f"
        )
    else:
        ax.text(
            cx,
            y + h / 2,
            title,
            ha="center",
            va="center",
            fontsize=tsize,
            fontweight="bold",
            color=INK,
        )
    return (x, y, w, h)


def arrow(p1, p2, text="", style="-|>", color=INK, ls="-", lw=2.0, rad=0.0, toff=(0, 2)):
    ax.annotate(
        "",
        xy=p2,
        xytext=p1,
        arrowprops=dict(
            arrowstyle=style,
            color=color,
            lw=lw,
            linestyle=ls,
            connectionstyle=f"arc3,rad={rad}",
            shrinkA=2,
            shrinkB=2,
        ),
    )
    if text:
        mx, my = (p1[0] + p2[0]) / 2 + toff[0], (p1[1] + p2[1]) / 2 + toff[1]
        ax.text(
            mx,
            my,
            text,
            ha="center",
            va="center",
            fontsize=8.5,
            color=color,
            style="italic",
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85),
        )


# Title
ax.text(
    75,
    96,
    "Qwen MemoryAgent — Architecture",
    ha="center",
    va="center",
    fontsize=20,
    fontweight="bold",
    color=INK,
)
ax.text(
    75,
    91.5,
    "Track 1 · MemoryAgent  ·  agentic memory on Qwen Cloud, deployed on Alibaba Cloud ECS",
    ha="center",
    va="center",
    fontsize=11,
    color="#5a6b82",
)

# Client (left)
client = box(
    5, 46, 22, 12, CLIENT, CLIENT_EDGE, "Client", "MCP client · demo UI · curl", tsize=14, ssize=9
)

# ECS container (center)
ecs_x, ecs_y, ecs_w, ecs_h = 38, 12, 62, 72
ax.add_patch(
    FancyBboxPatch(
        (ecs_x, ecs_y),
        ecs_w,
        ecs_h,
        boxstyle="round,pad=0.02,rounding_size=3",
        facecolor=ECS,
        edgecolor=ECS_EDGE,
        linewidth=2.5,
        linestyle="--",
    )
)
ax.text(
    ecs_x + ecs_w / 2,
    ecs_y + ecs_h - 3.5,
    "Alibaba Cloud ECS  (Singapore · 2 vCPU / 3.4 GiB · Ubuntu)",
    ha="center",
    va="center",
    fontsize=11.5,
    fontweight="bold",
    color=ECS_EDGE,
)

cx0 = ecs_x + 5
cw = ecs_w - 10
fastapi = box(
    cx0,
    66,
    cw,
    9,
    COMP,
    COMP_EDGE,
    "FastAPI backend",
    "/chat · /health · /usage · /memory/* · /dream · /dream/apply",
    tsize=13,
    ssize=8.5,
)
agent = box(
    cx0,
    52,
    cw * 0.5 - 2,
    9,
    COMP,
    COMP_EDGE,
    "MemoryAgent loop",
    "Qwen function-calling",
    tsize=12,
    ssize=9,
)
mcp = box(
    cx0 + cw * 0.5 + 2,
    52,
    cw * 0.5 - 2,
    9,
    COMP,
    COMP_EDGE,
    "FastMCP server",
    "remember / recall / forget / stats\nexport / import / dream / dream_apply",
    tsize=12,
    ssize=7.2,
)
engine = box(
    cx0,
    33,
    cw,
    13,
    ENGINE,
    ENGINE_EDGE,
    "Memory Engine",
    "write · retrieve · exact + semantic supersession · typed retrieval\ngraded decay + reinforce-on-recall · dreaming loop · token-budget pack",
    tsize=13,
    ssize=7.8,
)
qdrant = box(
    cx0, 17, cw * 0.5 - 2, 9, QD, QD_EDGE, "Qdrant", "vector store (embedded)", tsize=12, ssize=9
)
persist = box(
    cx0 + cw * 0.5 + 2,
    17,
    cw * 0.5 - 2,
    9,
    "#fdf2f8",
    "#d6337a",
    "Disk snapshot",
    "memory.json · survives restart",
    tsize=12,
    ssize=8.2,
)

# Qwen Cloud (right)
qwen = box(112, 34, 34, 30, CLOUD, CLOUD_EDGE, "", "", radius=3, lw=2.5)
ax.text(
    129,
    58,
    "Qwen Cloud",
    ha="center",
    va="center",
    fontsize=15,
    fontweight="bold",
    color=CLOUD_EDGE,
)
ax.text(129, 54, "DashScope-intl", ha="center", va="center", fontsize=10.5, color="#42505f")
ax.text(129, 54, "", ha="center")
ax.text(
    129,
    47.5,
    "OpenAI-compatible endpoint",
    ha="center",
    va="center",
    fontsize=9,
    style="italic",
    color="#5a6b82",
)
ax.text(129, 43, "qwen-plus", ha="center", va="center", fontsize=10.5, fontweight="bold", color=INK)
ax.text(
    129, 40, "reasoning + tool-calling", ha="center", va="center", fontsize=8.5, color="#42505f"
)
ax.text(
    129,
    36.5,
    "text-embedding-v3",
    ha="center",
    va="center",
    fontsize=10.5,
    fontweight="bold",
    color=INK,
)

# Arrows
arrow((27, 54), (38, 71), "HTTP", rad=0.05)  # client -> FastAPI
arrow((27, 50), (43, 56.5), "MCP", ls=(0, (4, 3)), color="#5a6b82", rad=-0.05)  # client -> MCP
arrow((cx0 + cw * 0.25, 66), (cx0 + cw * 0.25, 61), "")  # FastAPI -> Agent
arrow((agent[0] + agent[2] / 2, 52), (cx0 + cw * 0.4, 46), "invokes tools", rad=0.0, toff=(-4, 1))
arrow((mcp[0] + mcp[2] / 2, 52), (cx0 + cw * 0.6, 46), "", rad=0.0)  # MCP -> Engine
arrow((cx0 + cw * 0.24, 33), (cx0 + cw * 0.24, 26), "", color="#7b3fe4")  # Engine <-> Qdrant
arrow((cx0 + cw * 0.30, 26), (cx0 + cw * 0.30, 33), "", color="#7b3fe4")
arrow(
    (cx0 + cw * 0.74, 33), (cx0 + cw * 0.74, 26), "", color="#d6337a"
)  # Engine -> snapshot (save)
arrow(
    (cx0 + cw * 0.80, 26), (cx0 + cw * 0.80, 33), "", color="#d6337a"
)  # snapshot -> Engine (load)
ax.text(
    cx0 + cw * 0.90,
    29.5,
    "save on write /\nload on start",
    ha="left",
    va="center",
    fontsize=8,
    style="italic",
    color="#d6337a",
)

# Agent <-> Qwen (chat + tools)
arrow((agent[0] + agent[2], 56.5), (112, 45), "chat + tool specs", rad=0.12, color=CLOUD_EDGE)
# Engine <-> Qwen (embed)
arrow((cx0 + cw, 39), (112, 37.5), "embed", rad=-0.10, color=CLOUD_EDGE)

# footer
ax.text(
    75,
    6.5,
    "github.com/rduffyuk/qwen-memory-agent  ·  MIT  ·  fully-offline test suite (zero API spend)",
    ha="center",
    va="center",
    fontsize=9.5,
    color="#7a8699",
)

plt.tight_layout()
plt.savefig("docs/architecture.png", bbox_inches="tight", facecolor="white", dpi=150)
print("wrote docs/architecture.png")
