"""Plain text and mathtext share one baseline.

A label that alternates plain words and ``$...$`` runs lies on a curve with
``valign="baseline"``, so the plain glyphs and the math glyphs sit on the same
line.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import CURVE_COLOR, LABEL_COLOR, bare, caption, figure, save

LABEL = r"mass $m$ and speed $c$ give $E = mc^2$"


def make(images_dir):
    fig = figure(17, 6.4, font_size=11)
    ax = fig.subplots()
    bare(ax)

    x = np.linspace(0, 10, 400)
    y = 1.0 * np.sin(np.pi * x / 10.0)  # one gentle hump
    ax.plot(x, y, color=CURVE_COLOR, linewidth=2)
    ax.set_xlim(-0.3, 10.3)
    ax.set_ylim(-0.4, 1.9)

    # valign="baseline" puts the shared baseline on the curve, so the plain words
    # and the math runs all sit on the drawn line together.
    curved_text(ax, x, y, LABEL, pos=0.5, anchor="center",
                valign="baseline", color=LABEL_COLOR, fontsize=15)

    caption(ax, 'curved_text(ax, x, y, r"mass $m$ and speed $c$ give '
                '$E = mc^2$",\n            valign="baseline")')

    path = os.path.join(images_dir, "15_mixed_alignment.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
