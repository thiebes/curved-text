"""A casing compared with a wide path-effects stroke.

The same plain-text label is drawn over the same lines with a wide
``withStroke`` on each glyph and with ``box``. The stroke leaves small gaps,
and the casing covers the lines under the whole label.
"""
from __future__ import annotations

import os

import numpy as np
import matplotlib.patheffects as pe

from curved_text import curved_text
from _style import LABEL_COLOR, bare, caption, figure, panel_letters, save

LABEL = "crossing the gridlines"


def make(images_dir):
    fig = figure(17, 7.7, font_size=9)
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
                    color=LABEL_COLOR, fontsize=18, **kwargs)
        caption(ax, label)

    panel_letters(axes)
    path = os.path.join(images_dir, "12_box_vs_stroke.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
