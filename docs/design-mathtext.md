# Design: mathtext and LaTeX support

## Decision

`CurvedText` accepts matplotlib mathtext (`$...$`) inside the label string.
The label is tokenized into runs: each plain character and each math run is
rendered from its glyph outline, positioned so a single shared text baseline
follows the curve. A plain character is placed rigidly (one rotation, shape
undistorted); a math run bends its glyph outlines through the curve's arc-length
frame so radicals and fractions stay connected. Mathtext arrives through the
existing `text` argument, and `pos`, `anchor`, `offset`, `valign`, and the kwargs
pass-through keep their meaning. Under usetex LaTeX lays out the same segments;
the LaTeX section below covers what changes.

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
  width, so the glyph shape is undistorted.
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
  segments, and `_size_px` measures both plain text and mathtext through
  matplotlib's `get_window_extent`, so the parent's measurement loop has no
  special case; a usetex plain glyph overrides it to read its run (see the
  LaTeX section). It owns `draw` and the outline-to-curve mapping and the
  outline cache; subclasses supply the outline source (`_build_outline`) and
  the `_bend` flag, and a usetex plain glyph also takes its size and outline
  from its run (`_size_px`, `_outline_units`). Segments stay out of figure layout (`set_in_layout`):
  the parent positions them when it draws, so their own `Text` position is not
  where they appear, and an unclipped label measured there would stretch a
  tight bounding box to it. That position is the display origin (an
  `IdentityTransform`), not the data origin, because `_size_px` still measures
  the segment there, and the data origin has no pixel on a logit axis, on a
  log axis that masks non-positive values, or on polar axes whose radial
  limits start above zero. A `transform` keyword forwarded from the label is
  replaced for the same reason; the segment never uses it.
  - `_outline_units()` returns the segment's outline `(vertices, codes)` in
    1/100-em units, baseline at `v = 0`, memoized per text, font properties, and
    usetex setting. It calls the subclass's `_build_outline` on a cache miss.
    `_PlainGlyph` reads the outline from `TextToPath.get_text_path`, or under
    usetex from its run (see the LaTeX section), whose cache it then uses;
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
  - `_set_placement(frame, s_left, width_px, datum)` is the per-draw handoff the
    parent calls. Any perpendicular offset is already baked into `frame` (it is
    the parallel curve), so a segment needs no offset of its own.
- `CurvedText` builds children from `_split_runs` (honoring `parse_math`), and
  its draw walks one cursor over the segments, handing each its placement. The
  child list is named `_segments`, since elements are characters and runs alike.
  The container draws nothing itself, so its draw places the segments and
  the casing (`_place_on_curve`).
- Units: the container keeps a copy of the curve as the caller gave it, as
  `Line2D` copies its data, and converts it with the axes' unit converters in
  `_curve_px`, before projecting it. Drawing, measuring (`get_window_extent`),
  and picking (`contains`) all place the label through `_curve_px`, so all
  three see the axes' current units; converting in `draw` alone would measure
  and pick an unconverted curve before the first draw. The converted curve is
  kept until either axis's units change, as matplotlib's lines keep theirs:
  each axis's public `"units"` callback, which also makes the lines convert
  again, drops it. Converting on every measurement would cost a long curve of
  `datetime` objects about 125 ms per measurement at 100,000 points, several
  times a draw under constrained layout or a legend at `loc="best"`. The
  callbacks are not picklable, so a pickled label drops them with its
  converted curve and connects them again when it is next placed. The
  placement key holds the projected pixels, so a change of units places the
  label again. Construction sets up an axis without units from the curve, as
  `plot` does, and leaves an axis that has them alone, so data it cannot
  convert raises `ConversionError` instead of replacing the converter the
  axes' other artists use. It sets up and converts the x axis before the y
  axis, so data the x axis rejects leaves the y axis as it was; like `plot`,
  it can leave an axis set up, or with new categories, when the curve then
  fails validation (1-D, equal length, at least two points, finite, with
  masked points as NaN). The container's own `Text` position is the caller's
  first point, taken by position (a pandas Series indexes by label). The
  casing needs nothing: it maps display points back to plain floats, which an
  axis passes through unconverted.
