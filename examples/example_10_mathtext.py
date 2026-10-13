"""A mathtext expression along a gentle curve.

A ``$...$`` run in the label is bent along the curve like plain text, so the
radical (square-root sign), the parentheses, and the superscripts stay joined.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import CURVE_COLOR, LABEL_COLOR, bare, caption, figure, save


def make(images_dir):
    fig = figure(17, 7.9, font_size=11)
    ax = fig.subplots()
    bare(ax)

    x = np.linspace(0, 10, 400)
    y = 1.6 * np.sin(np.pi * x / 10.0)
    ax.plot(x, y, color=CURVE_COLOR, linewidth=2)
    ax.set_xlim(-0.3, 10.3)
    ax.set_ylim(-0.4, 2.6)

    curved_text(ax, x, y, r"$E = \sqrt{(pc)^2 + (mc^2)^2}$",
                pos=0.5, anchor="center", offset=14.0,
                color=LABEL_COLOR, fontsize=16)

    caption(ax, r'curved_text(ax, x, y, r"$E = \sqrt{(pc)^2 + (mc^2)^2}$",'
                "\n"
                r'            pos=0.5, anchor="center", offset=14.0)')

    path = os.path.join(images_dir, "10_mathtext.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
