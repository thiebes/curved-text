# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
