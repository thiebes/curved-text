"""Streamlines of potential flow past a cylinder, each labeled upright.

A uniform flow of speed U past a cylinder of radius a has the stream function
psi = U (r - a^2 / r) sin(theta), where r is the distance from the cylinder's
axis and theta is the angle from the direction of the flow. In Cartesian
coordinates, psi = U y (1 - a^2 / (x^2 + y^2)). ``ax.contour`` of psi gives
each streamline as one continuous path and sets the direction of every path.
Here the paths happen to run from left to right, and each label is still passed
``upright=True``, which keeps it upright if a path runs the other way. Lengths
are in units of a, and psi is in units of U a.
"""
from __future__ import annotations

import os

import numpy as np
from matplotlib.patches import Circle

from curved_text import curved_text
from _style import (CURVE_COLOR, REFERENCE_COLOR, TEXT, data_axes, figure,
                    save)

# The extent of the plotted flow, in units of the cylinder's radius.
HALF_WIDTH = 4.0
HALF_HEIGHT = 2.6
# The streamlines drawn, as values of psi in units of U a.
LEVELS = [-2.0, -1.5, -1.0, -0.5, 0.5, 1.0, 1.5, 2.0]
MINUS = "\N{MINUS SIGN}"


def make(images_dir):
    x = np.linspace(-HALF_WIDTH, HALF_WIDTH, 801)
    y = np.linspace(-HALF_HEIGHT, HALF_HEIGHT, 521)
    xx, yy = np.meshgrid(x, y)
    # The flow is outside the cylinder, so the grid is masked inside it.
    radius_squared = xx ** 2 + yy ** 2
    outside = radius_squared >= 1.0
    psi = np.ma.masked_where(
        ~outside, yy * (1.0 - 1.0 / np.where(outside, radius_squared, 1.0)))

    fig = figure(17, 10.5, font_size=9)
    ax = data_axes(fig.subplots())
    ax.add_patch(Circle((0, 0), 1, facecolor="0.85", edgecolor=REFERENCE_COLOR,
                        linewidth=1.5, zorder=3))
    contours = ax.contour(xx, yy, psi, levels=LEVELS, colors=CURVE_COLOR,
                          linewidths=1.5, linestyles="solid")
    for level, segments in zip(contours.levels, contours.allsegs):
        # Each level is one path across the plot, on its side of the cylinder.
        path = max(segments, key=len)
        text = f"ψ = {level:g}".replace("-", MINUS)
        curved_text(ax, path[:, 0], path[:, 1], text, pos=0.5, box=True,
                    upright=True, fontsize=9, color=TEXT["blue"])
    ax.set_xlim(-HALF_WIDTH, HALF_WIDTH)
    ax.set_ylim(-HALF_HEIGHT, HALF_HEIGHT)
    ax.set_aspect("equal")
    ax.set_xlabel("x / a")
    ax.set_ylabel("y / a")

    path = os.path.join(images_dir, "24_streamlines.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