- Figure layout measures the label through the container's
  `get_window_extent`: the box of the placed glyphs' outline control points
  and the casing's band.
  The curves lie inside their control points, so the box can exceed the ink by
  a fraction of a pixel but never falls short of it. Exact curve extrema
  (`Path.get_extents`) would make a draw with a legend at `loc="best"`, which
  measures every text in the axes, about ten times slower. Constrained layout
  measures before the first draw has placed anything, so the label is placed
  to be measured. A measurement reuses the last placement while its key
  (`_placement_key`) is unchanged: the renderer, its resolution, the curve's
  position on the canvas, and each segment's text, font, and usetex setting.
  A legend measuring the label right after its draw therefore does not place
  it again, and every draw places afresh. The container's own `Text`, a single
  space at the curve's first point, takes no part, since its extent is that
  one point. The box casing counts by its band, half its line width beyond
  its centreline on every side, which also covers its round caps. Each
  segment reports an empty extent, so a legend, which measures
  every text in the axes, counts each label once and never at a segment's
  unused `Text` position, the display origin; the container measures a segment's
  size through matplotlib's `Text` measurement (`_size_px`). Without a
  renderer, as on a PDF canvas outside a draw, the label is measured with a
  one-pixel Agg renderer at the figure's dpi, kept per dpi
  (`_measuring_renderer`). A clipped label stays out of figure layout, as
  matplotlib leaves out every artist clipped to the axes.

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
The font lines come from the font the text is drawn in, so under usetex they
come from TeX; the LaTeX section below explains how, and how the two differ.

Centering on a segment's *own* layout box was rejected: a superscript or tall
delimiter inflates the box, so centering on it dropped the body below the plain
characters. A shared font-metric datum is immune, because it does not depend on
the segment's own extent. Pinned by tests: a math `x` shares the baseline of a
plain `x`, an exponent extends the run upward without moving its body, and
`valign` shifts the whole label by one constant with no per-glyph step.

## Kerning

Each plain character is its own segment, so matplotlib never lays two of them
out together and never applies the kern between them. `_kerns_px` adds it
back: between two consecutive plain glyphs it is the kern matplotlib's own text
layout applies to the pair, and next to a math run it is zero. A segment's
span, its width plus that kern, sets where the next segment starts, while the
glyph keeps its own width as the chord it is rotated by. Crowding's gap is
centred on the span, so the kern stays between the pair it belongs to. Under
usetex the kern is TeX's, from the glyph's run; see the LaTeX section.

The kern is read from matplotlib's layout of the pair (`_font_kern_units`),
cached per font file, pair, and the `text.hinting_factor` and
`text.kerning_factor` rcParams that select matplotlib's font object. Reading
FreeType's `get_kerning` directly was rejected. It reads only the font's `kern`
table, which matplotlib uses up to 3.10. From 3.11 matplotlib lays out text
through HarfBuzz, which reads the GPOS table instead, and many fonts keep their
only kerning there (STIXGeneral, Calibri) or a different one (Segoe UI). The
direct reading missed matplotlib 3.11 by up to 6.6 px at 30 pt.

How the kern is isolated depends on the version:

- Up to 3.10 the layout sets the right glyph at the left glyph's unhinted
  advance plus the kern, so the kern is the remainder.
- From 3.11 HarfBuzz also shapes the pair: it reorders right-to-left text, picks
  Arabic joining forms, attaches combining marks over their base, hides format
  characters such as the soft hyphen, and rounds advances to 1/64 pixel. Each
  of these would read as a kern under the remainder rule; the soft hyphen alone
  pulled the next glyph back over the previous one. The kern is therefore the
  difference between the pair laid out with and without the `kern` feature,
  which cancels everything else exactly.

Three cases take no kern: a pair the layout does not set as two glyphs (an
`fi` ligature), a pair whose font lacks either character, and right-to-left
characters, which curved labels draw in logical order, so even a real kern
would land on the wrong pair.

## LaTeX (`usetex`)

When a segment's usetex setting is on (the `text.usetex` rcParam, or
`usetex=True` passed through the kwargs), LaTeX lays out both segment kinds, so
a curved label matches the figure's other usetex text. The run architecture
carries over unchanged. The first bullet below makes the outline agree with
the advance matplotlib measures, the bullets after it cover plain-text runs,
and the last puts the `valign` lines on the drawn font.

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
  `DPI` is therefore set so the em spans at least 100 pixels, which makes the
  hinting negligible. FreeType takes the DPI as a whole number while
  matplotlib's DVI reader places glyphs at the exact value, so a fractional DPI
  would shrink the glyphs (2.8% at 190 pt). The DPI is rounded up to a whole
  number, and `_layout_units` rescales the outline to 1/100-em layout units by
  the remaining factor, which is within 1.4% of 1 up to 72 pt.
- **One LaTeX pass per plain run.** Each plain run is typeset once
  (`_typeset_tex_run`) and split per character. Typesetting each character on
  its own would run LaTeX once per distinct character and lose TeX's kerning
  between neighbours. Each printing character sets one item, a glyph or a rule
  (`\_` draws a rule in the default encoding), and the items, taken in order
  along the run, pair with the printing characters. A character's outline is
  its item, its width the item's own width, and its span the distance to the
  next character, which carries TeX's kern (`_PlainGlyph._tex_kern_units`). A
  usetex plain glyph's `_size_px` reads its width and height from the run, so
  matplotlib never measures it on its own. The height approximates the one
  matplotlib gives the character on its own: at least the box of `lp`, as for
  every line of usetex text, and for a taller character its ink, which stands
  in for its TeX box to within a fraction of a pixel (0.3 px at 26 pt).
  The run sits in an `\mbox`, so a long run stays on one line instead of
  breaking where matplotlib's LaTeX paragraph ends.
