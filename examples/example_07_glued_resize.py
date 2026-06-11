"""Tier 3: glued to the curve through a change of aspect.

The same curve and the same label call, drawn in two panels of different
aspect ratio. Because layout is recomputed per draw in display (pixel) space,
the character spacing and the perpendicular offset stay correct in both --
the label does not stretch or shear with the axes. This is the static stand-in
for the live case (interactive pan and zoom).
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import PALETTE, figure, bare, caption, save


def _panel(ax, label):
    bare(ax)
    x = np.linspace(0, 2 * np.pi, 400)
    y = np.sin(x)
    ax.plot(x, y, color=PALETTE["blue"], linewidth=2)
    ax.set_xlim(0, 2 * np.pi)
    ax.set_ylim(-1.5, 1.5)
    curved_text(ax, x, y, "same call, glued",
                pos=0.5, anchor="center", offset=8.0,
                color=PALETTE["gold"], fontsize=12)
    caption(ax, label)


def make(images_dir):
    fig = figure(18, 9, font_size=9)
    # A wide panel and a narrow one, same data and same label call.
    axes = fig.subplots(1, 2, width_ratios=[2.2, 1.0])
    _panel(axes[0], "wide aspect")
    _panel(axes[1], "narrow aspect")

    path = os.path.join(images_dir, "07_glued_resize.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
