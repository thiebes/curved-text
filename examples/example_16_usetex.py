"""Tier 1: curved labels typeset by LaTeX.

With matplotlib's ``text.usetex`` rcParam on, LaTeX typesets every text in the
figure -- tick labels, axis labels, and the curved labels alike -- so the labels
along the curves match the rest of the figure. This is the direct-labeling
figure (example 01) drawn under usetex.

The figure needs ``latex``, and ``dvipng`` for the tick and axis labels, as any
matplotlib usetex figure on the Agg backend does. Without them the script skips
the figure.
"""
from __future__ import annotations

import os
import shutil

import matplotlib as mpl
import numpy as np

from curved_text import curved_text
from _style import PALETTE, figure, data_axes, save

SERIES = [
    (1.5, PALETTE["blue"], 0.30),
    (3.0, PALETTE["gold"], 0.42),
    (6.0, PALETTE["green"], 0.58),
]
TOOLS = ("latex", "dvipng")


def make(images_dir):
    missing = [tool for tool in TOOLS if shutil.which(tool) is None]
    if missing:
        print(f"  (skipped 16_usetex: {', '.join(missing)} not installed)")
        return None

    with mpl.rc_context({"text.usetex": True, "font.family": "serif"}):
        fig = figure(12, 8, font_size=10)
        ax = data_axes(fig.subplots(), font_size=10)
        t = np.linspace(0, 10, 200)
        for tau, color, pos in SERIES:
            temp = 100.0 * np.exp(-t / tau)
            ax.plot(t, temp, color=color, linewidth=2)
            curved_text(ax, t, temp, rf"$\tau = {tau:g}\,\mathrm{{s}}$",
                        pos=pos, anchor="center", offset=7.0,
                        color=color, fontsize=10)
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 105)
        ax.set_xlabel(r"time $t\ (\mathrm{s})$")
        ax.set_ylabel(r"temperature $T\ ({}^{\circ}\mathrm{C})$")

        path = os.path.join(images_dir, "16_usetex.png")
        return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
