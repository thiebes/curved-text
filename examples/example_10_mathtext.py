"""Tier 1: mathtext bent along the curve.

A ``$...$`` run in the label is laid out by matplotlib's mathtext engine and
bent through the same arc-length frame as plain text, so the radical, nested
parentheses, and superscripts stay connected and follow the curve. The label
rides over a broad, gentle hump -- enough curvature to show the bend, gentle
enough that the expression stays clearly readable.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import PALETTE, figure, bare, caption, save


def make(images_dir):
    fig = figure(15, 7, font_size=11)
    ax = fig.subplots()
    bare(ax)

    x = np.linspace(0, 10, 400)
    y = 1.6 * np.sin(np.pi * x / 10.0)
    ax.plot(x, y, color=PALETTE["blue"], linewidth=2)
    ax.set_xlim(-0.3, 10.3)
    ax.set_ylim(-0.4, 2.9)

    curved_text(ax, x, y, r"$E = \sqrt{(pc)^2 + (mc^2)^2}$",
                pos=0.5, anchor="center", offset=20.0,
                color=PALETTE["gold"], fontsize=16)

    caption(ax, r'curved_text(ax, x, y, r"$E = \sqrt{(pc)^2 + (mc^2)^2}$", '
                r'pos=0.5, anchor="center", offset=20.0)')

    path = os.path.join(images_dir, "10_mathtext.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
