"""The label stays on its curve while the view zooms and pans.

The animated counterpart of figure 07: one call, one label, and axis limits
that change every frame, as interactive zooming and panning change them. The
view zooms in toward the label, pans along the curve, and zooms back out to
where it began, so the loop has no jump. Layout is recomputed on every draw,
in display space, so the label follows the curve through each change of scale
and position without stretching or shearing. Only the limits change: the tick
labels have a fixed width and the axes box is fixed after the first draw, so
nothing else on the figure moves.
"""
from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.ticker import FormatStrFormatter

from curved_text import curved_text
from _style import CURVE_COLOR, DPI, LABEL_COLOR, data_axes, figure

# GIF frame times are whole hundredths of a second, so the rate divides 100.
FPS = 10
# Each of the three moves (zoom in, pan, zoom out) takes this many frames.
MOVE_FRAMES = 20
# The views the loop passes through, as (x centre, x half width, y half
# height): the whole curve; close in on the label; the same close view panned
# along the curve. The label stays in view throughout.
WHOLE = (3 * np.pi, 9.5, 1.2)
CLOSE_START = (5.4, 2.4, 0.5)
CLOSE_END = (7.0, 2.4, 0.5)
VIEWS = [WHOLE, CLOSE_START, CLOSE_END]
# The label rides the rising slope after the first trough, centred on it, so
# it stays in the close view.
LABEL_STRETCH = (4.9, 7.5)


def _view(frame):
    """The view at ``frame``, eased to a stop at the end of each move."""
    move, step = divmod(frame, MOVE_FRAMES)
    start, end = VIEWS[move], VIEWS[(move + 1) % len(VIEWS)]
    eased = 0.5 - 0.5 * np.cos(np.pi * step / MOVE_FRAMES)
    return [a + (b - a) * eased for a, b in zip(start, end)]


def _freeze_layout(fig):
    """Keep the axes box where constrained layout put it, so changing tick
    labels cannot shift it from frame to frame."""
    fig.canvas.draw()
    box = fig.axes[0].get_position().frozen()
    if hasattr(fig, "set_layout_engine"):
        fig.set_layout_engine("none")
    else:  # matplotlib 3.5
        fig.set_constrained_layout(False)
    fig.axes[0].set_position(box)


def make(images_dir):
    fig = figure(17, 7.5, font_size=9)
    ax = data_axes(fig.subplots())

    x = np.linspace(0, 6 * np.pi, 1200)
    y = np.exp(-x / 12.0) * np.sin(x)
    ax.plot(x, y, color=CURVE_COLOR, linewidth=2)
    stretch = (x >= LABEL_STRETCH[0]) & (x <= LABEL_STRETCH[1])
    curved_text(ax, x[stretch], y[stretch], "stays on the curve", pos=0.5,
                anchor="center", offset=7.0, color=LABEL_COLOR, fontsize=11)

    # Tick labels of a fixed width, so the layout does not depend on the view.
    ax.xaxis.set_major_formatter(FormatStrFormatter("%.1f"))
    ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    centre, half_width, half_height = _view(0)
    ax.set_xlim(centre - half_width, centre + half_width)
    ax.set_ylim(-half_height, half_height)
    _freeze_layout(fig)

    def update(frame):
        centre, half_width, half_height = _view(frame)
        ax.set_xlim(centre - half_width, centre + half_width)
        ax.set_ylim(-half_height, half_height)

    animation = FuncAnimation(fig, update, frames=MOVE_FRAMES * len(VIEWS))
    path = os.path.join(images_dir, "25_pan_zoom.gif")
    animation.save(path, writer=PillowWriter(fps=FPS), dpi=DPI)
    plt.close(fig)
    return path


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
