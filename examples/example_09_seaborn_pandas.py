"""Tier 4: any matplotlib-backed axes works (seaborn / pandas).

``curved_text`` only needs a ``matplotlib.axes.Axes``, so it composes with any
library that draws on matplotlib. This example uses seaborn if it is installed
and otherwise skips cleanly -- seaborn and pandas are not dependencies of
curved-text.
"""
from __future__ import annotations

import os

import numpy as np

from curved_text import curved_text
from _style import PALETTE, figure, data_axes, save


def make(images_dir):
    try:
        import pandas as pd
        import seaborn as sns
    except ImportError:
        print("  (skipped 09_seaborn_pandas: seaborn/pandas not installed)")
        return None

    x = np.linspace(0, 10, 200)
    df = pd.DataFrame({"x": x, "y": np.sqrt(x)})

    fig = figure(12, 8, font_size=10)
    ax = fig.subplots()
    sns.lineplot(data=df, x="x", y="y", ax=ax, color=PALETTE["blue"],
                 linewidth=2)
    data_axes(ax)
    curved_text(ax, df["x"], df["y"], "drawn on a seaborn axes",
                pos=0.5, anchor="center", offset=8.0,
                color=PALETTE["gold"], fontsize=11)

    path = os.path.join(images_dir, "09_seaborn_pandas.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
