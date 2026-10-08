"""Why a label reads upside down: the direction of travel.

Text reads in the order of the curve's points as they appear on screen, and
each curve ends in an arrowhead at its last point, so it shows that direction
itself. The same sine, labelled three ways: (a) the points from left to
right, upright; (b) the arrays reversed, so the curve runs from right to left
and the label reads upside down; (c) the points from left to right on an
inverted x axis, which also puts them right to left on screen. ``pos`` counts
from the first point and ``offset`` turns with the direction too, so the label
also moves along and across the curve. Reversing the arrays of a curve that
runs from right to left on screen turns its label upright.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import (CURVE_COLOR, LABEL_COLOR, bare, caption, figure,
                    panel_letters, save)

# How many points the arrowhead spans back from the last one. The plotted line
# stops a few points short of the end, under the head: matplotlib draws the
# head's tip slightly short of the point it aims at, and the line would show
# past it.
HEAD_POINTS = 8
LINE_STOP = 5


def _curve_with_arrowhead(ax, x, y):
    """The curve, ending in an arrowhead at its last point."""
    ax.plot(x[:-LINE_STOP], y[:-LINE_STOP], color=CURVE_COLOR, linewidth=2)
    ax.annotate("", xy=(x[-1], y[-1]), xytext=(x[-HEAD_POINTS], y[-HEAD_POINTS]),
                arrowprops={"arrowstyle": "-|>,head_length=0.7,head_width=0.35",
                            "color": CURVE_COLOR, "linewidth": 0,
                            "shrinkA": 0, "shrinkB": 0, "mutation_scale": 15})


def make(images_dir):
    fig = figure(17, 5.5, font_size=8)
    axes = fig.subplots(1, 3)

    x = np.linspace(0, 2 * np.pi, 400)
    y = np.sin(x)
    panels = [
        (x, y, False, "curved_text(ax, x, y, ...)"),
        (x[::-1], y[::-1], False, "curved_text(ax, x[::-1], y[::-1], ...)"),
        (x, y, True, "ax.invert_xaxis()\ncurved_text(ax, x, y, ...)"),
    ]
    for ax, (cx, cy, invert, call) in zip(axes, panels):
        bare(ax)
        _curve_with_arrowhead(ax, cx, cy)
        # Room at the ends for the arrowhead.
        ax.set_xlim(-0.4, 2 * np.pi + 0.4)
        ax.set_ylim(-1.6, 1.6)
        if invert:
            ax.invert_xaxis()
        curved_text(ax, cx, cy, "reads this way", pos=0.4, anchor="center",
                    offset=7.0, color=LABEL_COLOR, fontsize=10)
        caption(ax, call)
    panel_letters(axes)

    path = os.path.join(images_dir, "17_direction_of_travel.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
