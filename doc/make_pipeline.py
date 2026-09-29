"""Render ScholarRAG pipeline diagram to PNG/PDF."""

from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.lines import Line2D

OUT_DIR = Path(__file__).parent
OUT_DIR.mkdir(exist_ok=True)

# Colors
C_STAGE   = "#DCE6F5"   # blue-ish  (main stages)
C_STAGE_E = "#4A6FA5"
C_INNER   = "#FCE3C0"   # orange-ish (sub-agent inner loop)
C_INNER_E = "#B3741E"
C_STORE   = "#CFE8CF"   # green (store)
C_STORE_E = "#3C7A3C"
C_IO      = "#EAEAEA"   # gray (input/output)
C_IO_E    = "#555555"
C_PANEL   = "#FAFAFA"
C_PANEL_E = "#AAAAAA"


def box(ax, xy, w, h, text, face, edge, sub=None, fontsize=10, sub_size=8):
    x, y = xy
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.1, facecolor=face, edgecolor=edge,
    )
    ax.add_patch(patch)
    cy = y + h / 2 + (0.06 if sub else 0.0)
    ax.text(x + w / 2, cy, text, ha="center", va="center",
            fontsize=fontsize, fontweight="bold", color="#222")
    if sub:
        ax.text(x + w / 2, y + h / 2 - 0.18, sub, ha="center", va="center",
                fontsize=sub_size, color="#444", style="italic")
    return (x, y, w, h)


def store(ax, xy, w, h, text, sub=None):
    # cylinder-ish: rounded rectangle + top ellipse
    x, y = xy
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.15",
        linewidth=1.1, facecolor=C_STORE, edgecolor=C_STORE_E,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2 + 0.05, text, ha="center", va="center",
            fontsize=10, fontweight="bold", color="#222")
    if sub:
        ax.text(x + w / 2, y + h / 2 - 0.18, sub, ha="center", va="center",
                fontsize=8, color="#444", style="italic")
    return (x, y, w, h)


def center_right(b):
    x, y, w, h = b
    return (x + w, y + h / 2)


def center_left(b):
    x, y, w, h = b
    return (x, y + h / 2)


def center_top(b):
    x, y, w, h = b
    return (x + w / 2, y + h)


def center_bottom(b):
    x, y, w, h = b
    return (x + w / 2, y)


def arrow(ax, p1, p2, style="-|>", color="#333", lw=1.2, ls="-",
          connectionstyle="arc3,rad=0"):
    a = FancyArrowPatch(p1, p2,
                        arrowstyle=style, mutation_scale=12,
                        color=color, linewidth=lw, linestyle=ls,
                        connectionstyle=connectionstyle)
    ax.add_patch(a)


def panel(ax, xy, w, h, title):
    x, y = xy
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.1",
        linewidth=1.0, facecolor=C_PANEL, edgecolor=C_PANEL_E,
        linestyle=(0, (4, 3)),
    )
    ax.add_patch(patch)
    ax.text(x + 0.15, y + h - 0.18, title, ha="left", va="center",
            fontsize=10, fontweight="bold", color="#333")


