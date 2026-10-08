"""Gaps in the curve: the label rides the stretch that holds its anchor.

A curve breaks where ``plot`` breaks it, and the label sits on the stretch of
curve that holds its anchor, with ``pos`` measured along the drawn length.
(a) NaN points: the square root of a cosine is undefined where the cosine is
negative. (b) Masked points: a tangent masked where it runs off toward its
poles. (c) A log axis, which has no place for the values of 0 or less where
the curve dips below zero.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import (CURVE_COLOR, LABEL_COLOR, bare, caption, figure,
                    panel_letters, save)


def make(images_dir):
    fig = figure(17, 5.5, font_size=8)
    axes = fig.subplots(1, 3)

    x = np.linspace(0, 4 * np.pi, 800)
    with np.errstate(invalid="ignore"):
        root = np.sqrt(np.cos(x))
    tangent = np.ma.masked_where(np.abs(np.tan(x / 2)) > 4, np.tan(x / 2))
    dips = 1.0 + 1.5 * np.sin(x)
    panels = [
        (root, (-0.2, 1.4), "linear",
         "y = np.sqrt(np.cos(x))\n# NaN where cos(x) < 0"),
        (tangent, (-4.5, 4.5), "linear",
         "y = np.ma.masked_where(\n    abs(t) > 4, t)"),
        (dips, (0.05, 4.0), "log", 'ax.set_yscale("log")'),
    ]
    for ax, (y, ylim, scale, call) in zip(axes, panels):
        bare(ax)
        ax.plot(x, y, color=CURVE_COLOR, linewidth=2)
        ax.set_yscale(scale)
        ax.set_xlim(0, 4 * np.pi)
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
