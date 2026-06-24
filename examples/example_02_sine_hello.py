"""Tier 1: the canonical "hello world" -- one curve, one label riding it.

The README figure, rendered. A single centred label sits just above a sine
wave with a small perpendicular offset.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import SPANISH, figure, bare, caption, save


def make(images_dir):
    fig = figure(14, 6, font_size=11)
    ax = fig.subplots()
    bare(ax)

    x = np.linspace(0, 2 * np.pi, 400)
    y = np.sin(x)
    ax.plot(x, y, color=SPANISH["fern_green"], linewidth=2)
    ax.set_xlim(0, 2 * np.pi)
    ax.set_ylim(-1.4, 1.4)

    curved_text(ax, x, y, "text that follows the curve",
                pos=0.5, anchor="center", offset=8.0,
                color=SPANISH["indigo"], fontsize=13)

    caption(ax, 'curved_text(ax, x, y, "...", '
                'pos=0.5, anchor="center", offset=8.0)')

    path = os.path.join(images_dir, "02_sine_hello.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
