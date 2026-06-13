# curved-text

[![CI](https://github.com/thiebes/curved-text/actions/workflows/ci.yml/badge.svg)](https://github.com/thiebes/curved-text/actions/workflows/ci.yml)

Draw text that follows an arbitrary curve in [matplotlib](https://matplotlib.org/).

![Direct labeling versus a legend](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/01_direct_labeling.png)

Label curves along their own paths instead of in a legend, so the eye never
leaves the data to decode a colour key.

Each character is placed in display coordinates and rotated to the chord across
its own advance, which follows the curve's local tangent while staying smooth
even when the curve is coarsely sampled. The layout is recomputed on every draw,
so the label keeps following the curve through layout, resizing, and interactive
panning or zooming. Placement is controlled by three independent parameters:

- `pos` -- where the label is anchored along the curve, as a fraction of arc
  length (`0.0` = first point, `1.0` = last).
- `anchor` -- which part of the label lands at `pos`: `"start"`, `"center"`, or
  `"end"`.
- `offset` -- a perpendicular shift off the curve, in typographic points, along
  the normal of the label's chord (positive is above a left-to-right curve).

A label that overruns either end of the curve is not clipped: the curve is
extended along its end tangent and the overrunning glyphs sit on that straight
extension.

If you know LaTeX, this is matplotlib's analogue of TikZ's `text along path`
decoration (from `decorations.text`): `pos`/`anchor` play the role of `text
align` and the indents, `offset` plays the role of `raise`, and overrunning
text rides the tangent extension instead of being truncated at the path's end.

## Install

```bash
pip install curved-text
```

Or, from a clone, an editable install:

```bash
pip install -e .
```

## Usage

```python
import numpy as np
import matplotlib.pyplot as plt
from curved_text import curved_text

x = np.linspace(0, 2 * np.pi, 400)
y = np.sin(x)

fig, ax = plt.subplots()
ax.plot(x, y)
curved_text(ax, x, y, "text that follows the curve",
            pos=0.5, anchor="center", offset=6.0, color="C3")
plt.show()
```

![A label following a sine wave](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/02_sine_hello.png)

More worked examples -- the three placement controls, overrun behaviour, and
integration with seaborn and pandas -- are in [examples/](examples/README.md).

The object-oriented form is also available:

```python
from curved_text import CurvedText

CurvedText(x, y, "along the curve", ax, pos=0.2, anchor="start", offset=4.0)
```

Note the axes argument position: the `CurvedText` class takes it after `x, y,
text` (matching `matplotlib.text.Text`), while the `curved_text` function takes it
first (matching matplotlib's axes-first helper functions).

Any extra keyword arguments (`color`, `fontsize`, `alpha`, `fontfamily`, ...) are
passed through to each character's `matplotlib.text.Text`.

## Mathtext

A `$...$` run in the label is laid out by matplotlib's
[mathtext](https://matplotlib.org/stable/users/explain/text/mathtext.html)
engine and bent through the same arc-length frame as plain text. Every glyph
outline and rule box is mapped through the curve, so radicals, fractions, and
sized delimiters stay connected and follow it at any curvature. Plain and math
runs mix freely in one string:

```python
curved_text(ax, x, y, r"flux $\propto \sqrt{D_{\mathrm{eff}}}\,(L/L_0)^2$",
            pos=0.5, anchor="center", offset=8.0)
```

![A mathtext expression following a sine wave](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/10_mathtext.png)

Pass `parse_math=False` to treat dollar signs literally. Tall expressions
compress vertically on the inside of tight bends, so choose the label size
relative to the curvature. `text.usetex` is not supported.

## Works with seaborn, pandas, and other matplotlib-backed libraries

`curved_text` needs a `matplotlib.axes.Axes`, so it works with any library that
draws on matplotlib. seaborn's axes-level functions return an `Axes`, its
figure-level functions expose one through `.axes`, and `pandas` `DataFrame.plot`
returns an `Axes` as well. Pass that axes in directly:

```python
import seaborn as sns

ax = sns.lineplot(data=df, x="x", y="y")
curved_text(ax, df["x"], df["y"], "along the curve",
            pos=0.5, anchor="center", offset=6.0)
```

## Notes

- The curve `(x, y)` should be ordered along the curve (monotonic in arc length)
  and have at least two points.
- Arc length and the offset are computed in display space, so spacing and the
  offset are correct at any DPI and figure size.
- The curve should be smooth relative to the glyph size. Each glyph (and each
  mathtext run) follows the local tangent, so when the curve reverses direction
  within a glyph's width -- as raw noisy data does -- the label collides with
  itself. Label a smoothed or fitted trend line rather than the raw samples.

## Related

[matplotlib-label-lines](https://github.com/cphyc/matplotlib-label-lines) labels
one or many lines inline at a chosen or automatically picked point, each label
rotated to the local slope. It is the quickest way to replace a legend across a
set of lines. `curved-text` solves the adjacent problem: making a single string
(plain or mathtext) follow the curve character by character, with arc-length
placement and a perpendicular offset, recomputed on every draw. Reach for
label-lines to drop legend labels onto several lines, and for curved-text to
make text ride a path. In the ggplot2 world,
[geomtextpath](https://github.com/AllanCameron/geomtextpath) covers similar
text-on-path ground.

## License

MIT
