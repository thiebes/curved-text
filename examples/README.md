# Examples

A small gallery showing what
[`curved-text`](https://github.com/thiebes/curved-text#readme) does and how to
drive it. Each figure is produced by a self-contained script in the
repository's [`examples/`](https://github.com/thiebes/curved-text/tree/main/examples)
directory; the link under each figure points to the script that drew it.

Most scripts need only matplotlib and numpy (already installed with the
package). The one integration example also needs seaborn and pandas; install
those with the `examples` extra. The usetex example also needs a LaTeX
installation with `dvipng`, which pip does not install; without it that script
skips its figure. The seaborn figure and the stock price figure read the
`Stocks.csv` sample data, which matplotlib 3.5 does not ship; there both skip.
Then regenerate everything into [images/](https://github.com/thiebes/curved-text/tree/main/examples/images):

```bash
pip install -e ".[examples]"
python examples/generate_all.py
```

Or run one script on its own:

```bash
python examples/example_02_sine_hello.py
```

The scripts follow the repository's plot conventions (the DICE palette in
shades that meet the WCAG 4.5:1 contrast minimum for text, with each data
series drawing its line and its label in the same shade, a white background,
sizes in centimetres, explicit dpi). Most panels hide their
axes on purpose: the subject is the text-on-curve geometry, so quantitative
ticks would only get in the way. The figures that plot data -- direct
labeling, its usetex version, the seaborn figure, and the applications on real
data or physical laws -- keep their axes and units, and so does the log-axis
panel of the gaps figure, whose subject is the scale.

The caption under a panel gives the call that drew it. Where every panel of a
figure makes the same call, its section gives that call once, and each caption
shows only what differs. The applications have no captions; their paragraphs
explain them.

## The case for the tool

### Direct labeling replaces the legend

The reason the package exists. In (a), a conventional legend forces the eye
off the data to decode a colour key. In (b), each curve is labeled along its
own path -- no legend, no round trip.

![Direct labeling versus a legend](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/01_direct_labeling.png)

[example_01_direct_labeling.py](https://github.com/thiebes/curved-text/blob/main/examples/example_01_direct_labeling.py)

### Hello, curve

One curve, one centred label riding it with a small perpendicular offset.

![A label following a sine wave](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/02_sine_hello.png)

[example_02_sine_hello.py](https://github.com/thiebes/curved-text/blob/main/examples/example_02_sine_hello.py)

### Mathtext rides the curve too

A `$...$` run is laid out by matplotlib's mathtext engine and bent through the
same arc-length frame as plain text, so the radical, fraction, and superscript
stay connected and follow the curve. Plain and math runs mix in one string.

![A mathtext expression following a sine wave](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/10_mathtext.png)

[example_10_mathtext.py](https://github.com/thiebes/curved-text/blob/main/examples/example_10_mathtext.py)

### Plain words and math share one baseline

Plain words and math runs in one label share a single baseline, so the math
symbols sit level with the surrounding letters and a superscript lifts only the
exponent, not the body.

![Plain words and math runs on one shared baseline along a curve](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/15_mixed_alignment.png)

[example_15_mixed_alignment.py](https://github.com/thiebes/curved-text/blob/main/examples/example_15_mixed_alignment.py)

### LaTeX typesets the labels under usetex

With matplotlib's `text.usetex` rcParam on and the serif font family, LaTeX
typesets the curved labels as it does the tick and axis labels, so the whole
figure reads in one face. This is the direct-labeling figure drawn under
usetex. The script needs `latex`, and `dvipng` for the tick and axis labels, as
any matplotlib usetex figure does, and skips the figure without them.

![Cooling curves labelled along their paths, with every text typeset by LaTeX](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/16_usetex.png)

[example_16_usetex.py](https://github.com/thiebes/curved-text/blob/main/examples/example_16_usetex.py)

## The placement controls

`pos`, `anchor`, `offset`, and `valign` are independent. Each small-multiple
below varies one and holds the others fixed.

### `pos` -- where the label is anchored, as a fraction of arc length

The ring marks the anchor point as `pos` runs from the first point (0.0) to the
last (1.0).

Every panel makes this call, with the argument its caption names:

```python
curved_text(ax, x, y, "label", pos=pos, anchor="center", offset=7.0)
```

![A label at five positions along a curve](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/03_pos_sweep.png)

[example_03_pos_sweep.py](https://github.com/thiebes/curved-text/blob/main/examples/example_03_pos_sweep.py)

### `anchor` -- which part of the label lands at `pos`

The ring is fixed at `pos=0.5` in every panel; the word's start, middle, or end
sits on it.

Every panel makes this call, with the argument its caption names:

```python
curved_text(ax, x, y, "anchored", pos=0.5, anchor=anchor, offset=7.0)
```

![Start, center, and end anchoring](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/04_anchor_triptych.png)

[example_04_anchor_triptych.py](https://github.com/thiebes/curved-text/blob/main/examples/example_04_anchor_triptych.py)

### `offset` -- a perpendicular shift off the curve

In points, along the chord normal. Positive is to the left of the direction of
travel -- above a left-to-right curve. The ring marks the on-curve anchor, and
stays visible over the label at `offset=0`.

Every panel makes this call, with the argument its caption names:

```python
curved_text(ax, x, y, "offset", pos=0.5, anchor="center", offset=offset)
```

![Negative, zero, and positive offset](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/05_offset_ladder.png)

[example_05_offset_ladder.py](https://github.com/thiebes/curved-text/blob/main/examples/example_05_offset_ladder.py)

### `valign` -- which line of the text rides the curve

By default the text straddles the curve (`valign="center"`). `"baseline"` runs
the text baseline along the curve, so the body sits above it with descenders
below, and `"ascender"` and `"descender"` ride the top or bottom of the text.
The shift is a single font metric applied to the whole label, so it never
disturbs the spacing or the alignment of plain text with mathtext.

Every panel makes this call, with the argument its caption names:

```python
curved_text(ax, x, y, "Amplitude", pos=0.5, anchor="center", valign=valign)
```

![The same word on a curve under each valign option](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/14_valign.png)

[example_14_valign.py](https://github.com/thiebes/curved-text/blob/main/examples/example_14_valign.py)

## Edge behaviors

### An overrun rides the end tangent

A long label on a short curve is not clipped: the curve is extended along its
end tangent (dashed) and the overrunning glyphs sit on that straight line.

![A label overrunning the curve end](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/06_overrun_tangent.png)

[example_06_overrun_tangent.py](https://github.com/thiebes/curved-text/blob/main/examples/example_06_overrun_tangent.py)

### Glued through a change of aspect

The same curve and the same call, drawn at two aspect ratios. Layout is
recomputed per draw in display space, so spacing and offset stay correct -- the
label does not stretch or shear. This is the static stand-in for interactive
pan and zoom, which the next figure animates.

Both panels make this call:

```python
curved_text(ax, x, y, "same call, glued", pos=0.5, anchor="center", offset=8.0)
```

![The same label glued at two aspect ratios](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/07_glued_resize.png)

[example_07_glued_resize.py](https://github.com/thiebes/curved-text/blob/main/examples/example_07_glued_resize.py)

### Glued through pan and zoom

The animated version: one call draws the label, and then only the axis limits
change, every frame, as interactive panning and zooming change them. The view
zooms in toward the label and back out, and the label follows its curve
through every change of scale. It rides the rising slope after the first
trough, which the script passes as its curve, so it stays in the close view:

```python
curved_text(ax, x[stretch], y[stretch], "stays on the curve", pos=0.5,
            anchor="center", offset=7.0)
```

![An animation zooming in on a labelled damped oscillation and back out, with the label staying on its curve](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/25_pan_zoom.gif)

[example_25_pan_zoom_animation.py](https://github.com/thiebes/curved-text/blob/main/examples/example_25_pan_zoom_animation.py)

### Even spacing on a tight bend

Letters are placed one after another by their own widths, so on a sharp bend
they crowd together on the inside of the curve, where each rigid letter box fans
into its neighbour. `crowding="curvature"` opens an even letterspacing gap that
grows with the local curvature, so the inside edges stop colliding. The gap is
the same between every pair of letters, so the tracking stays even, and it has a
deadband: a gentle bend, (c) and (d), stays below it, so the two columns there
are identical. Only the tight bend, (a) and (b), is changed.

Every panel makes this call, with the argument its caption names:

```python
curved_text(ax, x, y, "winds", pos=0.5, anchor="center", offset=-13.0,
            crowding=crowding)
```

![A sharp bend with crowded letters spaced out, a gentle bend left unchanged](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/13_crowding.png)

[example_13_crowding.py](https://github.com/thiebes/curved-text/blob/main/examples/example_13_crowding.py)

### Why a label reads upside down: direction of travel

A label reads in the order of its curve's points as they appear on screen; the
arrowhead at the end of each curve marks that direction. On the same
sine, (a) the points run from left to right and the label is upright; (b) the
arrays are reversed, so the curve runs from right to left and the label reads
upside down; (c) an inverted x axis puts the points right to left on screen
too, with the same result. `pos` counts from the first point and `offset` turns
with the direction, so the label also moves along the curve and to its other
side. Reversing the arrays of a curve that runs from right to left on screen
turns its label upright. An option to keep labels upright automatically is
planned ([#30](https://github.com/thiebes/curved-text/issues/30)). In each
caption, `...` stands for the same arguments:
`pos=0.4, anchor="center", offset=7.0`.

![The same label upright, upside down on reversed arrays, and upside down on an inverted x axis](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/17_direction_of_travel.png)

[example_17_direction_of_travel.py](https://github.com/thiebes/curved-text/blob/main/examples/example_17_direction_of_travel.py)

### Gaps in the curve

A curve has gaps where it has no value to draw: at NaN points (a), at masked
points (b), and at zeros on a log axis (c), which has no place for them. The
log axis in (c) masks the zeros (`nonpositive="mask"`), so the plotted line
breaks where the label's stretch does; the label treats them as gaps whatever
that setting. `pos` is measured along the drawn length, and the label rides the
stretch that holds its anchor. To run a label across gaps, pass a smooth curve
that follows the data instead.

Every panel makes this call, on the curve its caption builds:

```python
curved_text(ax, x, y, "a stretch", pos=0.5, anchor="center", offset=6.0)
```

![A label riding one stretch of curves with NaN, masked, and log-axis gaps](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/26_gaps.png)

[example_26_gaps.py](https://github.com/thiebes/curved-text/blob/main/examples/example_26_gaps.py)

## Styling and integration

### Keyword arguments reach every character

Anything beyond the placement controls is forwarded verbatim to each
per-character glyph and each mathtext run.

![A label styled with color, size, weight, and family](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/08_styling_passthrough.png)

[example_08_styling_passthrough.py](https://github.com/thiebes/curved-text/blob/main/examples/example_08_styling_passthrough.py)

### Clear the lines behind the label

`box=True` draws a casing that follows the curve at the label's height, under
the glyphs, so the label stays legible where it crosses the lines it labels. It
is a single fill, so it covers plain text and mathtext alike. (For a lighter
casing that hugs each glyph (a halo), pass a white `withStroke` through
`path_effects` instead.)

Every panel makes this call, with the argument its caption names:

```python
curved_text(ax, x, y, r"signal $s(t) = A\,e^{-t/\tau}$", pos=0.5,
            anchor="center", offset=0.0, box=box)
```

![A label cleared from the lines it crosses by a white casing](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/11_box.png)

[example_11_box.py](https://github.com/thiebes/curved-text/blob/main/examples/example_11_box.py)

### Box versus a path-effects stroke

The same plain-text label over the same lines, two ways. A wide `withStroke` is
applied per character, so neighbouring letters blur together and the lines show
through the gaps. `box` is a single fill under the whole label, so it covers
plain text cleanly. This is why `box` is the way to get solid coverage under
plain text. A thin halo still has its place, as
[the next figure](#a-halo-or-a-box) shows.

Every panel makes this call, with the keyword arguments its caption names:

```python
curved_text(ax, x, y, "crossing the gridlines", pos=0.5, anchor="center",
            offset=0.0, ...)
```

![A wide per-character stroke leaves gaps; a box fill covers cleanly](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/12_box_vs_stroke.png)

[example_12_box_vs_stroke.py](https://github.com/thiebes/curved-text/blob/main/examples/example_12_box_vs_stroke.py)

### A halo or a box

The same label over a family of thin lines that cross it, cleared two ways.
(a) A halo, a thin white `withStroke` around each glyph, hides the lines only
where they touch the letters, so they stay readable between and around the
letters. (b) A casing, here in its colour-string form, white to match the page,
gives one band under the whole label, which clears heavy lines completely but
erases every line inside the band. Use the halo for thin lines and dense
figures, and the box where the lines behind the label are heavy. A wide halo is
another matter: [it blurs the letters together](#box-versus-a-path-effects-stroke).

Every panel makes this call, with the keyword arguments its caption names:

```python
curved_text(ax, x, y, "legible over thin lines", pos=0.5, anchor="center",
            offset=10.0, ...)
```

![A label cleared by a thin halo and by a box over a family of thin lines](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/19_halo_or_box.png)

[example_19_halo_or_box.py](https://github.com/thiebes/curved-text/blob/main/examples/example_19_halo_or_box.py)

### Several labels on one curve

One call per label, each at its own `pos`, repeats a curve's name along it, as
inline contour labels do. Each label here clears the thin reference lines
behind it with a casing in its dict form: `color` sets the band's colour, white
to match the page, and `pad` its height relative to the tallest glyph. The
reference lines show where the band cuts them.

![A damped oscillation labelled three times, each label's white band cutting the reference lines behind it](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/18_repeated_labels.png)

[example_18_repeated_labels.py](https://github.com/thiebes/curved-text/blob/main/examples/example_18_repeated_labels.py)

### Any matplotlib-backed axes (seaborn, pandas)

`curved_text` only needs a `matplotlib.axes.Axes`, so it composes with seaborn,
`pandas.DataFrame.plot`, and anything else that draws on matplotlib. Here pandas
reads the `Stocks.csv` sample data that ships with matplotlib, and
`sns.lineplot` draws two stock market indexes in seaborn's `whitegrid` theme,
with each line labelled along its path in place of seaborn's legend. This
script renders only if seaborn and pandas are installed (they come with the
`examples` extra); they are not runtime dependencies of curved-text.

![Two stock market indexes drawn by seaborn, each labelled along its line](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/09_seaborn_pandas.png)

[example_09_seaborn_pandas.py](https://github.com/thiebes/curved-text/blob/main/examples/example_09_seaborn_pandas.py)

## Applications

### Blackbody spectra

Planck's law for four temperatures, from a cool star to the Sun's effective
temperature, 5772 K, on a logarithmic radiance axis. Each label rides its own
curve just past the peak, which Wien's law puts at 2898 μm K / T. The script
passes `curved_text` only that stretch of each curve: on this axis most of a
curve's length is its steep left flank, which falls far below the axes, so a
`pos` along the whole curve would count length the reader never sees.

![Four blackbody spectra, each labelled with its temperature along its path](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/21_blackbody.png)

[example_21_blackbody.py](https://github.com/thiebes/curved-text/blob/main/examples/example_21_blackbody.py)

### Text around a circle and along a spiral

(a) Each half of the circle is traced from nine o'clock to three o'clock, the
top half clockwise and the bottom half counterclockwise, so both labels run
left to right on screen and read upright, outside the circle. (b) A sentence
winds out along the inside of an Archimedean spiral, r = aθ, whose turns keep
an even spacing. Along the bottom of each turn the text runs right to left on
screen and reads upside down, as
[the direction-of-travel figure](#why-a-label-reads-upside-down-direction-of-travel)
explains.

![Text over and under a circle, and a sentence winding out along a spiral](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/22_circle_spiral.png)

[example_22_circle_spiral.py](https://github.com/thiebes/curved-text/blob/main/examples/example_22_circle_spiral.py)

### Stock prices on real dates

Monthly values from the `Stocks.csv` sample data on a log axis: adjusted
closing prices for three stocks, which include reinvested dividends, and the
S&P 500 price index, which does not, each relative to January 1990 and
smoothed with a 12-month rolling mean. The dates go to `plot` and
`curved_text` as `datetime64` values. Even smoothed, a monthly line wiggles at
the scale of a letter, which tilts neighbouring letters into each other, so
each label rides its line smoothed once more, by a Gaussian about a letter
wide: a path that follows the line without those wiggles, and is never drawn.
The seaborn figure labels its lines the same way, and
[#61](https://github.com/thiebes/curved-text/issues/61) tracks handling this in
the library.

![Three stocks and the S&P 500 since 1990 on a log axis, each labelled along its line](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/23_stocks.png)

[example_23_stocks.py](https://github.com/thiebes/curved-text/blob/main/examples/example_23_stocks.py)
