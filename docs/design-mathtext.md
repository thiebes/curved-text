# Design: mathtext support

## Decision

`CurvedText` accepts matplotlib mathtext (`$...$`) inside the label string.
The label is tokenized into runs: plain-text runs keep the existing
per-character placement exactly, and each math run is rendered by bending the
glyph outlines of matplotlib's own mathtext layout through the curve's
arc-length frame at draw time. There is no new public API: mathtext arrives
through the existing `text` argument, and `pos`, `anchor`, `offset`, and the
kwargs pass-through keep their meaning.

Two existing design invariants are preserved and remain load-bearing: all
geometry is computed per draw in display space, and children are independent
artists that the parent positions before they render (the zorder + 1
ordering).

## Why bending, and what was rejected

Mathtext cannot survive the library's per-character construction: splitting
`$\propto D$` into characters destroys the expression before matplotlib's
parser sees it. Four approaches were considered.

**Unicode substitution.** Translate math to Unicode characters (`\propto` to
U+221D) and curve them as plain text. Rejected as a library mechanism: the
coverage ceiling is hard (fractions, radicals, sized delimiters, most
subscript letters have no Unicode form), mathtext styles variables in italic
from the math font so substituted text renders visibly differently, and a
library silently rewriting user content violates least surprise. It remains
good user-side advice for simple symbols.

**One rigid block per math run.** Render each `$...$` run as a single child
`Text` artist, measured and rotated by the existing draw loop. About thirty
lines of change and fully vector, but the run sits on its chord: on a curving
section a long expression visibly detaches from the path. Kept as the mental
fallback; not chosen.

**Rigid per-glyph placement.** Decompose the mathtext layout into glyphs and
place each rigidly at its own arc position, rotated to the local tangent (the
classic text-on-path treatment). Prototyping showed the structural flaw:
composite constructs are drawn in two frames. A radical's check mark is one
rigid glyph while its overline is a rule box that must follow the curve; the
junction error grows with curvature times the construct's height, and the
tallest constructs (radicals, big delimiters, fractions) are exactly where it
shows. Repairing this requires grouping glyphs by parse-tree structure, which
the public layout API does not expose. Rejected on complexity.

**Bend everything through one frame (chosen).** Map every outline control
point and every rule box through the same curvilinear map

```text
(u, v) -> curve(u) + (v - datum) * normal(u)
```

where `u` is arc length along the label and `v` is height above the
baseline. Seams are impossible by construction because there is only one
frame. The single failure mode is smooth distortion that grows with label
height times curvature, and it degrades gracefully: prototypes remained
readable with the fraction centered on a bend whose radius was comparable to
the expression height, and were indistinguishable from straight typesetting at
typical label-to-curvature ratios.

## Mixed-string semantics

Plain runs and math runs deliberately use different placement at different
scales of rigidity:

- Plain characters stay rigid, each rotated to the tangent at its own arc
  midpoint. This is unchanged from the library without mathtext.
- Math runs bend continuously through the frame.

The two regimes are consistent rather than conflicting: per-character rigid
placement is the glyph-scale discretization of the same frame, so on a
straight section they coincide exactly, and within the width of one glyph the
difference is far below a pixel at any curvature where text is readable.
Keeping plain runs as real `Text` artists also preserves font rendering
(hinting, fallback) for the common case.

## Architecture

All code lives in `src/curved_text/_core.py`.

- `_Run` (NamedTuple: `is_math`, `text`) and `_split_runs(text)`: a pure
  tokenizer mirroring matplotlib's own rules. An odd count of unescaped `$`
  means the whole string is one plain run; `\$` in plain runs unescapes to
  `$`; empty plain runs between adjacent math runs are dropped; math runs keep
  their delimiters so they re-parse as written.
- `_CurveFrame`: the display-space curve geometry (projected points,
  cumulative arc length) with a vectorized point-and-tangent lookup. It
  replaces the `_point` closure and keeps its clip-then-extrapolate semantics,
  so labels overrunning a curve end still ride the straight tangent
  extension. Shared by the per-character walk and by math runs.
