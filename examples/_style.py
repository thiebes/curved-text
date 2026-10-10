"""Shared palette and helpers for the curved-text example gallery.

Follows the repo's plot conventions: the DICE palette with contrast-checked
text shades, white opaque background, constrained layout, sizes in
centimetres, explicit dpi. Most panels here are diagrams whose subject is the
text-on-curve geometry, so they hide their axes -- the curve is the data, and
bare quantitative ticks would be chartjunk. The figures that plot data (direct
labeling, its usetex version, the seaborn figure, and the applications on real
data or physical laws) keep axes with units, and so does the log-axis panel of
the gaps figure, whose subject is the scale, and the pan-and-zoom animation,
whose moving ticks are what show the view changing. Two data helpers sit here
as well: ``sample_data`` finds matplotlib's sample data, and ``smooth_path``
smooths the path a label rides on a line of real data.
"""
from __future__ import annotations

import os

import matplotlib.cbook as cbook
import matplotlib.patheffects as patheffects
import numpy as np
import matplotlib.pyplot as plt

# DICE palette set: blue / gold / green. These are the source hues; only blue
# is drawn as is, because DICE gold and green are too light to draw.
PALETTE = {"blue": "#003f7f", "gold": "#f7941e", "green": "#0cce6b"}
# The same hues dark enough for text, at least 4.5:1 against white by the WCAG 2
# contrast formula. DICE gold and green are 2.28:1 and 2.09:1, too light to
# read as text, and below the 3:1 that WCAG asks of lines and marks; DICE blue
# is 10.4:1 already. Every drawn colour comes from these shades.
TEXT = {
    "blue": "#003f7f",   # 10.41:1
    "gold": "#b06306",   # 4.53:1
    "green": "#088847",  # 4.54:1
}
# Colour roles in the diagrams, where the curve and the label are the subject:
# the curve in DICE blue, the label in dark gold, and an anchor mark (the
# point a label is placed from) as a dark green ring drawn above the label, so
# it never hides behind the text. One exception: 08 shows ``alpha``, which
# lightens its label, and only dark blue stays above 4.5:1 at alpha 0.85.
#
# In the data figures, each series draws its line and its label in one text
# shade, so the two match exactly and both pass. A reference series, which
# the others are read against (the Sun among the blackbodies, the S&P 500
# among the stocks), is near-black, and is drawn beneath the others so a
# coloured line that overlaps it stays on top.
CURVE_COLOR = PALETTE["blue"]
LABEL_COLOR = TEXT["gold"]
MARK_COLOR = TEXT["green"]
REFERENCE_COLOR = "0.15"  # 15.08:1
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
    """A ring at data point ``(x, y)`` in the anchor-mark colour.

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


def smooth_path(values, sigma, log=False):
    """``values`` smoothed by a Gaussian with a standard deviation of
    ``sigma`` samples, on a log scale if ``log``.

    Each end is padded with its own value, so the result has as many samples
    as ``values`` and covers the same span.

    A label on a line of real data rides this path rather than the line: even
    smoothed, a line of monthly data wiggles at the scale of a letter, which
    tilts neighbouring letters into each other. With ``sigma`` about a letter's
    width, the path follows the line without those wiggles.
    """
    values = np.asarray(values, dtype=float)
    reach = int(4 * sigma)
    kernel = np.exp(-0.5 * (np.arange(-reach, reach + 1) / sigma) ** 2)
    scaled = np.log(values) if log else values
    padded = np.concatenate([np.full(reach, scaled[0]), scaled,
                             np.full(reach, scaled[-1])])
    smoothed = np.convolve(padded, kernel / kernel.sum(), mode="valid")
    return np.exp(smoothed) if log else smoothed


def sample_data(name):
    """The path to one of matplotlib's sample data files, or ``None`` where the
    installed matplotlib does not ship it (3.5 has no ``Stocks.csv``)."""
    path = cbook.get_sample_data(name, asfileobj=False)
    return str(path) if os.path.exists(path) else None


def save(fig, path):
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path
