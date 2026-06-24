# Design: mathtext support

## Decision

`CurvedText` accepts matplotlib mathtext (`$...$`) inside the label string.
The label is tokenized into runs: each plain character and each math run is
rendered from its glyph outline, positioned so a single shared text baseline
follows the curve. A plain character is placed rigidly (one rotation, shape
undistorted); a math run bends its glyph outlines through the curve's arc-length
frame so radicals and fractions stay connected. Mathtext arrives through the
existing `text` argument, and `pos`, `anchor`, `offset`, `valign`, and the kwargs
pass-through keep their meaning.

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

Plain characters and math runs share one baseline and one outline-placement
mechanism, differing only in rigidity:

- Plain characters are placed rigidly, each rotated to the chord across its own
  advance, so the glyph shape is undistorted.
- Math runs bend continuously through the frame.

The two regimes are the same frame at different scales of discretization: a
rigid glyph is the glyph-scale case of the bend map, so on a straight section
they coincide exactly, and within the width of one glyph the difference is far
below a pixel at any curvature where text is readable. Both ride the text
baseline as their shared datum, so plain and math sit level by construction and a
glyph's perpendicular distance from the curve is exactly its height above the
baseline -- there is no per-glyph step. (Placing plain text instead as rotated
`Text` artists, the earlier approach, let matplotlib align each glyph from its
own rotated bounding box, scattering the baselines by a few pixels.)

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
- `_OutlineSegment(matplotlib.text.Text)`: the shared base for both segment
  kinds. Subclassing `Text` inherits kwargs handling identically across
  segments, and `get_window_extent` measures both plain text and mathtext, so
  the parent's measurement loop has no special case. It owns `draw` and the
  outline-to-curve mapping; subclasses supply only the outline source
  (`_outline_units`) and the `_bend` flag.
  - `_outline_units()` returns the segment's outline `(vertices, codes)` in
    1/100-em units, baseline at `v = 0`, memoized per text and font properties.
    `_PlainGlyph` reads it from `TextToPath.get_text_path`; `_MathRun` from
    `TextToPath.get_glyphs_mathtext`, subdividing rule boxes (fraction bars,
    radical overlines) with `_densify` so the long straight runs follow the
    curve. Glyph units are resolution independent; only the per-draw pixel scale
    varies.
  - `_placed_path(renderer)` builds the placed compound path in display pixels.
    For a math run (`_bend = True`) every outline point is bent through the
    frame, bezier control points mapped directly (the approximation vector
    editors use for path bending). For a plain glyph (`_bend = False`) the whole
    outline takes one rigid rotation about its centre on the curve, so its shape
    is preserved.
  - `draw(renderer)` fills the compound path with one `renderer.draw_path` call
    using the artist's color and alpha, clipping set through public
    `GraphicsContext` methods, wrapping the renderer in a `PathEffectRenderer`
    when effects are set. With no frame assigned it draws nothing.
  - `_set_placement(frame, s_left, width_px)` is the per-draw handoff the parent
    calls. Any perpendicular offset is already baked into `frame` (it is the
    parallel curve), so a segment needs no offset of its own.
- `CurvedText` builds children from `_split_runs` (honoring `parse_math`), and
  its draw walks one cursor over the segments, handing each its placement. The
  child list is named `_segments`, since elements are characters and runs alike.

## Vertical datum

Every segment -- plain glyph and math run -- measures height from the text
baseline; that shared zero is what makes plain and math level by construction (a
math run's main symbols sit on the same baseline as the neighbouring plain
characters, and the math axis for fractions sits at its standard offset above
it). The `valign` control then chooses which line rides the curve, by subtracting
a single font-metric datum from every segment's height before placement:
`"center"` (the default, `(ascender + descender) / 2`) so the text straddles the
curve, `"baseline"` (`0`), `"ascender"`, or `"descender"`. Because the datum is a
font metric, not a per-glyph box, it is identical for every glyph and introduces
no step. The default is `"center"` because it reproduces the placement of the
superseded `va="center"` per-character design, keeping the `offset` reference
backward compatible -- minus the per-glyph step, which was that design's bug.

Centering on a segment's *own* layout box was rejected: a superscript or tall
delimiter inflates the box, so centering on it dropped the body below the plain
characters. A shared font-metric datum is immune, because it does not depend on
the segment's own extent. Pinned by tests: a math `x` shares the baseline of a
plain `x`, an exponent extends the run upward without moving its body, and
`valign` shifts the whole label by one constant with no per-glyph step.

## Path effects

Keyword arguments reach every child, so `path_effects` flow to every segment.
`_OutlineSegment.draw` draws its own placed path, so it wraps the renderer in a
`PathEffectRenderer` when effects are set. The effect strokes the placed outline,
so a white `withStroke` casing follows the curved text and clears the lines a
label crosses. This is the matplotlib-native idiom for a light, glyph-hugging
casing.

## Casing (`box`)

A `path_effects` stroke cannot give solid coverage under plain text: each
character is its own artist that strokes then fills, so a wide neighbor stroke
overwrites the previous glyph's fill. The `box` parameter solves the
full-coverage case with a different mechanism -- a single `Line2D` casing
following the offset curve across the label's span, its linewidth set to the
tallest glyph's height scaled by `pad` (default 1.1), drawn as one fill so
nothing cannibalizes. Its centreline is shifted off the curve by the glyph
band's offset (the text rides its baseline, so the ink sits to one side of the
bare curve) so the band covers the ink. It is a child artist positioned per draw
in `CurvedText.draw`, like the glyphs. When `draw` bails out early (no segments,
detached axes, or a degenerate curve) it hides the casing, so a stale band is
never left painted.

Layering is by zorder, applied once in `__init__` and maintained by
`set_zorder`: the container at `z`, the casing at `z + 0.5`, the glyphs at
`z + 1`. The casing must sit above the container because the container's `draw`
is what positions it -- a lower zorder would draw the casing before its geometry
is set, leaving it stale or empty. It must sit below the glyphs so the text
reads on top.

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

- Straight-line equivalence: the placed path of a math run on a straight
  horizontal curve reduces to a plain affine reconstructed from its own layout.
  Pins datum, width, scale, and dpi handling at once.
- Anti-rigidity: a math label spanning a wide circular arc keeps every path
  vertex within `radius +/- label reach`, a bound chord placement would violate.
  Pins that bending actually happens.
- No per-glyph step: on a slanted straight guide the cap tops of mixed plain
  glyphs are collinear to sub-pixel. Pins the shared-baseline placement.
- Plain/math alignment: a math `x` and a plain `x` land on the same baseline.

## Deferred

- `usetex` support via `get_glyphs_tex`.
- Hinted outlines via `FT2Font.get_path` (recovers grid-fit stem weight, which
  rotation largely defeats anyway); marginal gain, not pursued.

## Ecosystem constraints

curved-text is listed in matplotlib's third-party package registry
(mpl-third-party). The implementation therefore uses public matplotlib API
only, verifies the declared matplotlib floor in CI, and adds a non-blocking CI
job against matplotlib pre-releases so upstream breakage surfaces here before
users meet it.
