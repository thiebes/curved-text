"""Edge behavior: the ``crowding`` control -- even spacing on a tight bend.

On a sharp bend the letters, set one after another by their flat advance widths,
crowd together on the inside (concave) edge of the curve where the rigid glyph
boxes fan into each other. ``crowding="curvature"`` opens an even letterspacing
gap that grows with the local curvature, so the inside edges stop colliding. The
gap is the same between every pair of letters, so the tracking stays even, and
it has a deadband: a gentle bend or a straight run is left untouched.

Top row: a sharp bend, where the correction visibly separates the letters.
Bottom row: a gentle bend of the same letters, where the bend is below the
deadband and the two columns are identical.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import PALETTE, figure, bare, save

WORD = "winds"
MODES = ["none", "curvature"]
FONTSIZE = 20
# Negative offset rides the inside (concave) edge of the bend, where the letters
# crowd worst -- and where they sit clear below the guide line rather than
# crossing it.
OFFSET = -13.0


def _arc(sweep_deg):
    """Unit-circle arc of angular width ``sweep_deg``, centered at the top and
    travelling left to right, shifted so its lowest point sits at ``y = 0``."""
    half = np.radians(sweep_deg) / 2.0
    th = np.linspace(np.pi / 2 + half, np.pi / 2 - half, 400)
    x, y = np.cos(th), np.sin(th)
    return x, y - y.min()


def make(images_dir):
    fig = figure(17, 9, font_size=8)
    axes = fig.subplots(2, 2)

    # Two bends of the same letters, both labelled on the inside of the bend.
    # The sharp arc is shown small (wide limits) so its displayed radius is tight
    # relative to the text -- the regime where the inside edges collide; the
    # gentle arc is a shallow slice shown large, so its displayed curvature falls
    # below the deadband and the correction is a no-op.
    rows = [
        ("sharp bend", _arc(180), (-2.6, 2.6), (-0.55, 1.25)),
        ("gentle bend", _arc(46), (-0.62, 0.62), (-0.30, 0.22)),
    ]

    for (row_label, (x, y), xlim, ylim), row in zip(rows, axes):
        for ax, mode in zip(row, MODES):
            bare(ax)
            ax.set_aspect("equal")
            ax.plot(x, y, color=PALETTE["blue"], linewidth=2)
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)
            curved_text(ax, x, y, WORD, pos=0.5, anchor="center", offset=OFFSET,
                        crowding=mode, color=PALETTE["gold"], fontsize=FONTSIZE)
        row[0].set_ylabel(row_label, labelpad=10)
        row[0].set_axis_on()
        row[0].set_xticks([])
        row[0].set_yticks([])
        for spine in row[0].spines.values():
            spine.set_visible(False)

    for ax, mode in zip(axes[0], MODES):
        ax.set_title(f'crowding="{mode}"')

    path = os.path.join(images_dir, "13_crowding.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
