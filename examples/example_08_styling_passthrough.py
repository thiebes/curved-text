"""Tier 4: extra keyword arguments reach every character.

Any kwargs beyond the placement controls are forwarded verbatim to each
per-character glyph and each mathtext run. Here ``color``, ``fontsize``,
``alpha``, ``fontweight``, and ``fontfamily`` are all set on one call, and the
label's colour matches its curve -- reinforcing the direct-labeling idea from the
first figure.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import PALETTE, figure, bare, caption, save


def make(images_dir):
    fig = figure(15, 7, font_size=10)
    ax = fig.subplots()
    bare(ax)

    x = np.linspace(0, 1, 300)
    y = np.exp(-3 * x) * np.cos(6 * x)
    ax.plot(x, y, color=PALETTE["green"], linewidth=2)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.6, 1.1)

    curved_text(ax, x, y, "styled per character",
                pos=0.18, anchor="start", offset=9.0,
                color=PALETTE["green"], fontsize=15, alpha=0.85,
                fontweight="bold", fontfamily="serif")

    caption(ax, 'color=..., fontsize=15, alpha=0.85, '
                'fontweight="bold", fontfamily="serif"')

    path = os.path.join(images_dir, "08_styling_passthrough.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