- **Cost.** LaTeX runs once per distinct plain run, as matplotlib runs it once
  per usetex string. A 37-character label's first draw takes about 2 s with an
  empty TeX cache. Each new label string costs one LaTeX run, so a figure with
  many short new labels runs LaTeX once per label. Typesetting per character
  was rejected: a new string could reuse characters already in TeX's cache, but
  each distinct character costs a run (9 to 10 s for the same label), and TeX
  never sets two characters together, so nothing is kerned. One LaTeX job per
  draw for every new run would cut the many-labels cost (#43).
- **Cache.** Runs are cached per run, size, and the rcParams matplotlib's
  `TexManager` writes the LaTeX preamble from: the user's
  preamble, `font.family`, and each family's font list, such as `font.serif`,
  from which it picks the font package. A change to any of them typesets the
  run again, and a glyph's outline and width come from the same pass, so a
  redraw after the change cannot mix two fonts. Keying on
  `TexManager.get_basefile`, which hashes the whole LaTeX job, was rejected: it
  rebuilds the job's source on every call, about 150 microseconds on
  matplotlib 3.10 and 3.11, and a draw reads every glyph's run, which tripled
  the redraw time of a figure with ten labels. The cache holds 1024 runs,
  enough that a large figure's runs are not read back from their DVI files on
  every draw.
- **Ligatures and characters that cannot be paired.** TeX fonts join pairs such
  as `fi`, `--`, and ` `` ` into one glyph, which would leave two characters
  with one item; an empty group between such a pair keeps them apart
  (`_TEX_LIGATURES`). A character TeX builds from several items, such as `é`,
  which the default OT1 encoding sets as an accent over an `e`, leaves the item
  count unequal to the character count. A control or format character, such as
  a soft hyphen, can set no item, and a combining mark joins the character
  before, so with one of them the counts could agree while the pairing is
  wrong; a run holding one is not paired at all (`_TEX_UNPAIRED_CATEGORIES`).
  Either way the run is typeset one character at a time: its glyphs take
  matplotlib's measurement of each character on its own, and no kern.
- **Plain text is literal.** Each plain character keeps its literal TeX source
  (`_tex_source`): markup characters are escaped, and `<`, `>`, and `|`, which
  the default OT1 encoding typesets as other glyphs, are spelled out by name,
  so TeX commands cannot span plain text. A glyph's own text is that source,
  set once at construction, when matplotlib also fixes the artist's usetex
  setting, so a run typeset one character at a time measures and draws the same
  string. Overriding matplotlib's private `Text._preprocess_math` hook would
  escape the text without changing `get_text()`, and was rejected under the
  public-API constraint below.
- **Whitespace advances.** matplotlib's DVI reader sizes its output from the
  glyphs and rules TeX sets, and glue alone sets neither, so a bare space
  measures zero wide. In a run, each whitespace character (TeX reads a tab as a
  space) is a control space, an interword space TeX neither drops at the ends
  nor collapses in a row, and a 1sp rule at each end of the run makes the
  reader measure spaces there. A run of spaces splits the gap between its
  neighbours evenly (`_char_lefts`). A control space takes no extra sentence
  spacing after a period, unlike a space in matplotlib's own usetex text. On
  its own, a space is an interword space between two 1sp rules.
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
band's offset (the text rides its `valign` datum, so the ink band is centred off
the bare curve) so the band covers the ink. The band's centre line comes from
the same font lines as the label, under usetex the TeX ones. It is a child
artist positioned per draw in `CurvedText._place_on_curve`, like the glyphs.
When placement bails out early (no segments, detached axes, or a degenerate
curve) it hides the casing, so a stale band is never left painted.

