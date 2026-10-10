"""The label stays on its curve while the view pans and zooms.

The animated counterpart of figure 07: one call, one label, and axis limits
that change every frame, as interactive panning and zooming change them.
Layout is recomputed on every draw, in display space, so the label follows
the curve through each change of scale without stretching or shearing. The
view eases in toward the label, pans along the curve, and eases back out, so
the animation loops without a jump.
"""
from __future__ import annotations

import os

import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter

from curved_text import curved_text
from _style import CURVE_COLOR, DPI, LABEL_COLOR, data_axes, figure

FRAMES = 48
FPS = 12
# The view at the two ends of the loop, as (x centre, x half width, y half
# height): wide and centred on the curve, then close in on the label.
WIDE = (9.0, 9.5, 1.2)
CLOSE = (6.2, 2.4, 0.5)
# The label rides the rising slope after the first trough, centred on it, so
# it stays in the close view.
LABEL_STRETCH = (4.9, 7.5)


def _view(frame):
    """The view at ``frame``: out to in and back, eased at both ends."""
    phase = 0.5 - 0.5 * np.cos(2 * np.pi * frame / FRAMES)
    return [wide + (close - wide) * phase for wide, close in zip(WIDE, CLOSE)]


def make(images_dir):
    fig = figure(17, 7.5, font_size=9)
    ax = data_axes(fig.subplots())

    x = np.linspace(0, 6 * np.pi, 1200)
    y = np.exp(-x / 12.0) * np.sin(x)
    ax.plot(x, y, color=CURVE_COLOR, linewidth=2)
    stretch = (x >= LABEL_STRETCH[0]) & (x <= LABEL_STRETCH[1])
    curved_text(ax, x[stretch], y[stretch], "stays on the curve", pos=0.5,
                anchor="center", offset=7.0, color=LABEL_COLOR, fontsize=11)

    def update(frame):
        centre, half_width, half_height = _view(frame)
        ax.set_xlim(centre - half_width, centre + half_width)
        ax.set_ylim(-half_height, half_height)
        return []

    animation = FuncAnimation(fig, update, frames=FRAMES)
    path = os.path.join(images_dir, "25_pan_zoom.gif")
    animation.save(path, writer=PillowWriter(fps=FPS), dpi=DPI)
    return path


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
