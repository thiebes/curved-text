"""Tier 2: box versus a path-effects stroke for clearing the line behind text.

Two ways to keep a label readable where it crosses the lines it labels, on the
same plain-text label over the same gridlines. A wide ``withStroke`` is applied
per character, so neighbouring letters blur together. ``box`` is a single fill
under the whole label, so it covers plain text cleanly. This is why ``box`` is
the way to get solid coverage under plain text.
"""
from __future__ import annotations

import os

import numpy as np
import matplotlib.patheffects as pe

from curved_text import curved_text
from _style import PALETTE, figure, bare, caption, save

LABEL = "crossing the gridlines"


def make(images_dir):
    fig = figure(20, 9, font_size=9)
    axes = fig.subplots(2, 1)

    # A gentle arch crossing a set of horizontal lines, so the casing has
    # something to clear.
    x = np.linspace(0, 10, 400)
    y = 1.5 * np.sin(np.pi * x / 10.0)

    panels = [
        ("withStroke(linewidth=6)",
         dict(path_effects=[pe.withStroke(linewidth=6, foreground="white")])),
        ("box=True", dict(box=True)),
    ]
    for ax, (label, kwargs) in zip(axes, panels):
        bare(ax)
        for shift in (-0.4, 0.0, 0.4):
            ax.plot(x, y + shift, color="0.55", linewidth=1.4)
        ax.set_xlim(-0.2, 10.2)
        ax.set_ylim(-0.9, 2.4)
        curved_text(ax, x, y, LABEL, pos=0.5, anchor="center", offset=0.0,
                    color=PALETTE["blue"], fontsize=18, **kwargs)
        caption(ax, label)

    path = os.path.join(images_dir, "12_box_vs_stroke.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
