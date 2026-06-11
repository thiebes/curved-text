"""Tier 1: direct labeling replaces the legend.

The case for the tool, in one figure. Left: three cooling curves with a
conventional legend -- the eye must leave the data, find the key, decode a
colour, and come back. Right: the same curves labeled along their own paths.
No legend, no colour key, no round trip.
"""
from __future__ import annotations

import os

import numpy as np
import matplotlib.pyplot as plt

from curved_text import curved_text
from _style import PALETTE, figure, data_axes, save

SERIES = [
    (1.5, PALETTE["blue"], 0.30),
    (3.0, PALETTE["gold"], 0.42),
    (6.0, PALETTE["green"], 0.58),
]


def _curves(ax):
    t = np.linspace(0, 10, 200)
    out = []
    for tau, color, pos in SERIES:
        temp = 100.0 * np.exp(-t / tau)
        ax.plot(t, temp, color=color, linewidth=2)
        out.append((t, temp, tau, color, pos))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 105)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("temperature (°C)")
    return out


def make(images_dir):
    fig = figure(17, 7.5, font_size=9)
    ax_legend, ax_direct = fig.subplots(1, 2)

    curves = _curves(ax_legend)
    data_axes(ax_legend)
    for _, _, tau, color, _ in curves:
        ax_legend.plot([], [], color=color, linewidth=2,
                       label=f"τ = {tau:g} s")
    ax_legend.legend(frameon=False, handlelength=1.2)

    curves = _curves(ax_direct)
    data_axes(ax_direct)
    for t, temp, tau, color, pos in curves:
        curved_text(ax_direct, t, temp, f"τ = {tau:g} s",
                    pos=pos, anchor="center", offset=7.0,
                    color=color, fontsize=9)

    path = os.path.join(images_dir, "01_direct_labeling.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
