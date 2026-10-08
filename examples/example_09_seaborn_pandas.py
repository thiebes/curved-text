"""Tier 4: any matplotlib-backed axes works (seaborn / pandas).

``curved_text`` only needs a ``matplotlib.axes.Axes``, so it composes with any
library that draws on matplotlib. Here pandas reads the ``Stocks.csv`` sample
data that ships with matplotlib, and seaborn draws two stock market indexes
in its own ``whitegrid`` theme, applied in a context so it does not leak into
other figures. Each line is labelled along its path instead of with
seaborn's legend. This example skips cleanly when seaborn or pandas is
missing (neither is a dependency of curved-text), or when matplotlib is too
old to ship ``Stocks.csv``.
"""
from __future__ import annotations

import os

from curved_text import curved_text
from _style import PALETTE, TEXT, figure, sample_data, save, smooth_path

# Column, label, line and text colour, the dates the label rides (centred on
# them), and its offset in points: positive above the line, negative below.
SERIES = [
    ("^IXIC", "NASDAQ Composite", PALETTE["blue"], TEXT["blue"],
     ("2010-01-01", "2017-01-01"), 8.0),
    ("^GSPC", "S&P 500", PALETTE["gold"], TEXT["gold"],
     ("2010-01-01", "2017-01-01"), -8.0),
]
WINDOW_MONTHS = 12
# The width, in months, of the Gaussian that smooths each label's path.
LABEL_SMOOTHING_MONTHS = 3.0


def make(images_dir):
    try:
        import pandas as pd
        import seaborn as sns
    except ImportError:
        print("  (skipped 09_seaborn_pandas: seaborn/pandas not installed)")
        return None

    path = sample_data("Stocks.csv")
    if path is None:
        print("  (skipped 09_seaborn_pandas: this matplotlib has no Stocks.csv)")
        return None
    stocks = (pd.read_csv(path, comment="#", parse_dates=["Date"])
              .dropna(how="all", subset=[column for column, *_ in SERIES])
              .set_index("Date"))
    # A 12-month rolling mean, dated at the middle of its window.
    smoothed = stocks.rolling(WINDOW_MONTHS, center=True).mean()
    long_form = (smoothed[[column for column, *_ in SERIES]]
                 .reset_index()
                 .melt(id_vars="Date", var_name="index", value_name="level")
                 .dropna())

    with sns.axes_style("whitegrid"):
        fig = figure(17, 9, font_size=9)
        ax = fig.subplots()
        sns.lineplot(data=long_form, x="Date", y="level", hue="index",
                     palette={column: line for column, _, line, *_ in SERIES},
                     linewidth=2, legend=False, ax=ax)
        for column, label, _, text, (start, end), offset in SERIES:
            line_values = smoothed[column].dropna()
            label_path = pd.Series(
                smooth_path(line_values, LABEL_SMOOTHING_MONTHS),
                index=line_values.index).loc[start:end]
            curved_text(ax, label_path.index, label_path.to_numpy(), label,
                        pos=0.5, anchor="center", offset=offset, color=text,
                        fontsize=9)
        ax.set_xlabel("")
        ax.set_ylabel("index level")
        sns.despine(ax=ax)

        path = os.path.join(images_dir, "09_seaborn_pandas.png")
        return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
