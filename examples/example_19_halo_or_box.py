"""A halo or a box: two ways to keep a label legible over the lines it crosses.

The same label over a family of thin lines that cross it at a steep angle,
cleared two ways. (a) A halo, a thin white ``withStroke`` around each glyph
(``path_effects``): it hides the lines only where they touch the letters, so
they stay readable on either side of each letter, which suits thin lines and
dense figures. (b) A casing (``box``, here in its colour-string form, white
to match the page): one band under the whole label, which clears heavy lines
completely, but also erases every line inside the band.
"""
from __future__ import annotations

import os

import matplotlib.patheffects as patheffects
import numpy as np

from curved_text import curved_text
from _style import (CURVE_COLOR, LABEL_COLOR, bare, caption, figure,
                    panel_letters, save)


def make(images_dir):
    fig = figure(17, 6.5, font_size=8)
    axes = fig.subplots(2, 1)

    x = np.linspace(0, 10, 400)
    y = 1.0 + 0.4 * np.sin(np.pi * x / 10.0)
    panels = [
        ('path_effects=[withStroke(linewidth=3, foreground="white")]',
         {"path_effects": [patheffects.withStroke(linewidth=3,
                                                  foreground="white")]}),
        ('box="white"', {"box": "white"}),
    ]
    for ax, (call, kwargs) in zip(axes, panels):
        bare(ax)
        ax.set_xlim(0, 10)
        ax.set_ylim(0.4, 1.9)
        # A family of thin parallel lines crossing the label steeply, like the
        # traces of a dense plot behind it.
        for intercept in np.arange(-30.0, 10.5, 0.6):
            ax.plot(x, 3.0 * x + intercept, color="0.55", linewidth=0.6,
                    zorder=1)
        ax.plot(x, y, color=CURVE_COLOR, linewidth=2, zorder=2)
        curved_text(ax, x, y, "legible over thin lines", pos=0.5,
                    anchor="center", offset=10.0, color=LABEL_COLOR,
                    fontsize=13, zorder=3, **kwargs)
        caption(ax, call)
    panel_letters(axes)

    path = os.path.join(images_dir, "19_halo_or_box.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
