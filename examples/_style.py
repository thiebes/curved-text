"""Shared palette and helpers for the curved-text example gallery.

Follows the repo's plot conventions: colorblind-safe palette, white opaque
background, constrained layout, sizes in centimetres, explicit dpi. Most panels
here are diagrams whose subject is the text-on-curve geometry, so they hide
their axes -- the curve is the data, and bare quantitative ticks would be
chartjunk. The one true data figure (direct labeling) keeps axes with units.
"""
from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

# DICE palette set: blue / gold / green -- the default for most panels.
PALETTE = {"blue": "#003f7f", "gold": "#f7941e", "green": "#0cce6b"}
# Spanish-flag palette set: a more saturated, categorical identity used on a few
# panels for variety. Indigo is the darkest colour and anchors the pairings.
SPANISH = {
    "flag_red": "#c60b1e",
    "flag_yellow": "#ffc400",
    "fern_green": "#4a7729",
    "blue": "#0077c8",
    "indigo": "#540d6e",
}
INCH = 1 / 2.54
DPI = 150


def figure(width_cm, height_cm, font_size=9):
    """A white, constrained-layout figure sized in centimetres."""
    plt.rcParams.update({"font.size": font_size})
    fig = plt.figure(figsize=(width_cm * INCH, height_cm * INCH),
                     layout="constrained")
    fig.patch.set_facecolor("w")
    fig.patch.set_alpha(1)
    return fig


def data_axes(ax, font_size=9, tick_len=4, tick_w=1):
    """Inward ticks on all four sides, so the frame reads as a box."""
    ax.tick_params(axis="both", which="both", direction="in",
                   top=True, right=True, labelsize=font_size,
                   length=tick_len, width=tick_w)
    return ax


def bare(ax):
    """Hide the axes entirely; the curve is the only subject."""
    ax.set_axis_off()
    return ax


def caption(ax, text, font_size=8):
    """A monospace caption under a panel -- usually the call that drew it."""
    ax.text(0.5, -0.06, text, transform=ax.transAxes, ha="center", va="top",
            fontsize=font_size, family="monospace", color="0.30")


def anchor_xy(ax, x, y, pos):
    """Data-space ``(x, y)`` at arc-length fraction ``pos``.

    Computed in display space so the marker lands exactly where ``CurvedText``
    anchors. Requires a prior ``fig.canvas.draw()`` so ``transData`` is valid.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    pts = ax.transData.transform(np.column_stack([x, y]))
    xf, yf = pts[:, 0], pts[:, 1]
    arc = np.insert(np.cumsum(np.hypot(np.diff(xf), np.diff(yf))), 0, 0.0)
    s = pos * arc[-1]
    i = int(np.clip(np.searchsorted(arc, s) - 1, 0, len(arc) - 2))
    d = arc[i + 1] - arc[i]
    f = (s - arc[i]) / d if d else 0.0
    px = xf[i] + f * (xf[i + 1] - xf[i])
    py = yf[i] + f * (yf[i + 1] - yf[i])
    return tuple(ax.transData.inverted().transform((px, py)))


def save(fig, path):
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path
