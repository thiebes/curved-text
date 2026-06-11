"""Tier 2: the ``anchor`` control -- which part of the label lands at ``pos``.

Same curve, same ``pos=0.5``; only ``anchor`` varies across start / center /
end. The green dot is fixed at ``pos`` in every panel; watch which part of
the word -- its start, middle, or end -- sits on the dot.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import PALETTE, figure, bare, caption, anchor_xy, save

ANCHORS = ["start", "center", "end"]
POS = 0.5


def make(images_dir):
    fig = figure(18, 5, font_size=8)
    axes = fig.subplots(1, len(ANCHORS))

    x = np.linspace(0, 1, 200)
    y = 0.3 * np.sin(np.pi * x)

    for ax, anchor in zip(axes, ANCHORS):
        bare(ax)
        ax.plot(x, y, color=PALETTE["blue"], linewidth=2)
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(-0.1, 0.45)
        curved_text(ax, x, y, "anchored", pos=POS, anchor=anchor,
                    offset=7.0, color=PALETTE["gold"], fontsize=11)
        caption(ax, f'anchor="{anchor}"')

    fig.canvas.draw()
    for ax in axes:
        ax_x, ax_y = anchor_xy(ax, x, y, POS)
        ax.plot([ax_x], [ax_y], "o", color=PALETTE["green"], markersize=6,
                zorder=5)

    path = os.path.join(images_dir, "04_anchor_triptych.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
