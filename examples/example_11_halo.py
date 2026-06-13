"""Tier 2: clear the lines behind a label with a casing.

Set ``box`` to draw a band that follows the curve at the label's height,
under the glyphs, so the label stays legible where it crosses the lines it
labels. The casing is a single fill, so it gives solid coverage behind plain
and mathtext alike. For a lighter, glyph-hugging casing instead, pass a white
``withStroke`` through ``path_effects``.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import PALETTE, figure, bare, caption, save

LABEL = r"signal $s(t) = A\,e^{-t/\tau}$"


def make(images_dir):
    fig = figure(20, 9, font_size=9)
    axes = fig.subplots(2, 1)

    # A gentle arch with enough curvature that the label visibly follows it.
    x = np.linspace(0, 10, 400)
    y = 1.5 * np.sin(np.pi * x / 10.0)

    for ax, box in zip(axes, [False, True]):
        bare(ax)
        for shift in (-0.4, 0.0, 0.4):
            ax.plot(x, y + shift, color="0.55", linewidth=1.4)
        ax.set_xlim(-0.2, 10.2)
        ax.set_ylim(-0.9, 2.4)
        curved_text(ax, x, y, LABEL, pos=0.5, anchor="center", offset=0.0,
                    color=PALETTE["gold"], fontsize=16, box=box)
        caption(ax, f"box={box}")

    path = os.path.join(images_dir, "11_halo.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
