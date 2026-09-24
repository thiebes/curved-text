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
    1/100-em units, baseline at `v = 0`, memoized per text, font properties, and
    usetex setting. `_PlainGlyph` reads it from `TextToPath.get_text_path`;
    `_MathRun` from `TextToPath.get_glyphs_mathtext` (or `get_glyphs_tex` under
    usetex, see below), subdividing rule boxes (fraction bars, radical
    overlines) with `_densify` so the long straight runs follow the curve. Glyph
    units are resolution independent; only the per-draw pixel scale varies.
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

## LaTeX (`usetex`)

When a segment's usetex setting is on (the `text.usetex` rcParam, or
`usetex=True` passed through the kwargs), LaTeX lays out both segment kinds, so
a curved label matches the figure's other usetex text. The run architecture
carries over unchanged; three details make the outline agree with the advance
matplotlib measures, and a fourth puts the `valign` lines on the drawn font.

- **Layout at the label size.** matplotlib measures a usetex advance by running
  LaTeX at the label's own size, and TeX fonts change design with size (cmss8 at
  8 pt, cmss12 at 12 pt). `TextToPath` runs LaTeX at its fixed 100 pt
  `FONT_SCALE`, which would draw a different design from the one measured:
  thinner letters with loose tracking on small labels. `_tex_to_path(size)`
  returns a converter whose public `FONT_SCALE` is the label size. The
  measurement and the outline then share one cached LaTeX run. The converter
  loads usetex glyphs with FreeType hinting on a grid of `FONT_SCALE` points at
  its public `DPI`, and at the default 72 dpi a 10 pt label is hinted on a
  10-pixel em, which snaps an x-height of 0.44 em to 0.50 em. The converter's
  `DPI` is therefore set so the em spans 100 pixels at every size. The hinting
  is then negligible, and the outline comes out in 1/100-em layout units.
- **Plain text is literal.** Each plain character is its own segment, so TeX
  commands cannot span plain text anyway. A plain glyph's text is the
  character's literal TeX source (`_tex_source`): markup characters are escaped,
  and `<`, `>`, and `|`, which the default OT1 encoding typesets as other
  glyphs, are spelled out by name. The escaped text is set once at
  construction, when matplotlib also fixes the artist's usetex setting, so
  matplotlib's own measurement, figure layout (`bbox_inches="tight"`), and the
  outline all read the same string. Overriding matplotlib's private
  `Text._preprocess_math` hook would escape the text without changing
  `get_text()`, and was rejected under the public-API constraint below.
- **Whitespace advances.** matplotlib's DVI reader sizes its output from the
  glyphs and rules TeX sets, and glue alone sets neither, so a bare space
  measures zero wide. Whitespace (TeX reads a tab as a space) is typeset as an
  interword space between two 1sp rules, which measures the true interword
  width.
- **`valign` reads the drawn font.** Under usetex the text is drawn in a TeX
  font chosen by the preamble, font family, and size, never in the matplotlib
  font the label's font properties name, so the `valign` lines come from TeX.
  The ascender and descender lines are the height and depth TeX gives `()gy`
  (`_tex_font_lines`), measured once per draw with matplotlib's own
  `TexManager.get_text_width_height_descent`. The parentheses reach the
  ascender line, and `g` and `y` reach the descender line in fonts whose
  parentheses stop short of it, such as typewriter fonts and Times. TeX takes
  the box from the font's metrics at the size it draws the font, so a font the
  preamble loads scaled (`helvet` with `scaled=0.92`) gets lines scaled with
  its glyphs.

The box of `()gy` tracks each font's designed lines. For Times and Helvetica it
gives ascenders of 0.675 and 0.728 em and descenders of -0.216 and -0.212 em,
against 0.683, 0.729, -0.217, and -0.218 em in their AFM files. Reading the
Type 1 font file through FreeType was rejected. FreeType reports a Type 1 font's
bounding box as its ascender and descender, which depends on the glyphs the
file contains, not on the letters' design: Latin Modern Sans draws the same
letters as Computer Modern Sans, but its file reports an ascender of 1.159 em
against 0.758 em.

