"""Tier 2: clear the line behind a label with a path-effect halo.

Extra keyword arguments pass through to every glyph and mathtext run, so
matplotlib's ``path_effects`` reach the label like any other ``Text``. A white
``withStroke`` effect draws a casing that follows each glyph -- curved to match
the text -- so the label stays legible where it crosses the data lines.
"""
from __future__ import annotations

import os

import matplotlib.patheffects as pe
import numpy as np

from curved_text import curved_text
from _style import PALETTE, figure, bare, caption, save


def make(images_dir):
    fig = figure(15, 7, font_size=11)
    ax = fig.subplots()
    bare(ax)

    x = np.linspace(0, 10, 400)
    # A small family of nearby curves for the label to cross.
    for shift in (-0.5, 0.0, 0.5):
        ax.plot(x, np.sin(x) + shift, color="0.55", linewidth=1.4)
    ax.set_xlim(0, 10)
    ax.set_ylim(-2.0, 2.0)

    # offset=0 puts the label on the middle curve, so it crosses its neighbours;
    # the white halo clears all three behind the text.
    curved_text(ax, x, np.sin(x), r"signal $s(t) = A\,e^{-t/\tau}$",
                pos=0.5, anchor="center", offset=0.0,
                color=PALETTE["gold"], fontsize=16,
                path_effects=[pe.withStroke(linewidth=4.0, foreground="white")])

    caption(ax, 'curved_text(ax, x, y, "...", '
                'path_effects=[pe.withStroke(linewidth=4, foreground="white")])')

    path = os.path.join(images_dir, "11_halo.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