The container draws nothing itself, so the properties that decide whether and
where the label shows reach the parts it draws. `set_visible` passes to every
segment and the casing; a hidden label is not placed and has an empty extent,
as matplotlib's own hidden text takes no room. `clip_on`, the clip box, and the
clip path pass to them as well, at construction and through the setters, so an
unclipped label keeps its casing outside the axes. Picking tests the mouse
against the box of each placed glyph (`contains`), as matplotlib's own text
tests its box; a click on the casing's band between glyphs is not a hit. The
segments take the forwarded `picker` but are never pickable themselves
(`pickable` is false), since matplotlib asks a picker function without calling
`contains`, and their `contains` is false for hover, since matplotlib's
`Text.contains` tests the base `Text` box at their unused position, the display
origin, not the empty extent they report. A click there picks nothing. The
label measures its casing, so the casing, like the segments, stays out of
figure layout itself.

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
- Under `usetex`, plain text is typeset literally, one run at a time; TeX
  commands work only inside `$...$`. This differs from matplotlib's own usetex
  `Text`, which passes the whole string to TeX. Each space is one interword
  space, without the extra sentence spacing TeX adds after a period in
  matplotlib's own usetex text.
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
- Kerning: the second glyph of "AV" and "To" starts where matplotlib's own
  layout puts it, for DejaVu Sans and for STIXGeneral, which keeps its kerning
  only in the GPOS table. It fails if the kern is dropped, split around the
  glyph, or read from the `kern` table under matplotlib 3.11. The kern is zero
  next to a math run, after a combining mark, within a ligature, after a soft
  hyphen, within a Hebrew pair, and for an unkerned cmr10 pair (exactly,
  despite HarfBuzz's rounding).
- Usetex runs: a label and a tight-bounding-box save ask LaTeX for the run and a
  fixed set of probes, never for a single character. "AV" and "To" are kerned
  exactly as TeX sets the pair. Ligature pairs, the markup characters (with
  `\_` as a rule), and spaces at either end and in a row each take one item. A
  run with `é`, alone or with a soft hyphen, is typeset one character at a time,
  in order. A long run at 72 pt stays on one line. A glyph's height matches
  matplotlib's measurement of the character on its own. After a change to
  `font.family` or to `font.serif`, a new label and a redrawn one both match
  the character typeset alone under the new rcParams.
- Figure layout: an unclipped label near its axes leaves a tight bounding box
  as it is without the label, instead of stretching it to the display origin. An
  unclipped label rising above the axes reaches the top of a tight bounding
  box, and constrained layout shrinks the axes for it on the first draw. A
  clipped one leaves the box as it is. The extent asked for at another `dpi`
  matches the label placed at that dpi to within 2% of its width. Without a
  renderer on a PDF canvas, before and after a save, it matches the Agg
  measurement. A measurement after an axis-limit change, or after a change to
  the glyphs' font size, matches the next draw. A legend at `loc="best"`
  measures each label without placing it again, and with a line across the top
  of axes that fill the figure goes to the lower left, which the glyphs' unused
  positions at the display origin would block. The extent is empty for a
  degenerate curve. On a logit axis and on a log axis with
  `nonpositive="mask"`, x or y, and on polar axes whose radial limits start
  above zero, a label on valid points draws inside the axes, each glyph as wide
  as on a linear axis.
- Units: a label on `datetime64` in seconds, microseconds, or nanoseconds, a
  list of `datetime`, a `DatetimeIndex` (naive or timezone-aware), a pandas
  Series of dates, categories on either axis, or dates on y places every glyph
  and its casing at the same pixels as a label on the plotted line's own
  converted data. So does a label made before anything is plotted, dates or
  categories, which sets up the axis to format its units, and one on a float
  Series whose index has no 0. After a switch from kilometres to metres the
  label stays on the line, which fails if the curve is converted once and
  kept, and so does an unpickled label. Drawing twice and measuring convert
  the curve no more after construction, and a change of units converts it
  once. Before the first draw, a measurement and a click see the converted
  curve, which fails if it is converted only in `draw`. `datetime64[D]`
  follows a changed date epoch. Plotted categories add no ticks and new ones
  do. Strings on a date axis raise `ConversionError`, keep the date converter,
  and leave the y axis without units. A masked point raises `ValueError`, and
  a change to the caller's array after construction does not move the
  label.

## Deferred

- Hinted outlines via `FT2Font.get_path` for non-usetex text (recovers grid-fit
  stem weight, which rotation largely defeats anyway); marginal gain, not
  pursued. Usetex glyphs are hinted by matplotlib, at a resolution where it is
  negligible (see the LaTeX section).
- Kerning for usetex runs that cannot be paired. A run with a character TeX
  builds from several items, such as `é` in the default OT1 encoding, or with a
  printing character that may set no item (a soft hyphen) or join the one
  before (a combining mark), is typeset one character at a time without
  kerning. Pairing items with characters there needs a way to tell which items
  belong to which character.
- One LaTeX job per draw for every usetex run not yet cached, so a figure with
  many short new labels starts LaTeX once rather than once per label (#43).

## Ecosystem constraints

curved-text is listed in matplotlib's third-party package registry
(mpl-third-party). The implementation therefore uses public matplotlib API
only, verifies the declared matplotlib floor in CI, and adds a non-blocking CI
job against matplotlib pre-releases so upstream breakage surfaces here before
users meet it.
