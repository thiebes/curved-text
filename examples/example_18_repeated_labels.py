"""Several labels on one long curve, as inline contour labels repeat.

One call per label, each at its own ``pos``, so a long curve carries its name
wherever the reader's eye meets it. Each label clears the line with a casing,
given here in its dict form, which sets the band's colour and its height
relative to the tallest glyph.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import CURVE_COLOR, LABEL_COLOR, bare, caption, figure, save

POSITIONS = (0.12, 0.5, 0.88)


def make(images_dir):
    fig = figure(17, 6, font_size=9)
    ax = fig.subplots()
    bare(ax)

    # A damped oscillation over several periods: a long curve with bends.
    x = np.linspace(0, 6 * np.pi, 1200)
    y = np.exp(-x / 12.0) * np.sin(x)
    ax.plot(x, y, color=CURVE_COLOR, linewidth=1.5)
    ax.set_xlim(-0.3, 6 * np.pi + 0.3)
    ax.set_ylim(-1.2, 1.2)

    for pos in POSITIONS:
        curved_text(ax, x, y, "damped response", pos=pos, anchor="center",
                    color=LABEL_COLOR, fontsize=10,
                    box={"color": "white", "pad": 1.3})

    caption(ax, 'for pos in (0.12, 0.5, 0.88):\n'
                '    curved_text(ax, x, y, "damped response", pos=pos,\n'
                '                box={"color": "white", "pad": 1.3})')

    path = os.path.join(images_dir, "18_repeated_labels.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
