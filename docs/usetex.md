# LaTeX typesetting (usetex)

LaTeX (a typesetting system built on TeX) can typeset a curved label, so the label matches the other LaTeX text in the figure. This page covers how to turn it on, what it requires, how plain text and Greek letters behave, how to set up the preamble, and how `valign` changes. The [README](https://thiebes.github.io/curved-text/index.html) has a short summary, and the [API reference](https://thiebes.github.io/curved-text/api.html) lists every parameter.

## Enable usetex

Set matplotlib's `text.usetex` rcParam (a matplotlib runtime setting), or pass `usetex=True` to `curved_text`:

```python
curved_text(ax, x, y, r"yield 50% at $\sqrt{\bar{\sigma}_G}$", usetex=True)
```

The usetex setting is fixed when the label is created, as matplotlib fixes it for each text. Set the rcParam or pass `usetex=True` before you create the label.

In the next figure, the rcParam and the serif font family make the tick labels, the axis labels, and the curve labels share one LaTeX typeface. With the default sans-serif family, words in text mode are set in Computer Modern Sans, while math stays in the serif Computer Modern.

![Three cooling curves, temperature T in degrees Celsius against time t in seconds from 0 to 10, with tau = 1.5 s, 3 s, and 6 s, each labeled along its own curve. The tick labels, axis labels, and curve labels are all set in the same serif LaTeX typeface.](https://raw.githubusercontent.com/thiebes/curved-text/main/examples/images/16_usetex.png)

## Requirements

`curved_text` requires `latex`, as for any matplotlib usetex figure. matplotlib's own usetex text, such as tick labels and axis labels, also needs `dvipng` (a program that converts LaTeX output to images). The figure above has usetex tick labels, so its script needs both programs. The library alone needs only `latex`.

## Plain text and Greek letters

A plain run is a piece of plain text between math runs, or between a math run and an end of the string. Math runs are the `$...$` parts.

Plain text is typeset literally. The characters `%`, `#`, `&`, and the other TeX markup characters print as themselves. TeX commands work only inside `$...$`. matplotlib's own usetex text differs: it needs `r"50\%"` for a percent sign. A straight `"` is typeset as a closing curly quote, as in matplotlib's own usetex text.

Plain text is limited to characters that the LaTeX preamble (the setup commands that come before the text) can typeset. By default, a Greek letter in plain text is a LaTeX error, as it is in matplotlib's own usetex text. A Greek letter in a math run (`$\lambda$`) is italic, as a variable should be. An upright Greek letter in plain text, such as a name or a unit, needs a LaTeX package and one declaration per letter. The next section shows a recipe.

## The preamble and the order of setup

The library leaves the preamble to you. It does not load packages, because the preamble is one global setting for every usetex text in the figure, including the layout passes that measure the label. A package loaded only during the library's own draws would measure and draw with different preambles. A package loaded globally would change your other usetex text.

To print an upright Greek letter in plain text, declare it in your own preamble, one declaration per letter:

```python
mpl.rcParams["text.latex.preamble"] = (
    r"\usepackage{upgreek}"
    r"\DeclareUnicodeCharacter{03BB}{\ensuremath{\uplambda}}"
)
curved_text(ax, x, y, r"plain λ, math $\lambda$", usetex=True)
```

Set the LaTeX preamble and the font family and font lists before the figure is first drawn. matplotlib caches text measurements per figure without the preamble. If you change these settings after a draw, a redraw of the same figure keeps the old measurements of math runs and of text typeset one character at a time. Plain runs follow the change, so one label can mix two fonts. matplotlib's own usetex text also keeps the old measurements. After you change the settings, create the figure again.

LaTeX takes the font family from the `font.family` rcParam, as for matplotlib's own usetex text. The `fontfamily` keyword therefore has no effect.

## How runs are typeset and cached

LaTeX typesets each plain run in one pass, with kerning (adjustment of the space between particular pairs of characters) as TeX sets it. Each space is one interword space, without the extra space that TeX adds after a period. A tab counts as a space.

Some plain runs are typeset one character at a time, without kerning. This happens when a run holds a character that TeX builds from several pieces, such as an accented letter in the default encoding. It also happens for a character that can print nothing, such as a soft hyphen.

The first draw runs LaTeX once for each distinct plain run and math run, as matplotlib does for each usetex string. It runs up to twice more to measure the font's line heights. Later draws use caches. A figure with many short new labels therefore runs LaTeX many times on its first draw. A label that was drawn before, with the same text, size, and preamble, does not run LaTeX again.

## Vertical alignment (`valign`)

Under usetex, the `valign` lines come from the TeX font as LaTeX draws it, not from the matplotlib font named by the font properties. The ascender and descender lines are the height and depth that TeX measures for the text `()gy` in the font it sets the label in.

The ascender line is the one that `valign="ascender"` puts on the curve. Under usetex, it lies about 0.06 em above the tops of capital letters (1 em is the font size). Without usetex, it lies about 0.2 em above them in the default font, DejaVu Sans, on the line that the font reserves for line spacing. Other fonts differ, from about 0.02 em to about 0.4 em.

The [README](https://thiebes.github.io/curved-text/index.html#vertical-alignment-valign) describes the four `valign` values.

## Safety

Math runs go to LaTeX as written, so they can run TeX commands, including ones that read local files. Do not pass untrusted text with usetex on.
