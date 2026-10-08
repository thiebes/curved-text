"""Gaps in the curve: the label rides the stretch that holds its anchor.

A curve breaks where it has no value to draw, and the label sits on the
stretch of curve that holds its anchor, with ``pos`` measured along the drawn
length. (a) NaN points: the square root of a cosine is undefined where the
cosine is negative. (b) Masked points: a tangent masked where it runs off
toward its poles. (c) Zeros on a log axis, which has no place for them:
``10 ** cos(x)``, set to zero where the cosine falls below -0.5. The axis
masks them (``nonpositive="mask"``), so the plotted line breaks where the
label's stretch does, and its axis shows the logarithmic scale. Every panel
makes the same call, ``pos=0.5``; in (c) the stretches are symmetric about
the middle of the curve, so the label lands on the middle peak.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import (CURVE_COLOR, LABEL_COLOR, bare, caption, data_axes, figure,
                    panel_letters, save)


def make(images_dir):
    fig = figure(17, 5.5, font_size=8)
    axes = fig.subplots(1, 3)

    x = np.linspace(0, 4 * np.pi, 800)
    with np.errstate(invalid="ignore"):
        root = np.sqrt(np.cos(x))
    t = np.tan(x / 2)
    tangent = np.ma.masked_where(np.abs(t) > 4, t)
    peaks = np.where(np.cos(x) > -0.5, 10 ** np.cos(x), 0.0)
    panels = [
        (root, (-0.2, 1.4), None,
         "y = np.sqrt(np.cos(x))\n# NaN where cos(x) < 0"),
        (tangent, (-4.5, 4.5), None,
         "t = np.tan(x / 2)\ny = np.ma.masked_where(\n    np.abs(t) > 4, t)"),
        (peaks, (0.2, 20.0), "log",
         'y = np.where(np.cos(x) > -0.5,\n'
         '             10 ** np.cos(x), 0)\n'
         'ax.set_yscale("log",\n'
         '              nonpositive="mask")'),
    ]
    for ax, (y, ylim, scale, call) in zip(axes, panels):
        if scale == "log":
            # The scale is the subject here, so its axis stays visible.
            data_axes(ax, font_size=8)
            ax.set_xticks([])
            ax.set_yscale("log", nonpositive="mask")
        else:
            bare(ax)
        ax.plot(x, y, color=CURVE_COLOR, linewidth=2)
        # Room at the sides, so the space between panels reads as a margin,
        # not as another gap.
        ax.set_xlim(-0.8, 4 * np.pi + 0.8)
        ax.set_ylim(*ylim)
        curved_text(ax, x, y, "a stretch", pos=0.5, anchor="center",
                    offset=6.0, color=LABEL_COLOR, fontsize=10)
        caption(ax, call)
    panel_letters(axes)

    path = os.path.join(images_dir, "26_gaps.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
