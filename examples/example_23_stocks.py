"""Stock prices on real dates, with each line labeled along a smoothed copy.

Monthly values from the ``Stocks.csv`` sample data, January 1990 to June 2022:
adjusted closing prices for three stocks and the S&P 500 price index, each
divided by its January 1990 value and smoothed with a rolling mean over
``WINDOW_MONTHS``. Each label follows a smoothed copy of its line, filtered
further by a Gaussian about one character wide. The copy is never drawn. The
file is read with the ``csv`` module, so the figure runs without the
``examples`` extra, and it is skipped where matplotlib does not include
``Stocks.csv``.
"""
from __future__ import annotations

import csv
import os

import numpy as np
from matplotlib.ticker import StrMethodFormatter

from curved_text import curved_text
from _style import (REFERENCE_COLOR, TEXT, data_axes, figure, sample_data,
                    save, smooth_path)

# Column, label, colour of the line and its label, the dates the label rides
# (centred on them), and its offset in points: positive above the line,
# negative below. The reference series comes first, so it is drawn beneath
# the others.
SERIES = [
    ("^GSPC", "S&P 500", REFERENCE_COLOR, ("2013-06-01", "2019-06-01"), -8.0),
    ("MSFT", "Microsoft", TEXT["blue"], ("2013-01-01", "2019-01-01"), 8.0),
    ("IBM", "IBM", TEXT["green"], ("2010-06-01", "2015-06-01"), 8.0),
    ("XRX", "Xerox", TEXT["gold"], ("2016-01-01", "2019-06-01"), 8.0),
]
WINDOW_MONTHS = 12
# The standard deviation, in months, of the Gaussian that smooths each label's
# path: about the width of a letter on this axis.
LABEL_SMOOTHING_MONTHS = 3.0


def _read_stocks(path):
    """Dates and the column-to-prices table, without the dividend-date rows,
    which have no prices, and without a row that repeats the one before it,
    as the file's last row repeats June 2022."""
    with open(path, newline="") as f:
        rows = [row for row in csv.reader(f)
                if row and not row[0].startswith("#")]
    header, rows = rows[0], [row for row in rows[1:] if any(row[1:])]
    rows = [row for i, row in enumerate(rows)
            if i == 0 or row[1:] != rows[i - 1][1:]]
    dates = np.array([row[0] for row in rows], dtype="datetime64[D]")
    column_to_prices = {
        name: np.array([float(row[i]) if row[i] else np.nan for row in rows])
        for i, name in enumerate(header) if i > 0
    }
    return dates, column_to_prices


def _rolling_mean(values, window):
    """The mean of each run of ``window`` consecutive values."""
    return np.convolve(values, np.ones(window) / window, mode="valid")


def make(images_dir):
    path = sample_data("Stocks.csv")
    if path is None:
        print("  (skipped 23_stocks: this matplotlib has no Stocks.csv)")
        return None
    dates, column_to_prices = _read_stocks(path)
    # Each smoothed value is dated at the middle of its window.
    smoothed_dates = dates[WINDOW_MONTHS // 2:][:len(dates) - WINDOW_MONTHS + 1]

    fig = figure(17, 10, font_size=9)
    ax = data_axes(fig.subplots())
    for column, label, color, (start, end), offset in SERIES:
        prices = column_to_prices[column]
        relative = _rolling_mean(prices / prices[0], WINDOW_MONTHS)
        ax.plot(smoothed_dates, relative, color=color, linewidth=2)
        span = ((smoothed_dates >= np.datetime64(start))
                & (smoothed_dates <= np.datetime64(end)))
        label_path = smooth_path(relative, LABEL_SMOOTHING_MONTHS, log=True)[span]
        curved_text(ax, smoothed_dates[span], label_path, label, pos=0.5,
                    anchor="center", offset=offset, color=color, fontsize=9)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:g}"))
    ax.set_ylabel("value relative to January 1990")

    path = os.path.join(images_dir, "23_stocks.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
