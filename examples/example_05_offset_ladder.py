"""Tier 2: the ``offset`` control -- a perpendicular shift off the curve.

Same curve, same ``pos``; only ``offset`` varies across negative, zero, and
positive. The label rides the curve at ``offset=0`` and lifts off along the
chord normal otherwise. Positive is to the left of the direction of travel,
which is visually above a left-to-right curve. The green dot marks the
on-curve anchor as a reference.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import SPANISH, figure, bare, caption, anchor_xy, save

OFFSETS = [-14.0, 0.0, 14.0]
POS = 0.5


def make(images_dir):
    fig = figure(18, 5.5, font_size=8)
    axes = fig.subplots(1, len(OFFSETS))

    x = np.linspace(0, 1, 200)
    y = 0.45 * (1 - (2 * x - 1) ** 2)  # a downward-opening arc

    for ax, offset in zip(axes, OFFSETS):
        bare(ax)
        ax.plot(x, y, color=SPANISH["indigo"], linewidth=2)
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(-0.35, 0.95)
        label = curved_text(ax, x, y, "offset", pos=POS, anchor="center",
                            offset=offset, color=SPANISH["flag_red"],
                            fontsize=11)
        # Lift the glyphs above the anchor dot so the dot never sits on the
        # text -- it marks the on-curve reference the offset is measured from.
        label.set_zorder(5)
        caption(ax, f"offset={offset:g}")

    # Mark the on-curve anchor the offset is measured from, behind the glyphs.
    fig.canvas.draw()
    for ax in axes:
        ax_x, ax_y = anchor_xy(ax, x, y, POS)
        ax.plot([ax_x], [ax_y], "o", color=SPANISH["flag_yellow"], markersize=5,
                zorder=4)

    path = os.path.join(images_dir, "05_offset_ladder.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
