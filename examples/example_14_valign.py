"""The ``valign`` control: which line of the text lies on the curve.

The same word on the same arc, once for each ``valign`` value. The word has an
ascender and a descender, so all four panels differ.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import (CURVE_COLOR, LABEL_COLOR, bare, caption, figure,
                    panel_letters, save)

WORD = "Amplitude"
MODES = ["center", "baseline", "ascender", "descender"]
FONTSIZE = 20


def _arc():
    """A shallow left-to-right arc, low curvature so the word reads cleanly."""
    th = np.linspace(np.pi / 2 + 0.5, np.pi / 2 - 0.5, 400)
    x, y = np.cos(th), np.sin(th)
    return x, y - y.min()


def make(images_dir):
    fig = figure(17, 9, font_size=8)
    axes = fig.subplots(2, 2).ravel()
    x, y = _arc()

    for ax, mode in zip(axes, MODES):
        bare(ax)
        ax.set_aspect("equal")
        # The guide line, so the reader sees where each alignment sits relative
        # to the curve.
        ax.plot(x, y, color=CURVE_COLOR, linewidth=1.5)
        ax.set_xlim(-0.62, 0.62)
        ax.set_ylim(-0.18, 0.30)
        curved_text(ax, x, y, WORD, pos=0.5, anchor="center", valign=mode,
                    color=LABEL_COLOR, fontsize=FONTSIZE)
        caption(ax, f'valign="{mode}"')
    panel_letters(axes)

    path = os.path.join(images_dir, "14_valign.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
