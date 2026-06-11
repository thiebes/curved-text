"""Tier 2: the ``pos`` control, as a small-multiple sweep.

Same curve, same word, ``anchor="center"``; only ``pos`` varies. A dot marks
the anchor point so the reader sees the label slide from the first point
(0.0) to the last (1.0) along arc length.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import PALETTE, figure, bare, caption, anchor_xy, save

POSITIONS = [0.0, 0.25, 0.5, 0.75, 1.0]


def make(images_dir):
    fig = figure(20, 5, font_size=8)
    axes = fig.subplots(1, len(POSITIONS))

    x = np.linspace(0, 1, 200)
    y = 0.35 * np.sin(np.pi * x)

    for ax, pos in zip(axes, POSITIONS):
        bare(ax)
        ax.plot(x, y, color=PALETTE["blue"], linewidth=2)
        # Wide enough that a centred label at pos 0.0 / 1.0 shows in full
        # (it overruns the endpoint along the tangent rather than clipping).
        ax.set_xlim(-0.35, 1.35)
        ax.set_ylim(-0.15, 0.55)
        curved_text(ax, x, y, "label", pos=pos, anchor="center",
                    offset=7.0, color=PALETTE["gold"], fontsize=11)
        caption(ax, f"pos={pos}")

    # Mark each anchor point after a draw, when transData is valid.
    fig.canvas.draw()
    for ax, pos in zip(axes, POSITIONS):
        ax_x, ax_y = anchor_xy(ax, x, y, pos)
        ax.plot([ax_x], [ax_y], "o", color=PALETTE["green"], markersize=5,
                zorder=5)

    path = os.path.join(images_dir, "03_pos_sweep.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
