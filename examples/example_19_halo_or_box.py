"""A halo or a box: two ways to keep a label legible over the lines it crosses.

The same label over a dense grid of thin lines, cleared two ways. (a) A thin
white halo around each glyph (``path_effects`` with ``withStroke``): it hides
the lines only where they touch the letters, so the grid stays visible around
them, which suits thin lines and dense figures. (b) A casing (``box``, here
in its colour-string form): one band under the whole label, which gives solid
coverage over heavier lines at the cost of hiding more of them.
"""
from __future__ import annotations

import os

import matplotlib.patheffects as patheffects
import numpy as np

from curved_text import curved_text
from _style import (CURVE_COLOR, LABEL_COLOR, bare, caption, figure,
                    panel_letters, save)


def make(images_dir):
    fig = figure(17, 8, font_size=8)
    axes = fig.subplots(2, 1)

    x = np.linspace(0, 10, 400)
    y = 1.0 + 0.6 * np.sin(np.pi * x / 10.0)
    panels = [
        ({"path_effects": [patheffects.withStroke(linewidth=3,
                                                  foreground="white")]},
         'path_effects=[withStroke(linewidth=3, foreground="white")]'),
        ({"box": "white"}, 'box="white"'),
    ]
    for ax, (kwargs, call) in zip(axes, panels):
        bare(ax)
        # A dense grid of thin lines, the background a halo is made for.
        for level in np.arange(0.0, 2.21, 0.1):
            ax.axhline(level, color="0.55", linewidth=0.6, zorder=1)
        for position in np.arange(0.0, 10.01, 0.5):
            ax.axvline(position, color="0.55", linewidth=0.6, zorder=1)
        ax.plot(x, y, color=CURVE_COLOR, linewidth=2, zorder=2)
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 2.2)
        curved_text(ax, x, y, "legible over a dense grid", pos=0.5,
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
