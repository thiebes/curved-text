"""Plain text and mathtext share one baseline.

A label that alternates plain words and ``$...$`` math runs rides a single
shared baseline, so the math symbols sit level with the surrounding letters and
a superscript lifts only the exponent, not the body. The curve here is drawn as
that baseline (``valign="baseline"``), so every plain glyph and every math glyph
visibly sits on the same line -- the alignment is structural, not tuned.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import SPANISH, figure, bare, caption, save

LABEL = r"mass $m$ and speed $c$ give $E = mc^2$"


def make(images_dir):
    fig = figure(16, 6, font_size=11)
    ax = fig.subplots()
    bare(ax)

    x = np.linspace(0, 10, 400)
    y = 1.0 * np.sin(np.pi * x / 10.0)  # one gentle hump
    ax.plot(x, y, color=SPANISH["fern_green"], linewidth=2)
    ax.set_xlim(-0.3, 10.3)
    ax.set_ylim(-0.4, 1.9)

    # valign="baseline" puts the shared baseline on the curve, so the plain words
    # and the math runs all sit on the drawn line together.
    curved_text(ax, x, y, LABEL, pos=0.5, anchor="center",
                valign="baseline", color=SPANISH["indigo"], fontsize=15)

    caption(ax, 'plain words and math runs ride one baseline '
                '(valign="baseline")')

    path = os.path.join(images_dir, "15_mixed_alignment.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
