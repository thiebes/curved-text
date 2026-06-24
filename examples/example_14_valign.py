"""The ``valign`` control -- which line of the text rides the curve.

Every label shares one text baseline; ``valign`` chooses which line that baseline
relationship puts on the curve, as a single constant shift applied to the whole
label (so it never introduces a per-glyph step, and plain text and mathtext stay
aligned). The default is ``"center"``, which straddles the text on the curve.

Each panel draws the same word on the same arc with the guide line shown, so the
relationship is visible: ``"baseline"`` sits the body above the line (descenders
dip below), ``"center"`` straddles it, ``"ascender"`` hangs the text below the
line, and ``"descender"`` lifts it above. The word has an ascender and a
descender so all four differ. Combine any of these with ``offset`` to lift the
chosen line off the curve.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import SPANISH, figure, bare, save

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
        ax.plot(x, y, color=SPANISH["indigo"], linewidth=1.5)
        ax.set_xlim(-0.62, 0.62)
        ax.set_ylim(-0.18, 0.30)
        curved_text(ax, x, y, WORD, pos=0.5, anchor="center", valign=mode,
                    color=SPANISH["flag_red"], fontsize=FONTSIZE)
        ax.set_title(f'valign="{mode}"')

    path = os.path.join(images_dir, "14_valign.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