Without usetex the lines are the ascender and descender FreeType reads from the
matplotlib font. For a TrueType font such as DejaVu Sans that is the ascender
the font's designer set for line spacing (0.928 em), about 0.17 em above the
tops of its letters. The two modes therefore place `"ascender"` differently
against the letters: without usetex the curve runs a little above the tallest
letters, and under usetex it touches them.

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
- Under `usetex`, plain text is typeset literally, one character at a time; TeX
  commands work only inside `$...$`. This differs from matplotlib's own usetex
  `Text`, which passes the whole string to TeX.
- Under `usetex`, plain text is limited to characters the LaTeX preamble can
  typeset. By default a Greek letter in plain text is a LaTeX error, as it is in
  matplotlib's own usetex text. Math-run Greek (`$\lambda$`) is italic, the
  convention for variables; plain Greek, like the rest of plain text, should be
  upright, and lowercase upright Greek needs a LaTeX package. The README gives
  a preamble recipe (`upgreek` plus `\DeclareUnicodeCharacter`). The library
  does not load packages itself: the preamble is one global rcParam that also
  governs layout passes outside the library's draw, so injecting a package only
  during its own draws would measure and draw with different preambles, and
  setting it globally would change the user's other usetex text. A straight `"`
  typesets as a closing curly quote, as it does in matplotlib's own usetex text.
- Tall constructs degrade by vertical compression on the inside of bends;
  the docstring states this and leaves label-size-to-curvature judgment to the
  user.

## Test pins

Beyond ports of the existing behavioral suite (ordering, offset, dpi
invariance, overrun, idempotent redraw, degenerate curve, zorder, remove,
fontsize pass-through), these tests carry the design:

- Straight-line equivalence: the placed path of a math run on a straight
  horizontal curve reduces to a plain affine reconstructed from its own layout.
  Pins datum, width, scale, and dpi handling at once.
- Anti-rigidity: a math label spanning a wide circular arc keeps every path
  vertex within `radius +/- label reach`, a bound chord placement would violate.
  Pins that bending actually happens.
- No per-glyph step: on a slanted straight guide the cap tops of mixed plain
  glyphs are collinear to sub-pixel. Pins the shared-baseline placement.
- Plain/math alignment: a math `x` and a plain `x` land on the same baseline,
  under mathtext and under usetex.
- Usetex design match: the ink-to-advance ratio of a plain glyph is the same at
  8 pt and 30 pt, which fails if the outline is laid out at a size other than
  the one measured.
- Usetex `valign`: a `()gy` label straddles a flat curve under `"center"` and
  touches it at the top or bottom under `"ascender"` or `"descender"`, for
  Computer Modern, its typewriter font, Latin Modern, Times, and Helvetica
  loaded at `scaled=0.92`. The cases fail when the lines come from the
  matplotlib font, from a Type 1 font file's bounding box, from the unscaled
  font, or from parentheses alone.
- Usetex `box`: the casing centreline sits midway between the top and bottom of
  `()gy` under every `valign`, which fails when the casing takes its centre line
  from the matplotlib font instead of the drawn one.
- `valign` without usetex: the `"ascender"` shift equals the ascender of the
  font the label names, for DejaVu Sans and for STIXGeneral.

## Deferred

- Hinted outlines via `FT2Font.get_path` (recovers grid-fit stem weight, which
  rotation largely defeats anyway); marginal gain, not pursued.
- Inter-character kerning for plain runs. Each plain character is laid out and
  advanced on its own, so kerning pairs between adjacent glyphs are not applied.
  The per-character placement that rides the curve is what makes this hard:
  kerning is a pairwise shift, and the glyphs do not share one layout pass.

## Ecosystem constraints

curved-text is listed in matplotlib's third-party package registry
(mpl-third-party). The implementation therefore uses public matplotlib API
only, verifies the declared matplotlib floor in CI, and adds a non-blocking CI
job against matplotlib pre-releases so upstream breakage surfaces here before
users meet it.
