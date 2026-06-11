# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
