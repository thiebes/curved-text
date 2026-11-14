"""The ``smooth`` control: a label on a line of measured data.

Monthly closing prices of Microsoft from the ``Stocks.csv`` sample data,
smoothed with a rolling mean over six months, on a log axis. The line still
wiggles at about the width of a letter. In (a) the label rides the line as it
is, so neighboring letters tilt and step with each wiggle. In (b),
``smooth="auto"`` smooths the path the label rides, by about three quarters of
an em, where it wiggles under the label, and the letters sit evenly. The line
is drawn as it is in both panels. The figure is skipped where matplotlib does
not include ``Stocks.csv``.
"""
from __future__ import annotations

import os

import numpy as np
from matplotlib.ticker import StrMethodFormatter

from curved_text import curved_text
from _style import (CURVE_COLOR, LABEL_COLOR, caption, data_axes, figure,
                    panel_letters, read_stocks, rolling_mean, sample_data,
                    save)

WINDOW_MONTHS = 6
SPAN = ("2012-10-01", "2017-10-01")
FONTSIZE = 16
OFFSET = 14.0
MODES = [None, "auto"]


def make(images_dir):
    path = sample_data("Stocks.csv")
    if path is None:
        print("  (skipped 28_smooth: this matplotlib has no Stocks.csv)")
        return None
    dates, column_to_prices = read_stocks(path)
    prices = rolling_mean(column_to_prices["MSFT"], WINDOW_MONTHS)
    # Each smoothed value is dated at the middle of its window.
    dates = dates[WINDOW_MONTHS // 2:][:len(dates) - WINDOW_MONTHS + 1]
    span = (dates >= np.datetime64(SPAN[0])) & (dates <= np.datetime64(SPAN[1]))

    fig = figure(17, 9, font_size=8)
    axes = fig.subplots(1, 2, sharey=True)
    for ax, smooth in zip(axes, MODES):
        data_axes(ax, font_size=8)
        ax.plot(dates[span], prices[span], color=CURVE_COLOR, linewidth=2)
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(StrMethodFormatter("{x:g}"))
        ax.yaxis.set_minor_formatter(StrMethodFormatter("{x:g}"))
        ax.set_ylim(25, 80)
        curved_text(ax, dates[span], prices[span], "Microsoft", pos=0.5,
                    anchor="center", offset=OFFSET, color=LABEL_COLOR,
                    fontsize=FONTSIZE, smooth=smooth)
        caption(ax, f"smooth={smooth!r}".replace("'", '"'))
    axes[0].set_ylabel("price in dollars")
    panel_letters(axes)

    path = os.path.join(images_dir, "28_smooth.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
