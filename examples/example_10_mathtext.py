"""Tier 1: mathtext bent along the curve.

A ``$...$`` run in the label is laid out by matplotlib's mathtext engine and
bent through the same arc-length frame as plain text, so the radical, fraction,
and superscript stay connected and follow the curve. Plain and math runs mix in
one string.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import PALETTE, figure, bare, caption, save


def make(images_dir):
    fig = figure(14, 6, font_size=11)
    ax = fig.subplots()
    bare(ax)

    x = np.linspace(0, 2 * np.pi, 400)
    y = np.sin(x)
    ax.plot(x, y, color=PALETTE["blue"], linewidth=2)
    ax.set_xlim(0, 2 * np.pi)
    ax.set_ylim(-1.4, 1.4)

    curved_text(ax, x, y,
                r"flux $\propto \sqrt{D_{\mathrm{eff}}}\,\left(L/L_0\right)^{2}$",
                pos=0.5, anchor="center", offset=8.0,
                color=PALETTE["gold"], fontsize=14)

    caption(ax, r'curved_text(ax, x, y, '
                r'r"flux $\propto \sqrt{D_{\mathrm{eff}}}\,(L/L_0)^2$", ...)')

    path = os.path.join(images_dir, "10_mathtext.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
