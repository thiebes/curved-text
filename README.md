# curved-text

[![Continuous integration status](https://github.com/thiebes/curved-text/actions/workflows/ci.yml/badge.svg)](https://github.com/thiebes/curved-text/actions/workflows/ci.yml)
[![Documentation build status](https://github.com/thiebes/curved-text/actions/workflows/docs.yml/badge.svg)](https://thiebes.github.io/curved-text/)
[![Digital Object Identifier (DOI) of the archived release on Zenodo](https://zenodo.org/badge/DOI/10.5281/zenodo.20725006.svg)](https://doi.org/10.5281/zenodo.20725006)

Draw text that follows an arbitrary curve in [matplotlib](https://matplotlib.org/).

A label along its own curve replaces a legend, so the reader does not look away
from the data to decode a color key. In (a) below, a legend identifies the
lines. In (b), the same lines carry labels along the curves.

![Two panels with the same three cooling curves. In (a), a legend decodes each line by color. In (b), each curve carries its own label, tau = 1.5 s, 3 s, or 6 s, along the curve, so no legend is needed.](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/01_direct_labeling.png)

The label is recomputed every time the figure is drawn, so it keeps following
the curve through layout changes, resizing, and interactive panning or zooming.

## Install

```bash
pip install curved-text
```

Requires Python 3.9 or later, matplotlib 3.5 or later, and numpy 1.20 or later.
seaborn and pandas are optional.

To work from a clone, install it in editable mode:

```bash
pip install -e .
```

The Gallery scripts need the extra dependencies. From a clone, run
`pip install -e ".[examples]"`.

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
            pos=0.5, anchor="center", offset=8.0,
            color="#b06306", fontsize=13)
plt.show()
```

The label follows the curve, and each character turns to match the curve under
it:

![A sine wave with the text 'text that follows the curve' placed along its falling part, each character turned to match the curve under it.](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/02_sine_hello.png)

More figures: [Gallery](https://thiebes.github.io/curved-text/gallery.html).
Every parameter: [application programming interface (API) reference](https://thiebes.github.io/curved-text/api.html).
Known limits (3D axes, blitting, text in vector files, and removing a label)
are listed under [Limits](#limits).

### Choosing a curve

- The curve `(x, y)` must be ordered along its length: each point comes after
  the one before it. It needs at least two points.
- The curve should be smooth relative to the text size: it should have no bend
  smaller than one character, or the glyphs overlap. Label a fitted or smoothed
  copy of the data and leave that copy unplotted. A polynomial fit
  (`numpy.polyfit`) works, and so does a Gaussian filter about one character
  wide. A short running mean usually does not.
- The label reads in the order of the points on screen. A curve that runs from
  right to left reads upside down: see Placement.
- The curve is in data coordinates, and the `transform` keyword is ignored. To
  place a label with axes fractions, convert the points to data coordinates
  first: `ax.transData.inverted().transform(ax.transAxes.transform(points))`.

### Placement

Four independent parameters control where the label sits:

- `pos` sets where the label is anchored along the curve, as a fraction of the
  curve's length. `0.0` is the start of the curve and `1.0` is its end. The
  default is `0.5`.
- `anchor` sets which part of the label lands at `pos`: `"start"`, `"center"`,
  or `"end"`. The default is `"center"`.
- `offset` shifts the label perpendicular to the curve, in points (1/72 inch).
  A positive value sits above a left-to-right curve. The default is `0.0`.
- `valign` sets which line of the text lies on the curve: `"center"`,
  `"baseline"`, `"ascender"`, or `"descender"`. The default is `"center"`. See
  [Vertical alignment (`valign`)](#vertical-alignment-valign) below.

The next figure sweeps `pos` from the first point to the last. The ring marks
the anchor point in each panel.

![Five panels of one arch-shaped curve with the word 'label' at pos = 0.0, 0.25, 0.5, 0.75, and 1.0. A ring marks the anchor point. It moves from the left end of the arch to the right end, and the label follows it.](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/03_pos_sweep.png)

The label reads in the order of the points as they appear on screen. If the
points run from right to left, the text is upside down. Reverse both arrays
(`x[::-1], y[::-1]`) to turn it upright. `pos` and `offset` also count from the
first point. The Gallery section [Why a label reads upside down: direction of
travel](https://thiebes.github.io/curved-text/gallery.html#why-a-label-reads-upside-down-direction-of-travel) shows
the cases.

If the label runs past either end of the curve, it is not cut off. The curve
continues straight in the direction it had at that end, and the extra glyphs sit
on that straight line.

### Curves with gaps and log axes

A curve with NaN (not a number), infinite, or masked points (points hidden by a
NumPy masked array) has gaps, as `plot` draws it. So does a curve with points
the axes cannot show. These are values of 0 or less on a log axis, and values
of 0 or less or 1 or more on a logit axis, whatever the `nonpositive` setting.

A stretch is a connected piece of the curve between gaps. `pos` counts only the
drawn length. The label follows the stretch that holds its anchor. It continues
straight past the ends of that stretch, over a gap if there is one, and never
continues onto another stretch. Lengths are measured on screen, so zooming can
move the anchor onto another stretch.

To label a curve with gaps, or scattered points, pass `curved_text` a smooth
curve that follows their overall shape, such as a fit or a running mean. Leave
that curve unplotted: the label never draws the curve it follows.

In the next figure, the label follows one stretch of three curves with gaps: NaN
points in (a), masked points in (b), and zeros on a log axis in (c).

![Three curves with gaps: NaN points in (a), masked points in (b), and zeros on a log axis in (c), where the plotted curve runs between about 0.3 and 10. Each curve breaks into separate stretches, and the label 'a stretch' follows only the middle stretch, the one that holds its anchor.](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/26_gaps.png)

### Text cut off at the axes edge

A label is clipped to the axes, as lines are. Glyphs that run past the edge of
the axes are cut there. matplotlib's own `ax.text` is not clipped by default.
Pass `clip_on=False` to draw the whole label wherever its curve goes. A tight
bounding box (`bbox_inches="tight"`) and constrained layout then make room for
it.

### Dates, categories, and units

The curve takes the same data `plot` does: dates (`datetime64`, `datetime`,
pandas dates), category strings, and values with units. The axes convert them
as they convert the plotted line, so the label stays on it.

```python
days = np.arange("2024-01-01", "2025-01-01", dtype="datetime64[D]")
# Day length at 40° N, from the sun's declination on each day of the year.
n = np.arange(days.size)
declination = np.radians(23.44) * np.sin(2 * np.pi * (n - 80) / 365)
hours = 24 / np.pi * np.arccos(-np.tan(np.radians(40)) * np.tan(declination))

fig, ax = plt.subplots()
ax.plot(days, hours)
curved_text(ax, days, hours, "day length at 40° N", pos=0.3, offset=6.0)
```

A label created before anything is plotted sets up the axis for its data, as
`plot` does. Category strings not yet on an axis are added to it, as ticks.
Data an axis cannot convert, such as strings on a date axis, raises
matplotlib's `ConversionError` when the label is made.

### The function and the class

The class form of the same call is [`CurvedText`](https://thiebes.github.io/curved-text/api.html):

```python
from curved_text import CurvedText

CurvedText(x, y, "along the curve", ax, pos=0.2, anchor="start", offset=4.0)
```

The `CurvedText` class takes the axes after `x, y, text`, matching
`matplotlib.text.Text`. The `curved_text` function takes it first, matching
matplotlib's axes-first helper functions. Passing the axes last to `curved_text`
raises `AttributeError`.

Extra keyword arguments are `Text` properties applied to every glyph, such as
`color`, `alpha`, `fontsize`, `fontfamily`, and `path_effects`. Properties that
describe one text box, such as `ha`, `va`, `bbox`, and `wrap`, have no effect,
and `transform` is replaced. Do not pass `rotation`: it changes the spacing of
the characters. The [API reference](https://thiebes.github.io/curved-text/api.html)
lists every property.

## Features

### Mathtext

A `$...$` run (a math run) in the label is laid out by matplotlib's
[mathtext](https://matplotlib.org/stable/users/explain/text/mathtext.html)
engine and then bent along the curve the way plain text is. Every part of the
expression follows the curve, including the bars of fractions and the overlines
of radicals (square-root signs). Plain and math runs mix freely in one string:

```python
curved_text(ax, x, y, r"$E = \sqrt{(pc)^2 + (mc^2)^2}$",
            pos=0.5, anchor="center", offset=14.0,
            color="#b06306", fontsize=16)
```

The whole expression bends with the curve:

![A mathtext expression, E = square root of ((pc) squared + (mc squared) squared), as a label above an arch-shaped curve. The square-root bar and the superscripts bend with the curve and stay connected.](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/10_mathtext.png)

Fractions, radicals, and large brackets stay joined while the radius of
curvature is larger than the height of the expression. On a tighter bend the
expression is squeezed along the curve. Where the radius falls below its height
on the concave side, it folds over itself: ink beyond the center of curvature
comes out mirrored. Choose the text size to suit the curvature.

Pass `parse_math=False` to treat dollar signs literally.

Plain words and math runs in one label share a single baseline. The math
symbols sit level with the surrounding plain text, and a superscript lifts only
the exponent, not the body. The alignment is built in, with no tuning:

```python
curved_text(ax, x, y, r"mass $m$ and speed $c$ give $E = mc^2$",
            valign="baseline")
```

The Gallery section [Plain words and math share one baseline](https://thiebes.github.io/curved-text/gallery.html#plain-words-and-math-share-one-baseline)
shows the symbols level with the words, with only the exponent raised.

### LaTeX typesetting (usetex)

LaTeX (a typesetting system built on TeX) can typeset the label, so it matches
the other usetex text in the figure. Set matplotlib's `text.usetex` rcParam (a
matplotlib runtime setting), or pass `usetex=True` to `curved_text`.
`curved_text` requires `latex`, as for any matplotlib usetex figure.
matplotlib's own usetex text, such as tick labels, also needs `dvipng`.

```python
curved_text(ax, x, y, r"yield 50% at $\sqrt{\bar{\sigma}_G}$", usetex=True)
```

Math runs go to LaTeX as written, so they can run TeX commands, including ones
that read local files. Do not pass untrusted text with usetex on.

The page [LaTeX typesetting (usetex)](https://thiebes.github.io/curved-text/usetex.html)
covers plain text, Greek letters, the preamble, caching, and `valign`.

### Background box and halo (`box`, `path_effects`)

Set `box` to add a casing behind the label: a band that follows the curve under
the glyphs, at the label's height. It keeps the label readable where it crosses
other lines. A single fill covers plain text and mathtext alike:

```python
curved_text(ax, x, y, r"signal $s(t) = A\,e^{-t/\tau}$", box=True)
```

`box` accepts `True`, a color string, or a dict with these keys:

| Key | Meaning | Default |
| ------- | ------------- | ------------- |
| `color` | Fill color of the band | white |
| `pad` | Band height, as a multiple of the tallest glyph's height | `1.1` |
| `alpha` | Opacity of the band | opaque |

In (b) below, the white casing hides the lines under the label. In (a), without
`box`, the lines pass through the text.

![Two panels with the same label over three gray lines. In (a), without box, the lines pass through the text. In (b), with box=True, a white band behind the label hides the lines under it.](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/11_box.png)

For a lighter effect that outlines each glyph (a halo), pass a white
`withStroke` through matplotlib's
[`path_effects`](https://matplotlib.org/stable/users/explain/artists/patheffects_guide.html).
Path effects reach every glyph and every math run, as they do on any `Text`.
Each glyph is stroked on its own, so a wide stroke makes neighboring glyphs blur
together. Use `box` for solid coverage under plain text:

```python
import matplotlib.patheffects as pe

curved_text(ax, x, y, r"signal $s(t) = A\,e^{-t/\tau}$",
            path_effects=[pe.withStroke(linewidth=4, foreground="white")])
```

A wide stroke per character leaves gaps, and one `box` fill does not. A thin
halo has its own use. Over thin lines and dense figures it hides the lines only
where they touch the glyphs. The Gallery sections
[Box versus a path-effects stroke](https://thiebes.github.io/curved-text/gallery.html#box-versus-a-path-effects-stroke) and
[A halo or a box](https://thiebes.github.io/curved-text/gallery.html#a-halo-or-a-box) show both cases.

### Tight bends (`crowding`)

Glyphs are placed one after another as ordinary text places them, by width and
kerning. On a
sharp bend they crowd together on the inside of the bend, where each rigid glyph
overlaps its neighbor. Set `crowding="curvature"` to add an even gap between
glyphs that grows with the local curvature, so the inside edges stop colliding:

```python
curved_text(ax, x, y, "winds", pos=0.5, anchor="center", offset=-13.0,
            crowding="curvature", color="#b06306", fontsize=20)
```

The gap is the same between every pair of glyphs, so the spacing stays even.
The correction has a deadband (a range below which no gap is added). A gentle
bend or a straight run stays below it and is unchanged, so only crowded text is
spaced out. The default `crowding="none"` leaves the spacing as ordinary text
sets it.

The Gallery section [Even spacing on a tight bend](https://thiebes.github.io/curved-text/gallery.html#even-spacing-on-a-tight-bend)
shows a sharp bend, where the correction visibly separates the glyphs. It also
shows a gentle bend of the same word, unchanged because it falls below the
deadband.

### Vertical alignment (`valign`)

By default the text straddles the curve (`valign="center"`). `valign` selects
which line of the text lies on the curve. `"baseline"` puts the baseline on the
curve, so the body sits above it. `"ascender"` and `"descender"` put the top or
bottom line of the text on the curve, which places the label below or above the
curve:

```python
curved_text(ax, x, y, "Amplitude", valign="baseline")
```

The shift is a single font metric applied to the whole label, so it never
disturbs the spacing or the alignment of plain text with mathtext. Combine it
with `offset` to lift the chosen line clear of the curve.

With `valign`, the same word moves from straddling the arc to hanging below it
or sitting above it. The Gallery section [`valign`: which line of the text lies on the curve](https://thiebes.github.io/curved-text/gallery.html#valign-which-line-of-the-text-lies-on-the-curve)
shows the word on an arc for each value.

### Works with seaborn, pandas, and other matplotlib-backed libraries

`curved_text` needs only a `matplotlib.axes.Axes`, so it works with any library
that draws on matplotlib. seaborn's axes-level functions return an `Axes`, and
its figure-level functions expose one through `.axes`. The pandas
`DataFrame.plot` method returns an `Axes` as well. Pass that axes in directly.
Here `df` is a long-form data frame with the columns `date`, `level`, and
`series`:

```python
import seaborn as sns

palette = {"NASDAQ Composite": "#003f7f", "S&P 500": "#b06306"}
ax = sns.lineplot(data=df, x="date", y="level", hue="series",
                  palette=palette, legend=False)
for name, line in df.groupby("series"):
    curved_text(ax, line["date"], line["level"], name, color=palette[name],
                pos=0.6, anchor="center", offset=8.0)
```

The Gallery section [Any matplotlib-backed axes (seaborn, pandas)](https://thiebes.github.io/curved-text/gallery.html#any-matplotlib-backed-axes-seaborn-pandas)
labels two stock market indexes with similar calls, in seaborn's `whitegrid`
theme, with each label in place of a legend entry. It also passes
`curved_text` a smoothed copy of each line, which keeps the glyphs of a label
on monthly data from tilting into each other.

## Limits

`curved_text` and `CurvedText` take the same arguments and make the same
artist. Keep the returned object to hide it (`set_visible`), restack it
(`set_zorder`), change its clipping, or remove it (`remove()`). To change the
text, color, size, or curve, remove the label and make a new one. `get_text()`
does not return the label's string.

- **Vector output:** In PDF, SVG, PostScript, and EPS output, each character is
  drawn as an outline path, not as text. The label cannot be selected, searched,
  or edited as text, and each glyph is a separate shape. In PNG output the label
  looks as it does on screen.
- **Axes:** Cartesian and polar axes work. On polar axes the angle runs
  counterclockwise, so a curve from angle 0 to π runs right to left over the top
  and its label reads upside down: reverse the arrays. A 3D axes accepts the
  call and draws nothing.
- **Animation:** Blitting is not supported: `ax.draw_artist(label)` draws
  nothing. Redraw the whole figure (a `FuncAnimation` without blitting works),
  or leave the label out of the blit.
- **Child artists:** Each character and each math run is a separate artist on
  the axes, so `ax.texts` lists them as well as the label. Do not remove or
  restyle them one at a time: removing one glyph breaks the next draw, and a
  loop that removes every item of `ax.texts` raises `ValueError`. Call
  `label.remove()` on the object that `curved_text` returns: it removes every
  part. To tell a label from other text, test `isinstance(t, CurvedText)`.
- **Lifecycle:** `label.remove()` removes every part of the label. `ax.clear()`
  removes it with the other artists. A figure that holds a label can be pickled.
  `legend(loc="best")` avoids the label from matplotlib 3.9.
- **Axis limits:** The label does not change the data limits. Plot the curve
  first, or set the limits yourself.
- **Text:** One line. A newline in the string is not a line break.
- **`pos`:** `pos` is a fraction of the curve you pass in, including any part
  outside the axes limits: pass the visible piece of the curve. A value outside
  0 to 1 places the anchor on the straight extension beyond an end; a value far
  outside can place it outside the figure. Use `clip_on=False` to see an anchor
  outside the axes.
- **Cost:** The time of a draw grows with the number of characters and the
  number of curve points, and is paid on every redraw. If interactive pan and
  zoom feels slow, pass fewer points: decimate or smooth the curve. Dozens of
  labels draw in well under a second.

## How it works

Each character (and each `$...$` run) is a child artist drawn from its glyph
outline and placed so that one shared text baseline follows the curve. A plain
glyph is turned rigidly: the package draws a straight line across the width of
that one glyph and turns the glyph to match. Averaging over the width keeps
neighboring glyphs smooth even when the curve has only a few points.
Sharing one baseline keeps plain text and mathtext level. The
[design notes](https://thiebes.github.io/curved-text/design.html) describe how mathtext is bent along the
curve.

All of this is measured in display space: pixels on the final figure after every
scaling step. Spacing and perpendicular offset therefore stay correct at any
dots per inch (dpi) and figure size. The layout is redone on every draw, so the
label follows resizing and interactive panning and zooming.

## Related

[matplotlib-label-lines](https://github.com/cphyc/matplotlib-label-lines) labels
one or many lines inline at a chosen or automatically picked point, each label
rotated to the local slope. `curved-text` addresses a different problem: it
makes a single string (plain or mathtext) follow a curve character by character,
with arc-length placement and a perpendicular offset, redone on every draw. Use
label-lines to replace legend entries on several lines, and curved-text to make
text follow a curve. For R users,
[geomtextpath](https://github.com/AllanCameron/geomtextpath) provides similar
functions for text along a curve in ggplot2 (an R plotting package).

For matplotlib users coming from LaTeX: curved-text is matplotlib's counterpart
of the `text along path` decoration of TikZ (a LaTeX drawing package), from
`decorations.text`. The mapping is close. `pos` and `anchor` play the role of
`text align` and the indents, and `offset` plays the role of `raise`. Text that
overruns the path follows the straight tangent extension. It is not cut off at
the end of the path.

## Documentation

Full documentation, including the API reference and the design notes, is at
[thiebes.github.io/curved-text](https://thiebes.github.io/curved-text/). More
worked examples are in the
[example gallery](https://thiebes.github.io/curved-text/gallery.html).

## Contributing

Bug reports, feature requests, and pull requests are welcome. See
[CONTRIBUTING.md](https://github.com/thiebes/curved-text/blob/main/CONTRIBUTING.md)
for the development install, how to run the tests, linting, and the rest of the
workflow. By participating you agree to the
[Code of Conduct](https://github.com/thiebes/curved-text/blob/main/CODE_OF_CONDUCT.md).

## Development and AI use

Generative AI tools were used to develop and maintain this package. The author
(the sole maintainer) directed the design and reviewed, tested, and approved
every change before committing it.

- **Design and direction.** The architecture and the design decisions were the
  maintainer's: the chord-across-width placement, the `_CurveFrame`
  display-space geometry, tangent-extension overflow, and the choice to support
  mathtext by bending glyph outlines along the curve. The mathtext feature was
  iterated against real problems found in use, including the baseline-alignment
  fix and the move from a per-character stroke to a single box casing once the
  per-letter halo was found to leave gaps. AI assisted in drafting the design
  documents and the implementation against these decisions.
- **Code.** The implementation in `src/curved_text/` was drafted with
  substantial AI assistance against that design, then reviewed and revised by
  the maintainer. Correctness, cross-version compatibility (the test suite runs
  against a matplotlib floor and a pre-release), packaging, and the release
  process were the maintainer's responsibility.
- **Tests.** The test suite in `tests/` was drafted with AI assistance and
  reviewed by the maintainer, and is run in CI on every change.
- **Documentation.** The README, API reference, and example gallery prose were
  drafted with AI assistance and edited by the maintainer.
- **How AI was used.** Primarily conversational and agentic drafting with
  Anthropic's Claude. The maintainer provided the problem framing, the design
  decisions, and the final review.

No AI-generated content was committed without human review.

## License

MIT