def make_pipeline():
    fig, ax = plt.subplots(figsize=(13.5, 7.5))
    ax.set_xlim(0, 18)
    ax.set_ylim(0, 10)
    ax.set_aspect("equal")
    ax.axis("off")

    # ---------- Offline ingestion panel ----------
    panel(ax, (0.3, 7.7), 17.4, 1.9, "Offline ingestion")

    bw, bh = 2.3, 1.0
    y0 = 8.05
    gap = 0.35

    b_pdf    = box(ax, (0.7,  y0), bw, bh, "PDF upload",          C_IO,    C_IO_E)
    x = 0.7 + bw + gap
    b_parse  = box(ax, (x,    y0), bw, bh, "Docling parse",       C_STAGE, C_STAGE_E, sub="+ OCR fallback")
    x += bw + gap
    b_nodes  = box(ax, (x,    y0), bw, bh, "Typed nodes",         C_STAGE, C_STAGE_E, sub="hdr / para / cap / fig / tbl / formula", sub_size=7)
    x += bw + gap
    b_cls    = box(ax, (x,    y0), bw, bh, "Section classify",    C_STAGE, C_STAGE_E)
    x += bw + gap
    b_chunk  = box(ax, (x,    y0), bw, bh, "Parent / child",      C_STAGE, C_STAGE_E, sub="chunking")
    x += bw + gap
    b_milvus = store(ax, (x,  y0), bw, bh, "Milvus",              sub="BM25 + dense")

    for a, b in [(b_pdf, b_parse), (b_parse, b_nodes), (b_nodes, b_cls),
                 (b_cls, b_chunk), (b_chunk, b_milvus)]:
        arrow(ax, center_right(a), center_left(b))

    # ---------- Online agent panel ----------
    panel(ax, (0.3, 0.3), 17.4, 7.1, "Online multi-agent pipeline")

    # Top row: orchestration
    y1 = 5.5
    b_q   = box(ax, (0.7,  y1), bw, bh, "User query",       C_IO,    C_IO_E, sub="+ history")
    x = 0.7 + bw + gap
    b_sum = box(ax, (x,    y1), bw, bh, "Summarize",        C_STAGE, C_STAGE_E, sub="memory")
    x += bw + gap
    b_clf = box(ax, (x,    y1), bw, bh, "Classify",         C_STAGE, C_STAGE_E, sub="query type")
    x += bw + gap
    b_ana = box(ax, (x,    y1), bw, bh, "Decompose",        C_STAGE, C_STAGE_E, sub="sub-queries")
    x += bw + gap
    b_dsp = box(ax, (x,    y1), bw, bh, "Parallel dispatch", C_STAGE, C_STAGE_E)

    for a, b in [(b_q, b_sum), (b_sum, b_clf), (b_clf, b_ana), (b_ana, b_dsp)]:
        arrow(ax, center_right(a), center_left(b))

    # Bottom row: sub-agent loop
    y2 = 2.3
    b_ret = box(ax, (2.5,  y2), bw, bh, "Retrieve",  C_INNER, C_INNER_E, sub="hybrid + rerank + parent", sub_size=7)
    x = 2.5 + bw + gap
    b_gen = box(ax, (x,    y2), bw, bh, "Generate",  C_INNER, C_INNER_E, sub=r"($\pm$ VLM)")
    x += bw + gap
    b_ref = box(ax, (x,    y2), bw, bh, "Reflect",   C_INNER, C_INNER_E, sub="sufficient?")
    x += bw + gap
    b_syn = box(ax, (x,    y2), bw, bh, "Synthesize", C_STAGE, C_STAGE_E, sub="+ citations")
    x += bw + gap
    b_out = box(ax, (x,    y2), bw, bh, "Answer",    C_IO,    C_IO_E)

    arrow(ax, center_right(b_ret), center_left(b_gen))
    arrow(ax, center_right(b_gen), center_left(b_ref))
    arrow(ax, center_right(b_ref), center_left(b_syn))
    ax.text((b_ref[0] + b_ref[2] + b_syn[0]) / 2, y2 + bh + 0.1,
            "done", ha="center", va="bottom", fontsize=8, color="#444")
    arrow(ax, center_right(b_syn), center_left(b_out))

    # Dispatch -> Retrieve: enter top-left of Retrieve
    dx, dy = center_bottom(b_dsp)
    rt_x_left = b_ret[0] + b_ret[2] * 0.33
    rt_y = b_ret[1] + b_ret[3]
    ax.add_line(Line2D([dx, dx], [dy, 4.35], color="#333", linewidth=1.2))
    ax.add_line(Line2D([dx, rt_x_left], [4.35, 4.35], color="#333", linewidth=1.2))
    arrow(ax, (rt_x_left, 4.35), (rt_x_left, rt_y), color="#333")
    ax.text((dx + rt_x_left) / 2, 4.45, "dispatch sub-queries",
            ha="center", va="bottom", fontsize=8, color="#333", style="italic")

    # Milvus -> Retrieve: enter top-right of Retrieve; route above the dispatch line
    mx, my = center_bottom(b_milvus)
    rx_top_right = b_ret[0] + b_ret[2] * 0.7
    ry_top = b_ret[1] + b_ret[3]
    wp_y = 4.0
    ax.add_line(Line2D([mx, mx], [my, wp_y],
                       color="#3C7A3C", linestyle=(0, (4, 3)), linewidth=1.2))
    ax.add_line(Line2D([mx, rx_top_right], [wp_y, wp_y],
                       color="#3C7A3C", linestyle=(0, (4, 3)), linewidth=1.2))
    arrow(ax, (rx_top_right, wp_y), (rx_top_right, ry_top),
          ls=(0, (4, 3)), color="#3C7A3C")
    ax.text(mx - 0.2, wp_y + 0.15, "vector feed",
            ha="right", va="bottom", fontsize=8, color="#3C7A3C", style="italic")

    # Retry loop: Reflect -> Retrieve (dashed curve below)
    p_r = center_bottom(b_ref)
    p_t = center_bottom(b_ret)
    a = FancyArrowPatch(p_r, p_t,
                        arrowstyle="-|>", mutation_scale=12,
                        color="#B3741E", linewidth=1.2,
                        linestyle=(0, (4, 3)),
                        connectionstyle="arc3,rad=0.25")
    ax.add_patch(a)
    # Sub-agent loop label: above the retry arrow label (tight spacing)
    ax.text((p_r[0] + p_t[0]) / 2, y2 - 0.5,
            "sub-agent inner loop (run in parallel per sub-query)",
            ha="center", va="center", fontsize=9, color="#8a5a12", style="italic")

    ax.text((p_r[0] + p_t[0]) / 2, y2 - 0.72,
            r"retry $\leq k$", ha="center", va="center",
            fontsize=9, color="#B3741E", style="italic")

    # Title
    ax.text(9.0, 9.8, "RuleTrace Scholar Base Pipeline",
            ha="center", va="center", fontsize=14, fontweight="bold")

    # Legend
    legend_items = [
        ("Input / Output", C_IO, C_IO_E),
        ("Orchestration stage", C_STAGE, C_STAGE_E),
        ("Sub-agent step", C_INNER, C_INNER_E),
        ("Vector store", C_STORE, C_STORE_E),
    ]
    lx, ly = 0.7, 0.55
    for i, (label, face, edge) in enumerate(legend_items):
        rx = lx + i * 4.3
        rect = FancyBboxPatch((rx, ly), 0.35, 0.25,
                              boxstyle="round,pad=0.01,rounding_size=0.05",
                              facecolor=face, edgecolor=edge, linewidth=1.0)
        ax.add_patch(rect)
        ax.text(rx + 0.45, ly + 0.12, label, ha="left", va="center",
                fontsize=9, color="#333")

    plt.tight_layout()
    out_png = OUT_DIR / "pipeline.png"
    out_pdf = OUT_DIR / "pipeline.pdf"
    fig.savefig(out_png, dpi=220, bbox_inches="tight")
    fig.savefig(out_pdf, bbox_inches="tight")
    print(f"saved: {out_png}")
    print(f"saved: {out_pdf}")


if __name__ == "__main__":
    make_pipeline()
