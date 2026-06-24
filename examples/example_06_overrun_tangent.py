"""Tier 3: an overrunning label rides the end tangent, it is not clipped.

A long label on a short curve, anchored so it begins on the curve and runs
past the end. Rather than clip or bunch the overrunning glyphs, ``CurvedText``
extends the curve along its end tangent and places them on that straight line
(dashed). The behaviour is guarded by the test suite.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import SPANISH, figure, bare, caption, save


def make(images_dir):
    fig = figure(15, 7, font_size=10)
    ax = fig.subplots()
    bare(ax)

    x = np.linspace(0, 1, 60)
    y = 0.6 * np.sin(np.pi * x)
    ax.plot(x, y, color=SPANISH["indigo"], linewidth=2)

    # The end tangent, extended -- the straight line the overrun rides.
    dx, dy = x[-1] - x[-2], y[-1] - y[-2]
    norm = np.hypot(dx, dy)
    ux, uy = dx / norm, dy / norm
    ext = 0.9
    ax.plot([x[-1], x[-1] + ux * ext], [y[-1], y[-1] + uy * ext],
            linestyle="--", color="0.6", linewidth=1.2)

    ax.set_xlim(-0.05, 1.75)
    ax.set_ylim(-0.55, 0.85)

    curved_text(ax, x, y, "this label overruns the curve end",
                pos=0.55, anchor="start", offset=6.0,
                color=SPANISH["flag_red"], fontsize=12)

    caption(ax, 'pos=0.55, anchor="start"  (curve solid, tangent dashed)')

    path = os.path.join(images_dir, "06_overrun_tangent.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
