# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
