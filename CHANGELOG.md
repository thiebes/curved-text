# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- The curve takes the data `plot` takes: dates (`datetime64` in any unit,
  `datetime`, pandas dates, including timezone-aware ones), category strings,
  and values with units. The axes convert the curve as they convert a plotted
  line, so the label stays on the line and follows a later change of the axis
  units ([#24](https://github.com/thiebes/curved-text/issues/24)). Before,
  the curve was cast to float: a `datetime64` curve put the label far outside
  the axes, and `datetime` objects and strings raised. A label made before
  anything is plotted sets up the axis for its data, as `plot` does, and
  category strings not yet on an axis are added to it, as ticks, as for
  `ax.text` and `plot`.
- A NaN, infinite, or masked point leaves a gap in the curve, as in `plot`
  ([#28](https://github.com/thiebes/curved-text/issues/28)).
  `pos` is a fraction of the drawn length, and the label rides the stretch
  that holds its anchor, past whose ends it follows the stretch's end
  tangents, as at the ends of a curve. A point the axes' scale gives no pixel,
  such as x of 0 or less on a log axis with `nonpositive="mask"`, leaves a
  gap too. Before, NaN and infinite points raised `ValueError`, and the value
  under a mask placed the label. The curve needs two consecutive finite
  points.

### Changed

- Data an axis cannot convert, such as strings on a date axis, raises
  matplotlib's `ConversionError`, a `TypeError`, when the label is made
  ([#24](https://github.com/thiebes/curved-text/issues/24)). Before,
  strings raised `ValueError`, so code that catches `ValueError` no longer
  catches them.
- `get_position()` returns the curve's first finite point as given, for
  example a `datetime64`, as for any `Text`; `get_unitless_position()` returns
  it on the axes ([#24](https://github.com/thiebes/curved-text/issues/24),
  [#28](https://github.com/thiebes/curved-text/issues/28)).
- The label keeps its own copy of the curve, so a change to the caller's
  array after the label is made no longer moves it
  ([#24](https://github.com/thiebes/curved-text/issues/24)).

### Fixed

- A `box` color matplotlib cannot draw raises without leaving a half-made
  label on the axes. Before, the label was added to the axes first, so the
  next draw of the figure raised `AttributeError`.
- A label that cannot be placed, such as one on a curve that collapses to a
  point, is no longer drawn where it was last placed
  ([#28](https://github.com/thiebes/curved-text/issues/28)). Before,
  only its `box` casing was hidden, and its glyphs stayed painted.

## 0.7.0

### Changed

- Plain text is kerned. Each plain character's advance now includes the
  font's kern toward the next character in the same run, as the text's own
  layout applies it: matplotlib's, or under usetex TeX's. Pairs such as "AV"
  and "To" sit as tightly as in ordinary text, so labels that contain kerning
  pairs come out slightly tighter than before
  ([#20](https://github.com/thiebes/curved-text/issues/20)).
- Under usetex, each run of plain text is typeset in one LaTeX pass, where
  LaTeX used to run once for each distinct character. A long label's first draw
  is several times faster: about 2 s instead of 9 to 10 s for a 37-character
  label with an empty TeX cache. Each new label string now costs one LaTeX run,
  as matplotlib's own usetex text does, so a figure with many short new labels
  can take much longer than when their characters were already cached: 300 new
  short labels took 124 s, against 2.5 s
  ([#43](https://github.com/thiebes/curved-text/issues/43)). A run with a
  character TeX builds from several pieces, such as an accented letter in the
  default encoding, or with a soft hyphen or combining mark, is typeset one
  character at a time without kerning, as all usetex plain text was before.

### Fixed

- A label drawn with `clip_on=False` no longer stretches a tight bounding box
  (`bbox_inches="tight"`) to the data origin. Figure layout measured each glyph
  at its unused `Text` position; glyphs now stay out of figure layout.
- A label drawn with `clip_on=False` outside the axes is no longer cropped by a
  tight bounding box, and constrained layout makes room for it, as for
  matplotlib's own unclipped text. Figure layout measured the label as a single
  space at its curve's first point; it now measures the label as drawn
  ([#42](https://github.com/thiebes/curved-text/issues/42)). The same extent
  is what a legend placed at `loc="best"` avoids (matplotlib 3.10 and later) and
  what an annotation anchored to the label (`xycoords=label`) refers to, so
  both now follow the label's glyphs. Such a legend also no longer avoids the
  data origin, where it measured each glyph at an unused position.
- A label's visibility, clipping, and picking reach the parts it draws
  ([#45](https://github.com/thiebes/curved-text/issues/45)).
  `set_visible(False)` hides the label and its `box` casing, where its glyphs
  kept drawing before. The casing follows the label's `clip_on`, clip box, and
  clip path, so an unclipped label keeps its casing outside the axes instead of
  having it cut at the axes edge, and `set_clip_on` and the other clipping
  setters reach every glyph after construction too. The casing's band is part
  of the label's extent in figure layout, and leaves layout with the label.
  `picker=True` picks the label when the mouse is on one of its glyphs, where
  it never matched before, and its glyphs no longer fire pick events of their
  own near the data origin, whether `picker` is `True` or a function.
- A label on a logit axis, on a log axis with `nonpositive="mask"`, or on
  polar axes whose radial limits start above zero is drawn
  ([#27](https://github.com/thiebes/curved-text/issues/27)). It was missing
  even when every point of the curve was valid for the axes, usually with no
  error, though saving a boxed one to PDF raised a `ValueError`: each glyph
  was measured at the data origin, which has no pixel on those axes.

## 0.6.0

### Added

- LaTeX support: with the `text.usetex` rcParam set, or `usetex=True` passed as
  a keyword, LaTeX typesets both math runs and plain text, so a curved label
  matches the figure's other usetex text. Plain text is typeset literally, one
  character at a time, so TeX markup characters such as `%` and `#` print as
  themselves and TeX commands work only inside `$...$`. Contributed by Andrey
  Latyshev in [#5](https://github.com/thiebes/curved-text/pull/5).

  A LaTeX installation is required, as for any matplotlib usetex text. Plain
  text is limited to the characters the LaTeX preamble can typeset; the README
  shows how to declare upright Greek letters. The `valign` lines and the `box`
  casing come from the TeX font as LaTeX draws it, so `valign="ascender"` meets
  the tops of the letters, where without usetex it sits a little above them.
  The first draw runs LaTeX once for each distinct character and math run,
  which can take several seconds; later draws are cached. Math runs go to LaTeX
  as written and can run TeX commands, so do not pass untrusted text with
  usetex on.

### Changed

- With the `text.usetex` rcParam already on, curved labels are now typeset by
  LaTeX in the figure's usetex font. Before, they were drawn in the matplotlib
  font with the letters run together, and a `%`, `&`, or `#` in the label
  raised an error.

## 0.5.0

### Added

- A `valign` option chooses which line of the text rides the curve: `"center"`
  (the default), `"baseline"`, `"ascender"`, or `"descender"`. It is a single
  font-metric shift applied identically to every glyph and every mathtext run, so
  it keeps plain and math aligned and introduces no per-glyph step. Combine it
  with `offset` to lift the chosen line off the curve.

### Fixed

- Plain text drawn along a curve no longer shows a per-character perpendicular
  "step". Each glyph sat a few pixels off the shared baseline, producing a
  visible staircase that was worst on steep or straight runs. The cause was that
  every character was an individually rotated `matplotlib.text.Text`, which
  matplotlib aligns from its own per-glyph bounding box, scattering the baselines
  by a few pixels. Every segment -- plain character or mathtext run -- now shares
  one text baseline, so the placement is level by construction.
- A tab or newline in the label no longer renders a missing-glyph box. Whitespace
  advances the cursor and draws nothing, as a plain space already did.

### Changed

- Plain characters are now rendered from their glyph outlines, the way mathtext
  already was, rather than as individually rotated text artists. This is what
  lets a single shared baseline be placed exactly. The one trade-off is that
  outlines are unhinted, which is unavoidable for rotated text and is marginal in
  practice. The default `valign="center"` reproduces the previous "text straddles
  the curve" placement, so existing `offset` values land where they did.

## 0.4.0

### Added

- A `crowding` option spaces glyphs apart where the curve bends sharply. The
  default, `crowding="none"`, advances each glyph by its own width, so on the
  concave side of a tight bend the rotated glyph boxes can overlap.
  `crowding="curvature"` opens an even letterspacing gap that grows with the
  local curvature and the glyph height, so the inside edges stop colliding. The
  gap is the same between every pair of letters, so the tracking stays even, and
  a deadband leaves gentle bends and straight runs unchanged.

### Fixed

- `offset` now lays the label along the parallel (offset) curve at the requested
  distance, rather than translating it by a single vector taken from the normal
  of the label's end-to-end chord. The old translation crowded one end of the
  label against a steep, asymmetrically curved guide while floating the other end
  off it. Laying the glyphs along the offset curve -- so the cursor advances
  along the curve they actually sit on -- keeps both the perpendicular clearance
  and the on-screen letter spacing uniform along the whole label. The casing and
  mathtext runs ride the same offset curve. `pos` and `anchor` stay measured
  against the original curve and are carried perpendicularly onto the offset
  curve, so an offset label sits directly off the spot the same `pos` marks on
  the bare curve. On straight, gently curved, or symmetric guides the result is
  unchanged.
- A `box` casing no longer stays painted with stale geometry when a later draw
  meets a degenerate curve (zero arc length, e.g. an axis collapsed by zoom) or
  a detached axes. The casing is hidden on those draws rather than left on
  screen.

### Changed

- An unknown key in a `box` dict now raises `ValueError` instead of being
  silently dropped, so a typo such as `box=dict(colour="red")` surfaces.

## 0.3.1

This release carries no changes to the library's behaviour. It updates project
maturity, documentation, and packaging metadata.

### Changed

- Development status is now Beta. The public API (the `curved_text` function and
  the `CurvedText` class, with `pos`, `anchor`, `offset`, `box`, and the keyword
  pass-through) has been stable across releases.

### Added

- Hosted documentation and API reference at
  [thiebes.github.io/curved-text](https://thiebes.github.io/curved-text/).
- A `docs` extra (`pip install curved-text[docs]`) for building the
  documentation locally.

## 0.3.0

- Added `box`: a casing drawn behind the label that follows the curve at the
  label's height, under the glyphs, so the label stays legible where it crosses
  the lines it labels. Because it is a single fill it gives solid coverage
  behind plain and mathtext alike, unlike a wide `path_effects` stroke, which
  cannibalizes adjacent per-character glyphs. Accepts `True`, a color string, or
  a dict of `color` / `pad` / `alpha`.
- Mathtext runs now honor `path_effects`, matching the per-character glyphs, for
  a lighter glyph-hugging casing (a white `withStroke`). Path effects already
  reached plain characters through the keyword pass-through; mathtext runs draw
  their own path and previously skipped them.
- Fixed mathtext vertical alignment: a run now rides the curve on the
  surrounding text's x-height line rather than its own bounding box, so a
  superscript or tall delimiter no longer drops the body below the neighbouring
  plain characters.

## 0.2.0

- Mathtext support: a `$...$` run in the label is laid out by matplotlib's
  mathtext engine and bent through the curve's arc-length frame, mapping every
  glyph outline and rule box so radicals, fractions, and sized delimiters stay
  connected and follow the curve. Plain and math runs mix in one string. Pass
  `parse_math=False` to treat dollar signs literally; `text.usetex` is not
  supported.

## 0.1.1

- Fixed kinked letters on coarsely sampled curves: each glyph is now rotated to
  the chord across its own advance instead of the tangent of the single polyline
  segment under its midpoint, so rotation stays smooth across segment vertices.
  Glyph positions are unchanged.

## 0.1.0

Initial release.

- Draw a string along an arbitrary matplotlib curve, one character per
  `matplotlib.text.Text`, with the layout recomputed on every draw so the label
  follows the curve through layout, resizing, and interactive pan or zoom.
- Arc-length positioning (`pos`), label anchoring (`anchor`), and a perpendicular
  offset in typographic points (`offset`), each computed in display space.
- Labels that overrun a curve end ride the straight tangent extension rather than
  being clipped.
- Both a `curved_text` function and a `CurvedText` artist class.
