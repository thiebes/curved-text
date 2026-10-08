"""Text around a circle and along a spiral.

(a) A circle labelled on both halves, each traced from nine o'clock to three
o'clock: the top half clockwise and the bottom half counterclockwise, so both
labels run left to right on screen and read upright, outside the circle. (b) An
Archimedean spiral, r = aθ, traced clockwise from near its centre outward,
with a sentence on the inside of its turns, which keep an even spacing of
2πa. Along the bottom of each turn the text runs right to left on screen and
reads upside down, as figure 17 explains.
"""
from __future__ import annotations

import os

import numpy as np
from matplotlib.patches import Circle

from curved_text import curved_text
from _style import CURVE_COLOR, LABEL_COLOR, bare, figure, panel_letters, save

CIRCLE_TOP = r"its circumference is $2\pi r$"
CIRCLE_BOTTOM = r"and its area is $\pi r^2$"
SPIRAL_TEXT = (r"an Archimedean spiral, $r = a\theta$, keeps the same distance "
               r"between its turns, so a long sentence can wind out from its "
               r"centre at an even spacing")
# The spiral's growth per radian, a, so its turns are 2πa apart; and the
# angles it spans: from just over half a turn, so the first words have room
# on the inside, to where the sentence ends.
SPIRAL_A = 1.0
SPIRAL_THETA = (1.2 * np.pi, 5.05 * np.pi)
# Half the width of the spiral's axes, in data units, around the spiral's
# centre: it sets the scale, and so where the sentence ends.
SPIRAL_HALF_SPAN = 18.0


def make(images_dir):
    fig = figure(17, 8.5, font_size=9)
    ax_circle, ax_spiral = fig.subplots(1, 2)

    # A closed patch, so the circle has no seam where a line would start.
    ax_circle.add_patch(Circle((0, 0), 1, fill=False, edgecolor=CURVE_COLOR,
                               linewidth=1.5))
    # Each half is traced from nine o'clock to three o'clock, so both labels
    # run left to right on screen and read upright: the top half clockwise,
    # with the label to its left (outside), and the bottom half
    # counterclockwise, with the label to its right (outside again).
    top = np.linspace(np.pi, 0, 361)
    bottom = np.linspace(np.pi, 2 * np.pi, 361)
    for half, text, offset in ((top, CIRCLE_TOP, 7.0),
                               (bottom, CIRCLE_BOTTOM, -7.0)):
        curved_text(ax_circle, np.cos(half), np.sin(half), text, pos=0.5,
                    anchor="center", offset=offset, color=LABEL_COLOR,
                    fontsize=11)
    ax_circle.set_xlim(-1.35, 1.35)
    ax_circle.set_ylim(-1.35, 1.35)

    # Clockwise from the centre outward: the angle increases, and the minus
    # sign on y turns the counterclockwise trace clockwise.
    theta = np.linspace(*SPIRAL_THETA, 4000)
    r = SPIRAL_A * theta
    x, y = r * np.cos(theta), -r * np.sin(theta)
    ax_spiral.plot(x, y, color=CURVE_COLOR, linewidth=1.0)
    # A negative offset puts the text to the right of a clockwise travel:
    # inside each turn.
    curved_text(ax_spiral, x, y, SPIRAL_TEXT, pos=0.0, anchor="start",
                offset=-5.0, color=LABEL_COLOR, fontsize=9)
    # Centred on the spiral's extent, not on its origin, which sits off
    # centre in the drawn shape.
    centre_x = (x.min() + x.max()) / 2
    centre_y = (y.min() + y.max()) / 2
    ax_spiral.set_xlim(centre_x - SPIRAL_HALF_SPAN, centre_x + SPIRAL_HALF_SPAN)
    ax_spiral.set_ylim(centre_y - SPIRAL_HALF_SPAN, centre_y + SPIRAL_HALF_SPAN)

    for ax in (ax_circle, ax_spiral):
        bare(ax)
        ax.set_aspect("equal")
    panel_letters([ax_circle, ax_spiral])

    path = os.path.join(images_dir, "22_circle_spiral.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