- `_MathRun(matplotlib.text.Text)`: one child artist per math run.
  Subclassing `Text` inherits kwargs handling identically to sibling
  characters, and `get_window_extent` already measures mathtext, so the
  parent's measurement loop has no special case. The subclass overrides
  `draw`:
  - `_glyph_layout()` calls `TextToPath.get_glyphs_mathtext` (public API) and
    memoizes one entry keyed on text and font properties. Glyph units are
    resolution independent; only the per-draw pixel scale varies.
  - `_layout_path(renderer)` builds the bent compound path in display pixels:
    outline vertices are scaled and offset to expression coordinates, straight
    segments longer than a few display pixels along the curve direction are
    subdivided (rule boxes such as fraction bars are the long ones), bezier
    control points are mapped directly (the same approximation vector editors
    use for path bending), and whitespace glyphs with empty outlines are
    skipped.
  - `draw(renderer)` fills the compound path with one `renderer.draw_path`
    call using the artist's color and alpha, with clipping set through public
    `GraphicsContext` methods. With no frame assigned it draws nothing.
  - `_set_frame(frame, s_left, offset_px)` is the per-draw handoff the parent
    calls; it mutates the run and returns None.
- `CurvedText` builds children from `_split_runs` (honoring `parse_math`;
  disabling it restores per-character behavior exactly), and its draw gains
  one branch in the cursor walk: math runs receive the frame instead of a
  position and rotation. The child list is named `_segments`, since elements
  are no longer all characters.

## Vertical datum

A math run sits where a rigid `Text` child with `va="center"` would sit: its
own layout box center rides the curve, so `datum = height / 2 - depth` above
the baseline, taken from the mathtext metrics. This is the one definition
consistent with how every plain character is already placed, and it is pinned
by test rather than asserted: on a straight line the bend map is the identity,
so the bent path must match the window extent of an equivalent plain `Text`
within a pixel or two.

## Path effects

Keyword arguments reach every child, so `path_effects` flow to the per-character
`Text` glyphs and to each `_MathRun`. Plain glyphs apply them through the base
`Text.draw`; `_MathRun.draw` draws its own bent path, so it wraps the renderer in
a `PathEffectRenderer` when effects are set. The effect strokes the bent outline,
so a white `withStroke` casing follows the curved text and clears the lines a
label crosses. This is the matplotlib-native idiom for legible labels; no
dedicated parameter is added.

## Behavior rules

- `parse_math=False` (kwarg or rcParam) disables splitting entirely.
- A string with an odd count of unescaped `$` renders literally, character by
  character, as matplotlib itself would.
- `usetex` is unsupported and documented as such. The run architecture
  accepts a TeX backend later through `TextToPath.get_glyphs_tex` without
  redesign.
- Tall constructs degrade by vertical compression on the inside of bends;
  the docstring states this and leaves label-size-to-curvature judgment to the
  user.

## Test pins

Beyond ports of the existing behavioral suite (ordering, offset, dpi
invariance, overrun, idempotent redraw, degenerate curve, zorder, remove,
fontsize pass-through), two tests carry the design:

- Straight-line equivalence: the bent path of a math run on a straight
  horizontal curve matches matplotlib's own rendering of the same string as a
  rigid `Text`. Pins datum, width, scale, and dpi handling at once.
- Anti-rigidity: a math label spanning a wide circular arc keeps every path
  vertex within `radius +/- half label height`, a bound chord placement would
  violate. Pins that bending actually happens.

## Deferred

- Routing plain runs through the same outline pipeline would fix the
  per-character kerning loss but changes the rendering of every existing
  label; separate decision, tracked as a follow-up issue.
- `usetex` support via `get_glyphs_tex`.

## Ecosystem constraints

curved-text is listed in matplotlib's third-party package registry
(mpl-third-party). The implementation therefore uses public matplotlib API
only, verifies the declared matplotlib floor in CI, and adds a non-blocking CI
job against matplotlib pre-releases so upstream breakage surfaces here before
users meet it.
