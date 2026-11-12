"""The ``min_radius`` control: a label on the inside of a bend tighter than it.

The curve is a valley whose radius of curvature at the bottom is smaller than
the label is tall. In (a) and (c) the label rides the curve as it is: the
expression folds over itself in (a), and in (c) the letters of the offset label
overlap and change order. In (b) and (d) the default, ``min_radius="auto"``,
rounds the path the label rides to a radius larger than the label's ink on the
inside of the bend, so nothing folds.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import (CURVE_COLOR, LABEL_COLOR, bare, caption, figure,
                    panel_letters, save)

# The radius of curvature at the bottom of the valley, in data units. The axes
# are set so one data unit is about one point.
RADIUS = 5
MATH = r"flux $\sqrt{\frac{a^2+b^2}{c^2}}\,\sum_{i=1}^{n} x_i$ out"
PLAIN = "Temperature"
FONTSIZE = 14
OFFSET = 22.0
MODES = [None, "auto"]


def make(images_dir):
    fig = figure(17, 11, font_size=8)
    axes = fig.subplots(2, 2)

    x = np.linspace(-245, 245, 4001)
    y = np.sqrt(x ** 2 + RADIUS ** 2)
    rows = [(MATH, {}), (PLAIN, {"offset": OFFSET})]

    for (text, extra), row in zip(rows, axes):
        for ax, mode in zip(row, MODES):
            bare(ax)
            ax.set_aspect("equal")
            ax.set_xlim(-100, 100)
            ax.set_ylim(RADIUS - 25, RADIUS + 70)
            ax.plot(x, y, color=CURVE_COLOR, linewidth=1.2)
            curved_text(ax, x, y, text, color=LABEL_COLOR, fontsize=FONTSIZE,
                        min_radius=mode, **extra)

    for row in axes:
        for ax, mode in zip(row, MODES):
            caption(ax, f"min_radius={mode!r}".replace("'", '"'))
    panel_letters(axes)

    path = os.path.join(images_dir, "27_tight_bends.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
