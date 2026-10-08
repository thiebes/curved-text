"""Shared palette and helpers for the curved-text example gallery.

Follows the repo's plot conventions: the DICE palette with contrast-checked
text shades, white opaque
background, constrained layout, sizes in centimetres, explicit dpi. Most panels
here are diagrams whose subject is the text-on-curve geometry, so they hide
their axes -- the curve is the data, and bare quantitative ticks would be
chartjunk. The data figures (direct labeling and its usetex version) keep axes
with units.
"""
from __future__ import annotations

import matplotlib.patheffects as patheffects
import numpy as np
import matplotlib.pyplot as plt

# DICE palette set: blue / gold / green, for lines and fills in every figure.
PALETTE = {"blue": "#003f7f", "gold": "#f7941e", "green": "#0cce6b"}
# The same hues dark enough for text, at least 4.5:1 against white by the WCAG 2
# contrast formula (lines and marks need 3:1). DICE gold and green are 2.28:1
# and 2.09:1, too light to read as text; DICE blue is 10.4:1 already.
TEXT = {
    "blue": "#003f7f",   # 10.41:1
    "gold": "#b06306",   # 4.53:1
    "green": "#088847",  # 4.54:1
}
# Colour roles in the diagrams, where the curve and the label are the subject:
# the curve in DICE blue, the label in dark gold, and a reference mark (such as
# the anchor point) as a dark green ring drawn above the label, so it never
# hides behind the text. Data figures colour each series in its DICE hue and
# its label in the matching text shade. One exception: 08 shows ``alpha``, which
# lightens its label, and only dark blue stays above 4.5:1 at alpha 0.85.
CURVE_COLOR = PALETTE["blue"]
LABEL_COLOR = TEXT["gold"]
MARK_COLOR = TEXT["green"]
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
    """Inward ticks on the bottom and left; the frame still closes the box."""
    ax.tick_params(axis="both", which="both", direction="in",
                   top=False, right=False, labelsize=font_size,
                   length=tick_len, width=tick_w)
    return ax


def bare(ax):
    """Hide the axes entirely; the curve is the only subject."""
    ax.set_axis_off()
    return ax


def caption(ax, text, font_size=8):
    """A monospace caption under a panel, usually the call that drew it.

    When every panel of a figure makes the same call, each caption shows only
    what differs between them, and the figure's README paragraph gives the
    shared call.

    Dollar signs are escaped, so the caption shows the call as written, not a
    mathtext rendering of it, and the lines of a long call keep their
    indentation, aligned left within the centred block.
    """
    ax.text(0.5, -0.06, text.replace("$", r"\$"), transform=ax.transAxes,
            ha="center", va="top", multialignment="left", fontsize=font_size,
            family="monospace", color="0.30")


def panel_letters(axes, font_size=9):
    """Letter the panels of a multi-panel figure (a), (b), ... in bold.

    Each letter sits just above its panel's upper left corner, in reading
    order, clear of the panel's tick labels and data.
    """
    for index, ax in enumerate(np.ravel(axes)):
        ax.annotate(f"({chr(ord('a') + index)})", xy=(0.0, 1.0),
                    xycoords="axes fraction", xytext=(0.0, 3.0),
                    textcoords="offset points", ha="left", va="bottom",
                    fontsize=font_size, fontweight="bold")


def anchor_mark(ax, x, y):
    """A ring at data point ``(x, y)`` in the reference-mark colour.

    It is drawn above the label, so the text never covers it, with a thin
    white halo, so it stays apart from a glyph it crosses even where its hue
    and the label's look alike, as dark green and dark gold do to a reader
    with red-green colour blindness (both have the same luminance).
    """
    ax.plot([x], [y], "o", markersize=7, markerfacecolor="none",
            markeredgecolor=MARK_COLOR, markeredgewidth=1.5, zorder=10,
            path_effects=[patheffects.withStroke(linewidth=3.5,
                                                 foreground="white")])


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
