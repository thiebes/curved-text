# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
