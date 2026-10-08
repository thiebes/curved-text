"""Tier 1: direct labeling replaces the legend.

The case for the tool, in one figure. Left: three cooling curves with a
conventional legend -- the eye must leave the data, find the key, decode a
colour, and come back. Right: the same curves labeled along their own paths.
No legend, no colour key, no round trip.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import PALETTE, TEXT, data_axes, figure, panel_letters, save

SERIES = [
    (1.5, "blue", 0.30),
    (3.0, "gold", 0.42),
    (6.0, "green", 0.58),
]


def _curves(ax):
    t = np.linspace(0, 10, 200)
    out = []
    for tau, hue, pos in SERIES:
        temp = 100.0 * np.exp(-t / tau)
        ax.plot(t, temp, color=PALETTE[hue], linewidth=2)
        out.append((t, temp, tau, hue, pos))
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
    for _, _, tau, hue, _ in curves:
        ax_legend.plot([], [], color=PALETTE[hue], linewidth=2,
                       label=f"τ = {tau:g} s")
    ax_legend.legend(frameon=False, handlelength=1.2)

    curves = _curves(ax_direct)
    data_axes(ax_direct)
    for t, temp, tau, hue, pos in curves:
        curved_text(ax_direct, t, temp, f"τ = {tau:g} s",
                    pos=pos, anchor="center", offset=9.0,
                    color=TEXT[hue], fontsize=9)

    panel_letters([ax_legend, ax_direct])
    path = os.path.join(images_dir, "01_direct_labeling.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
