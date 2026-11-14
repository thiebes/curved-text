# Design notes

## Decision

`CurvedText` accepts matplotlib mathtext (`$...$`) inside the label string.
The label is tokenized into runs: each plain character and each math run is
rendered from its glyph outline, positioned so a single shared text baseline
follows the curve. A plain character is placed rigidly (one rotation, shape
undistorted); a math run bends its glyph outlines through the curve's arc-length
frame, so radicals (square-root signs) and fractions stay joined, on a tight
bend too, because the path is rounded where it is tighter than the ink (the
Tight bends section). Mathtext arrives through the `text` argument, and `pos`, `anchor`,
`offset`, `valign`, and the keyword argument pass-through keep their meaning.
Under LaTeX typesetting (usetex), LaTeX (a typesetting system) lays out the same
segments; the LaTeX section below covers what changes.

Two design invariants hold: all geometry is computed per draw in display space,
and the label is a composite artist: its parts are not children of the axes, and
`CurvedText.draw` places them and then draws them itself, the casing first and
the glyphs after it, with its own properties applied to each.

## Rules for changes

Each rule states a constraint and the reason for it.

- **Recompute layout on every draw.** Positioning logic belongs in
  `_place_on_curve`, not in `__init__`. Only a per-draw layout keeps the label
  on the curve through figure layout, resizing, and interactive panning and
  zooming, and both `draw` and `get_window_extent` place the label through it.
- **Do the geometry in display (pixel) space.** The curve is projected through
  `transData` once per placement, and spacing and offset are computed on the
  projected points. Spacing and offset are then correct at any resolution and
  figure size, which data-space arithmetic cannot give.
- **Place glyphs from their outlines on one shared baseline.** Never place plain
  text as rotated `Text` artists. matplotlib aligns a rotated `Text` from its own
  bounding box, which scatters the baselines of neighboring characters by a few
  pixels.
- **Keep the conversion of the curve behind `_curve_px`.** Drawing, measuring,
  and picking all place through it, so a later change of axis units reaches all
  three. Code that changes `_cx` or `_cy` after construction calls
  `_forget_curve_floats()`, or the label keeps drawing the old curve.
  `_unit_callbacks` stores each callback's registry, not its axis, because
  clearing the axes replaces the registries and their callback ids repeat.
- **Let `_CurveFrame` extend past the curve ends.** It clips arc length into the
  end links and follows the end tangents, so a label that overruns an end is not
  cut off. Tests depend on this behavior.
- **Decide upright in display space, at placement.** `upright` turns a label
  over by reversing the stretch before the frame is built, from the chord across
  the span the label covers (`_reads_leftward`), on every draw. An axis
  inversion or a changed view can change the answer, so it cannot be decided at
  construction. The label keeps its interval of the curve: the anchor arc length
  and `lead` are mirrored with the curve, so `pos` and `anchor` still refer to
  the curve as given and the label never overruns an end it did not overrun
  before.
- **Keep the parts out of the axes.** The axes holds only the label, so it
  never draws or measures a segment or the casing on its own. Measuring a
  segment would run LaTeX once per character under usetex, and an unclipped
  label would stretch a tight bounding box to the segments' unused position at
  the display origin. The container's `get_window_extent` reports the label.
- **Keep one zorder for the whole label.** The label draws its casing and then
  its glyphs inside its own `draw`, at its own zorder. The parts have none.
- **Take display properties from the label at draw time.** `draw` gives each
  glyph the label's color, alpha, path effects, and, with the casing, its URL,
  snap, sketch parameters, and clipping (`_pass_properties`, `_pass_common`),
  and the glyph the label's gid with its number, so a setter called after
  construction reaches what is drawn. The casing keeps its own color, alpha,
  and width, and takes no path effect. The font stays with each segment, which
  builds its outline from it. A new display property that should reach the
  drawn label is passed the same way. The `visible` and `rasterized` keywords
  are not forwarded to the segments: matplotlib measures a hidden text as an
  empty box, and warns for a rasterized text that does not draw itself through
  `allow_rasterization`.
- **Keep placement apart from drawing.** `_place_on_curve` returns a
  `_Placement` value and writes nothing to a segment, and a segment keeps no
  placement: `draw` places the label and draws each segment at the place it
  just made (`_draw_at`). A measurement with another renderer, for
  `get_window_extent` or picking, keeps a placement of its own and cannot
  change where the segments draw.
- **Pass extra keyword arguments to every glyph and math run.** They set the
  font and the usetex setting each segment builds its outline from. The one
  exception is `transform`, which each segment replaces with `IdentityTransform()`,
  because segments draw in display pixels and a data transform would move them.
- **Test with the Agg backend and measure the drawn outline.** Tests force a
  draw and read placement from `seg._placed_path(renderer, place)` with the
  place the label gave the segment, through the helpers `_place_of`, `_path`,
  `_anchor_xy`, and `_rotation_deg` in `tests/test_core.py`, not from
  `get_position` or `get_rotation`. Segments render outlines, so those getters
  do not describe where a glyph is drawn.

## Why bending, and what was rejected

Mathtext cannot survive the library's per-character construction: splitting
`$\propto D$` into characters destroys the expression before matplotlib's
parser sees it. Four approaches were considered.

**Unicode substitution.** Translate math to Unicode characters (`\propto` to
U+221D) and curve them as plain text. Rejected as a library mechanism: the
coverage ceiling is hard (fractions, radicals, sized delimiters, most
subscript letters have no Unicode form), mathtext styles variables in italic
from the math font so substituted text renders visibly differently, and a
library that silently rewrites user content does something the user did not
ask for. It remains good advice for users with simple symbols.

**One rigid block per math run.** Render each `$...$` run as a single child
`Text` artist, measured and rotated like a plain character. It needs little
code and is fully vector, but the run sits on its chord: on a curving piece of
the curve a long expression visibly detaches from the curve. Not chosen.

**Rigid per-glyph placement.** Decompose the mathtext layout into glyphs and
place each rigidly at its own arc position, rotated to the local tangent (the
classic text-on-path treatment). It has a structural flaw: composite
constructs are drawn in two frames. A radical's check mark is one rigid glyph,
while its overline is a rule box that must follow the curve. The junction error
grows with curvature times the construct's height, and the tallest constructs
(radicals, big delimiters, fractions) are exactly where it shows. Repairing this
requires grouping glyphs by parse-tree structure, which the public layout
application programming interface (API) does not expose. Rejected on
complexity.

**Bend everything through one frame (chosen).** Map every outline control
point and every rule box through the same curvilinear map

```text
(u, v) -> curve(u) + (v - datum) * normal(u)
```

where `u` is arc length along the label and `v` is height above the
baseline. Seams are impossible by construction because there is only one
frame. The single failure mode is smooth distortion that grows with label
height times curvature. The rate at which the map advances along the text is the
curve's own rate times `1 - kappa * v`, where `kappa` is the curvature and `v`
the height. On the inside of a bend the factor reaches zero at `v = R` and goes
negative past it, so the ink stops, reverses, and mirrors. Spacing along the
curve (`crowding`) scales the rate and cannot change that sign. See "Tight
bends" below for what the label rides instead.

## Mixed-string semantics

Plain characters and math runs share one baseline and one outline-placement
mechanism, differing only in rigidity:

- Plain characters are placed rigidly, each rotated to the chord across its own
  width, so the glyph shape is undistorted.
- Math runs bend continuously through the frame.

The two regimes are the same frame at different scales of discretization: a
rigid glyph is the glyph-scale case of the bend map, so on a straight piece of
the curve they coincide exactly. Within the width of one glyph the difference is
far below a pixel where the bend is gentle enough to read the text. Both lie on
the text baseline as their shared datum, so plain and math sit level by
construction, and a glyph's perpendicular distance from the curve is exactly its
height above the baseline: there is no per-glyph step. Placing plain text as
rotated `Text` artists is rejected, because matplotlib aligns each rotated `Text`
from its own bounding box, which scatters the baselines by a few pixels.

## Architecture

All code lives in `src/curved_text/_core.py`.

- `_Run` (NamedTuple: `is_math`, `text`) and `_split_runs(text)`: a pure
  tokenizer mirroring matplotlib's own rules. An odd count of unescaped `$`
  means the whole string is one plain run; `\$` in plain runs unescapes to
  `$`; empty plain runs between adjacent math runs are dropped; math runs keep
  their delimiters so they re-parse as written.
- `_CurveFrame`: the display-space curve geometry (projected points,
  cumulative arc length) with a vectorized point-and-tangent lookup. It clips
  arc length into the two end links and extrapolates there, so a label that
  overruns a curve end follows the straight tangent extension. Shared by the
  per-character walk and by math runs.
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
  - `_placed_path(renderer, place)` builds the placed compound path in display
    pixels, for a place made for that renderer.
    For a math run (`_bend = True`) every outline point is bent through the
    frame, with Bezier curve control points mapped directly (the approximation
    vector editors use for path bending). For a plain glyph (`_bend = False`) the whole
    outline takes one rigid rotation about its center on the curve, so its shape
    is preserved.
  - `_draw_at(renderer, place)` fills the compound path with one
    `renderer.draw_path` call using the segment's color and alpha, clipping set
    through public `GraphicsContext` methods, wrapping the renderer in a
    `PathEffectRenderer` when effects are set. `draw` itself draws nothing, so
    nothing but the label draws a segment.
  - A `_SegmentPlace` (frame, `s_left`, `width_px`, `datum`) is what the label
    hands it for one draw. Any perpendicular offset is already baked into
    `frame` (it is the parallel curve), so a segment needs no offset of its own.
- `CurvedText` builds its parts from `_split_runs` (honoring `parse_math`). They
  are not axes children. Its `_place_on_curve` walks one cursor over the
  segments and returns a `_Placement`, and its `draw` draws the casing and then
  each segment at its place. The list is named `_segments`, since elements are
  characters and runs alike.
- Units: the container keeps its own copy of the curve as the caller gave it
  (floats pass through conversion as they are, so converting the caller's
  array would share it) and converts it with the axes' unit converters in
  `_curve_px`, before projecting it. Drawing, measuring (`get_window_extent`),
  and picking (`contains`) all place the label through `_curve_px`, so all
  three see the axes' current units; converting in `draw` alone would measure
  and pick an unconverted curve before the first draw. The converted curve is
  kept until either axis's units change, as matplotlib's lines keep theirs:
  each axis's public `"units"` callback, which also makes the lines convert
  again, drops it. Converting on every measurement would cost a long curve of
  `datetime` objects about 0.15 s per measurement at 100,000 points, several
  times a draw under constrained layout or a legend at `loc="best"`. The
  callbacks are connected at construction, since the curve converted there is
  already kept. Removal disconnects each callback from the registry it was
  connected to: clearing the axes replaces the registries, whose new ids can
  repeat a removed label's. The callbacks are not picklable, so a pickled label
  drops them with its converted curve and connects them again when it is next
  placed. The placement key holds the projected pixels, so a change of units
  places the label again. Construction sets up an axis without units from the
  curve, as `plot` does, and leaves an axis that has them alone. Data that axis
  cannot convert raises `ConversionError` instead of replacing the converter
  that the other artists of the axes use. Construction sets up and converts the
  x axis before the y axis, so data the x axis rejects leaves the y axis as it
  was. Like `plot`, it can leave the x axis set up when the y axis then rejects
  its data. It can also leave an axis set up, or with new categories, when the
  curve then fails validation: 1-D, equal length, and at least two consecutive
  finite points, with masked points (points hidden by a NumPy masked array)
  read as NaN (not a number). The `box` casing is built before any of this, so a
  casing matplotlib cannot draw raises with the axes as they were. The
  container's own `Text` position is the caller's first finite point, taken by
  position (a pandas Series indexes by label). The casing needs nothing for
  units: it maps display points back to plain floats, which an axis passes
  through unconverted.
- Gaps: a point the projected curve gives no finite pixel (NaN, infinite, or
  masked, or one the axes' scale masks, such as x of 0 or less on a log axis
  with `nonpositive="mask"`) breaks the curve into stretches, as it breaks a
  `Line2D`. A stretch is a connected piece of the curve between gaps. A value
  outside a log or logit axis's domain (`_gaps_outside_domain`) breaks the curve
  too. `_curve_px` sets such a value to NaN against the axes' current scales.
  Without that check, under `nonpositive="clip"` (the default on a log axis),
  the value would project to a finite pixel far outside the axes. The link of a
  line toward it leaves the view, but a label measured along it would follow it
  out. Only the "log"
  and "logit" scales are checked, by name: "symlog" places every value, custom
  scales keep their own projection, and "functionlog", whose domain is where
  its forward function is positive rather than an interval of the data, is
  not handled. A hidden label whose own position is outside the domain gets
  the NaN box of a position without a pixel.
  `_place_on_curve` finds the stretch the label follows on the projected curve
  (`_stretch_at`), so drawing, measuring, and picking, which all place through
  it, see the same stretches. The drawn length is that of the links between two
  shown points (`_shown`), measured in one vectorized pass, and only the chosen
  stretch gets a `_CurveFrame`: a frame per stretch makes a placement on a curve
  with thousands of gaps tens of times slower. `pos` is a fraction of the drawn
  length, and the label follows the stretch that holds its anchor as though it
  were the whole curve. Past its ends the label follows its end tangents, over a
  gap if there is one, not the next stretch, so the label always sits at `pos`
  and never continues onto another stretch. A label meant to follow scattered or
  gappy points follows a smooth curve fitted to them instead, which it never
  draws. A point where one stretch ends and the next
  starts belongs to the stretch the label extends onto: the earlier one for
  `anchor="end"`, so a label ending there sits on the curve, and the later one
  otherwise. `pos` within a billionth of the drawn length of that point counts
  as the point, since `pos` times the length rarely lands on it exactly. A
  stretch of no length, such as two coincident points between gaps, holds no
  point, and the stretch the label follows leaves out the links of no length
  at its ends, such as a repeated last point, so a label overrunning it follows
  a real end tangent. Lengths are on screen, so a zoom can move the anchor onto
  another stretch. With no stretch left at draw time, as after a switch to a
  log axis on which no part of the curve is in the domain, the label is not
  placed. The container's `Text` position is the curve's first finite point, so
  it has a pixel wherever the curve does. An empty extent sits at the curve's
  first shown point, the same test placement uses.
- Figure layout measures the label through the container's
  `get_window_extent`: the box of the placed glyphs' outline control points
  and the casing's band.
  The curves lie inside their control points, so the box can exceed the ink by
  a fraction of a pixel but never falls short of it. Exact curve extrema
  (`Path.get_extents`) would make each measurement, and so each legend placement at
  `loc="best"` (which measures every text in the axes), several times slower. Constrained layout
  measures before the first draw has placed anything, so the label is placed
  to be measured. A measurement reuses the last placement while its key
  (`_placement_key`) is unchanged: the renderer, its resolution, the curve's
  position on the canvas, and each segment's text, font, and usetex setting.
  A legend measuring the label right after its draw therefore does not place
  it again, and every draw places afresh. The container's own `Text`, a single
  space at the curve's first finite point, takes no part, since its extent is
  that one point. The box casing counts by its band, half its line width beyond
  its centerline on every side, which also covers its round caps. Each
  segment reports an empty extent, so a legend, which measures
  every text in the axes, counts each label once and never at a segment's
  unused `Text` position, the display origin; the container measures a segment's
  size through matplotlib's `Text` measurement (`_size_px`). Without a
  renderer, as on a PDF canvas outside a draw, the label is measured with a
  one-pixel Agg renderer at the figure's resolution in dots per inch (dpi), kept
  per dpi (`_agg_renderer`). A clipped label stays out of figure layout, as
  matplotlib leaves out every artist clipped to the axes.

## Vertical datum

Every segment, plain glyph or math run, measures height from the text baseline.
That shared zero makes plain and math level by construction: a math run's main
symbols sit on the same baseline as the neighboring plain characters, and the
math axis for fractions sits at its standard offset above it. The `valign`
control then chooses which line lies on the curve, by subtracting a single
font-metric datum from every segment's height before placement:
`"center"` (the default, `(ascender + descender) / 2`) so the text straddles the
curve, `"baseline"` (`0`), `"ascender"`, or `"descender"`. Because the datum is a
font metric, not a per-glyph box, it is identical for every glyph and introduces
no step. The default is `"center"` because `offset` is then measured from the
vertical center of the text, the reference that `va="center"` gives a single
`Text`, and the shared datum keeps every glyph level. The font lines come from the font the text is drawn in, so under usetex they
come from TeX; the LaTeX section below explains how, and how the two differ.

Centering on a segment's own layout box is rejected: a superscript or tall
delimiter inflates the box, so centering on it drops the body below the plain
characters. A shared font-metric datum is immune, because it does not depend on
the segment's own extent. Pinned by tests: a math `x` shares the baseline of a
plain `x`, an exponent extends the run upward without moving its body, and
`valign` shifts the whole label by one constant with no per-glyph step.

## Kerning

Each plain character is its own segment, so matplotlib never lays two of them
out together and never applies the kern between them. Kerning is the
adjustment of the space between particular pairs of characters. `_kerns_px`
supplies it: between two consecutive plain glyphs it is the kern matplotlib's own text
layout applies to the pair, and next to a math run it is zero. A segment's
span, its width plus that kern, sets where the next segment starts, while the
glyph keeps its own width as the chord it is rotated by. Crowding's gap is
centered on the span, so the kern stays between the pair it belongs to. Under
usetex the kern is TeX's, from the glyph's run; see the LaTeX section.

The kern is read from matplotlib's layout of the pair (`_font_kern_units`),
cached per font file, pair, and the `text.hinting_factor` and
`text.kerning_factor` rcParams (matplotlib runtime settings) that select
matplotlib's font object. Reading FreeType's `get_kerning` directly was
rejected. It reads only the font's `kern` table, which matplotlib uses up to
3.10. From 3.11 matplotlib lays out text through HarfBuzz, which reads the GPOS
(glyph positioning) table instead, and many fonts keep their
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

## Crowding

`crowding="curvature"` solves one problem. Glyphs are rigid and rotate to the
chord across their own width, so on the concave side of a tight bend the glyph
boxes lose arc length and their ink collides. `"none"` (the default) spaces
glyphs by width and kerning only, and its layout is exactly the flat one.

The gap is computed per segment in `_advances`, along the offset curve that the
label follows:

1. `_CurveFrame.curvature(s, span)` estimates the signed turning rate
   (radians per pixel) over the segment's span. It takes the chord angle across
   each half of the span and divides the wrapped angle between the two chords by
   the distance between their midpoints, half the span. That is the glyph's own
   length scale, the scale over which rotation is smoothed, and it returns `1/R`
   on a circle of radius `R`. A straight piece of the curve returns zero.
2. A box of height `h` whose center lies on the curve has a concave edge `h / 2`
   nearer the center of curvature. That edge loses about `|kappa| * h / 2` of arc
   length per unit of advance. `crowd` is that fraction, capped at `_MAX_CROWD`
   (0.6).
3. Only the part of `crowd` past `_CROWD_SLACK` (0.2) is corrected: the gap is
   `max(0, crowd - 0.2) * h`. The deadband (a range below which no gap is added)
   exists because the sidebearing whitespace built into adjacent glyphs absorbs
   that much curvature before the ink collides. A bend with a radius of at least
   `2.5 h` and every straight run therefore keep their flat layout. The cap takes
   full effect at a radius of about `0.83 h` and bounds the gap at `0.4 h`.

The gap is a constant multiple of the line height, not of the glyph's width. A
multiple of the width would give wide glyphs a larger trailing gap, which reads
as uneven letterspacing on an arc. A constant gap gives every pair the same
space where the curvature is uniform. The height `h` is the segment's own
height, which is at least the height of `lp`, so a short glyph does not get a
smaller gap than its neighbors.

The span of each segment sits in the middle of its widened slot, so the gap
splits evenly around it and the kern stays between the pair it belongs to. The
curvature is sampled on the unwidened layout, anchored the same way, which is
accurate enough because the widening moves positions only slightly. The label
then spans the sum of the advances, starting from `s0 - lead * total`, so `pos`
and `anchor` still hold with the widened total. The anchor is converted from the
original curve to the offset curve (`remap_arc`) before this, so `offset` shifts
the label perpendicular to the curve without changing which part of the curve it
sits on. Because the frame is the offset curve, the curvature that sets the gap
is the offset curve's: it is larger on the concave side and smaller on the
convex side. The casing covers the widened span.

Pinned by tests: `test_crowding_none_leaves_glyph_positions_unchanged` (the
default is the flat layout),
`test_crowding_curvature_leaves_straight_line_unchanged`,
`test_crowding_curvature_spreads_glyphs_on_a_tight_bend`, and
`test_crowding_curvature_is_negligible_on_a_gentle_bend` (the deadband).

## Tight bends

A label rides a path, and every point of its ink sits at its own height from
that path along the normal. Where the path bends toward the ink more tightly
than the ink is tall, that placement has no valid answer: part of the label lies
farther from the path than the path's radius of curvature, past the center of
curvature. Two symptoms follow from the one cause.

- **Math runs.** The bend map advances at the curve's own rate times
  `1 - kappa * v`. On the inside of a bend the factor reaches zero at `v = R`,
  so a radical's overline hooks back along the curve and ink past the center of
  curvature is drawn mirrored.
- **Offset labels, plain text included.** An `offset` toward the inside of a
  bend that is larger than the bend's radius gives a parallel curve that runs
  backward for a stretch, so letters overlap or change order.

Spacing along the curve (`crowding`) scales the rate and cannot change the sign
of the factor. A fix has to change either the curvature of the path or the
heights of the ink.

**Rejected.** Stretching each math run so its inner edge keeps its natural width
removes the squeeze at moderate bends, but cannot prevent the fold, and does
nothing for offset labels. Bending math runs only partly leaves their ends
detached from the neighboring plain glyphs, which still follow the curve.
Compressing the heights of the ink on the inside distorts the glyphs. Warning
and leaving the output as it is does not help the label.

**Chosen.** Lay every label along a rounded copy of its curve, so the path has a
radius of at least a least value on each side, and plain and math segments stay
on one shared baseline. A ball of the least radius is rolled along each side of
the curve; where the curve bends more tightly than the ball, the ball's arc
replaces it. The rule is geometric. It handles smooth curves, the sharp corners
of a polyline (radius zero), and hairpins alike, and a bend gentler than the
ball is left exactly as it is, so a label on a gentle curve draws as it would
without the rounding.

The least radius, `min_radius`:

- `"auto"` (the default): `_MIN_RADIUS_CLEARANCE` (1.5) times the height of the
  label's ink on each side of the path. A left bend has the ink above the path
  on its inside, so it takes the height above the path; a right bend takes the
  depth below it. The ink band of each segment comes from the true extents of
  its outline (`_OutlineSegment._ink_band`), cached with the outline.
- A number, in points: the least radius for both sides.
- `None` or `0`: no rounding, the layout without it.

**Where it runs.** In `_place_on_curve`, after the stretch and the `upright`
decision and before the offset, so `pos`, `anchor`, the box casing, and every
segment read the rounded frame:

1. The offset `d` shifts the radii asked of the curve. The path at distance `d`
   to the left of a curve of radius `r` has radius `r - d` on a left bend and
   `r + d` on a right bend, so the curve is asked for `ride_left + d` and
   `ride_right - d`. The same rounding removes the swallowtail that a large
   offset creates.
2. A curvature test at the scale of the ball (`_CurveFrame.curvature`) decides,
   for each side, whether any bend within the label's reach is tight enough to
   matter. Where none is, that side is skipped.
3. The part of the curve the label can reach, with a margin of `_ROUND_REACH`
   radii on each side, is sampled at equal steps (extending along the end
   tangents past the ends of the curve, as the frame does). The label's length
   for this includes crowding's widest gaps. The samples sit on whole steps of
   arc length, so a small move of the label does not move the vertices. A point
   near the end of the sampled part does not see all the curve within reach of
   it, so when a bend comes within reach of either end, the margin doubles, up
   to `_ROUND_MAX_DOUBLINGS` times, and the part is sampled again. The rounding
   of the bends beside the label then does not depend on where the part ends,
   and the label does not jump as `pos` or the zoom changes. The loop stops
   early once the rounded path across the label has not changed for two
   passes, and a bend still in reach after the last doubling is rounded as far
   as the part shows it. A curve with bends all along it, such as noisy data,
   pays two or three passes: about 10 to 17 ms a draw, against 1 to 3 ms for a
   gentle curve or one isolated bend. A radius below
   `_ROUND_TOL_PX` is not rounded, and one above `_ROUND_MAX_RADIUS_PX` is
   clamped.
4. `_CurveFrame.rounded(radius, side, step)` runs for each side. The ball
   centers lie on the parallel curve. A point is one the ball cannot touch when
   the center is closer than the radius to another point of the curve within
   `_ROUND_REACH` radii of arc length. Each run of such points is laid on the arc
   of the ball wedged between the last valid point before it and the first valid
   point after it. If the two balls do not meet at one point, a cubic Hermite
   blend of the end points and their tangents replaces the arc. The rounded
   curve keeps the vertices of the sampled one.
5. The anchor, given on the curve as it was passed in, carries over to the
   rounded, offset frame through the shared vertices (`remap_arc`).

**Cost to the label.** Where a bend is tighter than the least radius, the label
leaves the curve: by about `0.29 * R_min` from either arm at a right-angle
corner (`0.41 * R_min` from the corner point) and by up to `R_min - R` at a
hairpin. The inside edge of the ink is squeezed to
`1 - 1/clearance` of its natural length at the least radius, a third at 1.5. A
clearance of 1.25 squeezes the inside edge more, and 2.0 moves the label
farther from the curve. Hyperbola valleys and peaks of radius 5 to 40 points, a
right-angle V, and labels of math, a fraction, plain text, and plain text with
an offset, at 10 and 20 points, showed no folding at 1.25, 1.5, 1.75, or 2.0;
1.5 was chosen as the middle of the range.

**Limits.** The guarantee that no ink folds holds for smooth curves and for
corners, and two kinds of curve fall outside it.

- A hairpin. The ball test reaches `_ROUND_REACH` radii along the curve. A bend
  that turns back so narrowly that the ball fits only farther along the curve
  than that is not laid on a ball. Its run of invalid points is blended with no
  radius guarantee, and the blend can distort the straight arms the label
  rides, so the label can fold where `min_radius=None` does not, wherever it
  sits on the arm. The largest apex angle at which a label still folded was
  18, 22, 26, and 30 degrees at 10, 14, 20, and 28 points, and 8 to 12 degrees
  gave about 25 to 80 violations (outline points closer to the path than their
  height) with a 14 point math label.
- Jagged input. Where the curve changes direction at nearly every sample, at
  the scale of the ink, the invalid runs are many and short. The balls either
  side of a run often do not meet, so the Hermite blend replaces the arc, and it
  has no radius guarantee. On a noisy sine the label folded far less than with
  `None`, but not never. Smoothing the tangents of the blend would remove this.
  For noisy data, pass a smoothed curve.

Interactions: `crowding="curvature"` samples the curvature of the rounded frame,
so it widens less at a rounded bend; `box` follows the rounded frame;
`valign` shifts the datum and so the heights; usetex changes only where the
outline comes from; pan, zoom, and dpi act in pixels on every draw.

Pinned by tests: `test_math_run_does_not_fold_in_a_tight_valley` measures the
placed outline against the invariant that every point sits at exactly its
height from the path it rides;
`test_offset_label_keeps_its_letters_in_order` and
`test_offset_path_never_runs_backwards` cover the offset symptom;
`test_a_gentle_bend_is_drawn_as_it_is_without_rounding` pins the layout where
no rounding is needed; `test_each_side_is_rounded_for_the_ink_on_the_inside_of_the_bend`
covers the radius taken for each side under every `valign`, on a valley and on a
peak; `test_auto_takes_one_and_a_half_times_the_ink_on_each_side` pins the
clearance; `test_the_label_moves_smoothly_as_pos_moves` pins the sampling that
does not depend on where the part ends; `test_a_narrow_hairpin_is_a_documented_limit`
pins the hairpin limit; and the radius, corner, fillet, anchor, end, zigzag, dpi,
zoom, crowding, and box tests cover the shape of the rounded path.

## Smoothing

**Problem.** A line of measured data wiggles at about a letter's width, even
after it is averaged. Each plain glyph is placed rigidly at its own point on the
curve and tilted by the chord across its own width. That removes wiggles much
shorter than a glyph, such as the vertices of a coarse polyline, but not wiggles
at a glyph's width: neighboring glyphs sample different tilts and heights, tilt
into each other, and step up and down. `crowding="curvature"` does not help, as
it answers a sustained bend, and these kinks are short and alternate in sign.

**Rejected.** Widening only the tilt window, which fixes half the symptom and
leaves the heights stepping. Leaving it to the user to smooth a copy of the
data, which every user of measured data must then find and repeat. Smoothing
every label by default: a smoothed path is not the line, so it moves labels off
it, and leaving smooth curves alone needs a test of whether the path wiggles
that cannot tell wiggles from a tight bend by how far smoothing moves the path
(the distance, a roughness measure against a cubic fit, and the sideways lean
were tried, and each overlapped).

**Chosen.** `smooth`, off by default, smooths the path the label rides, in
display pixels, before anything is laid on it. `_place_on_curve` calls
`_smoothed_stretch` on the stretch that holds the anchor, so the rounding of
`min_radius`, the offset, the casing, the reading direction, and every glyph
follow what the label rides, and the line itself is untouched.

- The width is a standard deviation in points of arc length, or `"auto"`: three
  quarters of the font size (`_SMOOTH_AUTO_EM`).
- Only the part of the stretch around the label is smoothed
  (`_smoothing_window`): the interval the label covers, with a margin either
  side of 24 widths or twice the label, whichever is larger, within the
  stretch. A long stretch, as a zoomed view of a long series gives, is then
  sampled as finely as a short one, and the cost does not grow with it. The
  margin gives the rounding and the offset smoothed path to work on near the
  label; where they reach further, as the rounding of a tight bend can, they
  find the end tangent of the part.
- The part is resampled evenly by arc length, every eighth of the width, from
  the stretch, which a frame extends past each end along its end tangent, so an
  end does not pull in. The samples stay one to one, which carries the anchor
  across (`np.interp` of the anchor's sample against the smoothed arc length). An
  anchor off the part, as `pos` outside 0 to 1 puts it, keeps its distance from
  the end.
- The step between samples depends on the width alone, and the part starts and
  ends on whole steps of arc length along the stretch, so the samples are the
  same wherever the label moves, and a label that moves a little moves only by
  that little. A part whose start followed the label put the samples on a new
  grid at every position, and a label with an offset or rounding on noisy data
  moved by about a pixel for a move of a few hundredths. Where the part would
  hold more than 20000 samples the step doubles until it does not, which keeps
  the grid. A label past the end of the stretch, even far past it, rides the
  last step of the part, so a width in points always smooths.
- The filter is a Gaussian corrected for the shrinking of bends: twice the
  smoothed path less the smoothed path smoothed again. A Gaussian alone pulls a
  circle in by sigma squared over twice its radius, and the correction leaves a
  smooth bend alone to second order. The cost is a small overshoot at a sharp
  corner, under a degree on a 37 degree corner.
- `"auto"` smooths only where the path wiggles under the label
  (`_path_reversals`). The path is laid out as chords each two thirds of the
  width long (half an em), end to end across the label. A turn is the change of
  direction from one chord to the next, of two degrees or more, and a wiggle is
  a turn the other way from the one before. The path wiggles with two or more.
  A bend turns the chords one way all through it, so it never counts. A half
  turn, where the path doubles back on itself, has no side, so it counts as a
  turn the other way from the one before. Chords that start at the same phase
  of a wiggle as they end see none, so the path is laid out from three starting
  offsets and the most reversals count. A number in points always smooths.
- Real monthly prices from matplotlib's sample data typically turn the chords
  back two to six times across a label, and the smooth analytic curves of the
  gallery, tight arcs and valleys among them, zero or one.

**Limits.**

- The label rides the smoothed path, so a line that wiggles by more than the
  label's offset can touch the letters. The gallery figure gives the label an
  offset larger than the wiggles.
- A width in points rounds a bend narrower than the width, and the label leaves
  the line there, as `min_radius` makes it leave a tight bend.
- The reversal count is a heuristic tuned on the sample stocks and the gallery's
  curves. A line with one slow wiggle under the label is not smoothed by
  `"auto"`, and a serpentine that alternates twice or more is, tight bends
  among them. Whether it smooths is a count, so it switches on and off as `pos`
  or the view moves, and the label moves by up to the size of the wiggles when
  it does. A number gives a steadier result, and is the choice for raw data. It
  is not perfectly steady: where the offset is larger than the radius of the
  smoothed path, a small change in the width or the view can move the label by
  the size of the wiggles.
- A path that turns by a steep angle each way, such as a sine whose amplitude is
  several times its wavelength, has chords that flip by nearly a half turn, and
  `"auto"` can miss it. Give a number there.
- The filter passes more at the scale of a letter than a plain Gaussian does, so
  on wiggles much larger than a letter a label keeps some of its jitter.

Pinned by tests:

- `test_a_label_on_measured_data_tilts_its_neighbors_less_when_smoothed`
  measures the jitter of glyph tilts on real prices.
- `test_a_smooth_curve_is_drawn_as_without_smoothing` pins that `"auto"` leaves
  gentle bends, a sine, and a straight run alone.
- `test_smoothing_does_not_shrink_a_circular_bend` pins the correction.
- The gate: `test_the_wiggle_test_tells_jitter_from_a_bend`,
  `test_auto_needs_two_reversals_to_smooth`,
  `test_auto_smooths_at_exactly_two_reversals_and_not_at_one`,
  `test_a_wiggle_of_two_chords_is_seen_at_every_phase`,
  `test_each_of_the_three_offsets_sees_a_wiggle_the_others_miss`,
  `test_a_path_that_doubles_back_on_itself_wiggles`,
  `test_a_steep_zigzag_wiggles`,
  `test_three_chords_can_reverse_once`,
  `test_a_path_that_wiggles_leftward_is_counted_as_one_that_goes_rightward`,
  and `test_a_path_that_turns_by_nearly_a_half_turn_the_same_way_never_reverses`.
- Where the gate looks:
  `test_auto_smooths_only_what_wiggles_where_the_label_covers`,
  `test_the_gate_stops_where_the_label_does`, and
  `test_the_gate_looks_where_the_label_is_for_each_anchor`.
- The part: `test_the_smoothing_window_is_on_a_grid_that_the_label_does_not_move`,
  `test_the_smoothing_window_reaches_a_margin_either_side_of_the_label`,
  `test_the_smoothing_window_coarsens_by_doublings_over_20000_samples`,
  `test_the_smoothing_window_keeps_one_step_past_either_end`,
  `test_a_smoothed_label_moves_only_as_far_as_its_pos_does`,
  `test_a_long_stretch_is_smoothed_as_accurately_as_a_short_one`,
  `test_a_very_wide_smooth_draws_without_error`, and
  `test_the_pixel_floor_and_the_step_floor_of_smoothing`.
- An anchor off the stretch:
  `test_a_pos_beyond_the_ends_keeps_its_distance_when_smoothed`,
  `test_smoothing_carries_an_anchor_off_the_stretch_by_its_distance`, and
  `test_a_width_in_points_smooths_for_a_label_far_past_an_end`.
- Units and defaults: `test_a_width_in_points_scales_with_the_dpi`,
  `test_auto_is_three_quarters_of_an_em`,
  `test_smoothing_keeps_the_anchor_on_a_symmetric_curve`,
  `test_smoothing_is_off_unless_asked_for`, and
  `test_the_default_of_the_class_is_no_smoothing_too`.

## LaTeX (`usetex`)

When a segment's usetex setting is on (the `text.usetex` rcParam, or
`usetex=True` passed through the keyword arguments), LaTeX lays out both segment
kinds, so a curved label matches the figure's other usetex text. The run
architecture carries over unchanged. A plain run is the plain text between math
runs, or between a math run and an end of the string. This section covers the
mechanism. The page [LaTeX typesetting (usetex)](https://thiebes.github.io/curved-text/usetex.html) tells users how to
enable it, what it requires, how plain text and Greek letters behave, how to set
the preamble, and how the caches behave. The first bullet below makes the
outline agree with the advance matplotlib measures, the bullets after it cover
plain-text runs, and the last puts the `valign` lines on the drawn font.

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
  matplotlib's reader of TeX's device independent (DVI) output places glyphs at
  the exact value, so a fractional DPI would shrink the glyphs (about 2.4% at
  190 pt). The DPI is rounded up to a whole number, and `_layout_units` rescales
  the outline to 1/100-em layout units by the remaining factor, which is within
  1% of 1 up to 72 pt.
- **One LaTeX pass per plain run.** Each plain run is typeset once
  (`_typeset_tex_run`) and split per character. Typesetting each character on
  its own would run LaTeX once per distinct character and lose TeX's kerning
  between neighbors. Each printing character sets one item, a glyph or a rule
  (`\_` draws a rule in the default encoding), and the items, taken in order
  along the run, pair with the printing characters. A character's outline is
  its item, its width the item's own width, and its span the distance to the
  next character, which carries TeX's kern (`_PlainGlyph._tex_kern_units`). A
  usetex plain glyph's `_size_px` reads its width and height from the run, so
  matplotlib never measures it on its own. The height approximates the one
  matplotlib gives the character on its own: at least the box of `lp`, as for
  every line of usetex text, and for a taller character its ink, which approximates
  its TeX box to within a fraction of a pixel (0.3 px at 26 pt).
  The run sits in an `\mbox`, so a long run stays on one line instead of
  breaking where matplotlib's LaTeX paragraph ends.
- **Cost.** LaTeX runs once per distinct plain run, as matplotlib runs it once
  per usetex string. A 37-character label's first draw takes about 2 s with an
  empty TeX cache. Typesetting per character was rejected: a new string could
  reuse characters already in TeX's cache, but each distinct character costs a
  run (9 to 10 s for the same label), and TeX never sets two characters
  together, so nothing is kerned. One LaTeX job per draw for every new run would
  cut the cost of a figure with many short new labels (see Deferred).
- **Cache.** Runs are cached per run, size, and the rcParams matplotlib's
  `TexManager` writes the LaTeX preamble (the LaTeX setup commands that come
  before the text) from: the user's preamble, `font.family`, and each family's
  font list, such as `font.serif`, from which it picks the font package. A
  change to any of them typesets the run again. A glyph's outline and width come
  from the same pass, so a redraw after the change cannot mix two fonts. Keying
  on `TexManager.get_basefile`, which hashes the whole LaTeX job, was rejected.
  It rebuilds the job's source on every call, about 150 microseconds on
  matplotlib 3.10 and 3.11, and a draw reads every glyph's run, which tripled
  the redraw time of a figure with ten labels. The cache holds 1024 runs, enough
  that a large figure's runs are not read back from their DVI files on every
  draw.
- **Ligatures and characters that cannot be paired.** TeX fonts join pairs such
  as `fi`, `--`, and ` `` ` into one glyph, which would leave two characters
  with one item; an empty group between such a pair keeps them apart
  (`_TEX_LIGATURES`). A character TeX builds from several items, such as `é`,
  which the default OT1 encoding sets as an accent over an `e`, leaves the item
  count unequal to the character count. A control or format character, such as
  a soft hyphen, can set no item, and a combining mark joins the character
  before, so with one of them the counts could agree while the pairing is
  wrong; a run holding one is not paired at all (`_TEX_UNPAIRED_CATEGORIES`).
  Either way the run is typeset one character at a time. Its glyphs take
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
  neighbors evenly (`_char_lefts`). A control space takes no extra sentence
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
against 0.683, 0.729, -0.217, and -0.218 em in the URW Adobe Font Metrics (AFM)
files. Reading the
Type 1 font file through FreeType was rejected. FreeType reports a Type 1 font's
bounding box as its ascender and descender, which depends on the glyphs the
file contains, not on the letters' design: Latin Modern Sans draws the same
letters as Computer Modern Sans, but its file reports an ascender of 1.159 em
against 0.758 em.

Without usetex the lines are the ascender and descender FreeType reads from the
matplotlib font. For a TrueType font such as DejaVu Sans that is the ascender
the font's designer set for line spacing (0.928 em), which lies above the tops
of the capital letters. The box of `()gy` ends nearer the capitals, so the two
modes place `"ascender"` at different heights against the letters. The page
[LaTeX typesetting (usetex)](https://thiebes.github.io/curved-text/usetex.html) gives the distances.

## Path effects

The label's `path_effects` pass to every segment at each draw.
`_OutlineSegment._draw_at` draws the placed path, so it wraps the renderer in a
`PathEffectRenderer` when effects are set. The effect strokes the placed outline,
so a white `withStroke` halo follows the curved text and clears the lines the
label crosses. It is the standard matplotlib way to draw a light halo close
around each glyph.

## Casing (`box`)

A `path_effects` stroke cannot give solid coverage under plain text: each
character is its own artist that strokes then fills, so the wide stroke of a
neighbor overwrites the previous glyph's fill. The `box` parameter solves the
full-coverage case with a different mechanism: a single `Line2D` casing
following the offset curve across the label's span, its linewidth set to the
tallest glyph's height scaled by `pad` (default 1.1), drawn as one fill so
no glyph's stroke overwrites another's fill. Its centerline is shifted off the
curve by the glyph band's offset (the text lies on its `valign` datum, so the
ink band is centered off the bare curve) so the band covers the ink. The band's
center line comes from
the same font lines as the label, under usetex the TeX ones. It is a part of the
label, placed per draw in `CurvedText._place_on_curve` and drawn by
`CurvedText.draw` before the glyphs. When placement fails early (no segments,
detached axes, no stretch of the curve with a span, or a degenerate offset
curve) `draw` clears every glyph's placement and draws nothing, so neither a
stale band nor stale glyphs are left painted.

The label draws its parts itself, so its own properties decide what is drawn.
A hidden label is not placed, draws nothing, and has an empty extent, as
matplotlib's own hidden text takes no room. `clip_on`, the clip box, and the
clip path apply to the glyphs and the casing as they are at each draw, so an
unclipped label keeps its casing outside the axes. Color, alpha, URL, snap,
sketch parameters, and path effects reach the glyphs the same way; `set_gid`
gives the glyphs `gid-0`, `gid-1`, and so on. A rasterized label rasterizes as
one piece, because the parts draw inside the label's own `draw`. Picking tests
the mouse against the box of each placed glyph (`contains`), as matplotlib's
own text tests its box; a click on the casing's band between glyphs is not a
hit. The parts are not artists of the axes, so they take no part in picking,
hover, `ax.texts`, legend placement, or figure layout. The label measures its
glyphs and its casing for them.

Layering is by the label's zorder alone: the casing draws first and the glyphs
after it, inside `CurvedText.draw`, so the text reads on top of its casing and
an artist at any zorder above the label covers both.

Measuring is kept apart from drawing. `_place_on_curve` returns a `_Placement`
(a place for each segment and for the casing) and writes nothing to a segment.
`get_window_extent` and `contains` keep the placement for the renderer they
were given, with the key it was made for, and `draw` places the label afresh
and draws each segment at the place it just made. The segments keep no
placement, so a measurement with a renderer of another resolution, between a
draw and the glyphs' next draw, has none of theirs to change.

## Behavior rules

- `parse_math=False` (kwarg or rcParam) disables splitting entirely.
- A string with an odd count of unescaped `$` renders literally, character by
  character, as matplotlib itself would.
- Under `usetex`, plain text is typeset literally, one run at a time, so TeX
  commands work only inside `$...$` (see the LaTeX section; the page
  [LaTeX typesetting (usetex)](https://thiebes.github.io/curved-text/usetex.html) describes what users see).
- Under `usetex`, the library does not load LaTeX packages itself, because the
  preamble is one global setting (the usetex page gives the reason).
- Fractions, radicals, and large brackets stay joined because the path the
  label rides has a radius of at least 1.5 times the height of its ink on the
  inside of a bend (`min_radius="auto"`). The inside edge is squeezed along the
  curve, to a third of its natural length at that radius. A tighter bend is
  rounded, so the label leaves the curve instead of folding.

## Test pins

Each bullet states an invariant that tests pin and names one or two of them in
`tests/test_core.py`.

- A math run on a straight horizontal curve reduces to a plain affine map. This
  pins datum, width, scale, and resolution handling at once:
  `test_math_run_straight_line_reduces_to_affine`.
- Bending happens: a math label spanning a wide circular arc keeps every vertex
  near the arc, which a chord placement would violate:
  `test_math_run_follows_tight_arc`.
- Plain and math share one baseline, with no per-glyph step, under mathtext and
  usetex: `test_plain_glyphs_share_one_baseline_on_a_slope`,
  `test_math_run_aligns_to_plain_baseline`.
- A superscript extends a math run upward without moving its body:
  `test_superscript_does_not_drop_math_body`.
- `valign` shifts the whole label by one font-metric constant, from the font the
  label names without usetex and from the drawn TeX font with it, and the
  casing centers on the ink:
  `test_valign_shifts_label_perpendicular_uniformly`,
  `test_usetex_valign_follows_the_drawn_font`,
  `test_usetex_box_centres_on_the_ink_under_every_valign`.
- The usetex outline is laid out at the size it is measured at:
  `test_usetex_outline_matches_measured_design_at_any_size`.
- Kerning is the kern that matplotlib's layout (or TeX) applies to the pair, and
  zero where no kern applies:
  `test_plain_glyphs_are_kerned_as_matplotlib_lays_out_text`,
  `test_kern_is_zero_where_no_plain_pair_is_kerned`,
  `test_usetex_plain_glyphs_are_kerned_as_tex_sets_them`.
- A plain run is typeset in one LaTeX pass with one item per character, and a
  run that cannot be paired falls back to one character at a time:
  `test_usetex_plain_run_is_typeset_in_one_latex_pass`,
  `test_usetex_run_that_cannot_be_paired_is_typeset_per_character`.
- Cached runs follow a change of the preamble inputs:
  `test_usetex_run_follows_the_font_when_rcparams_change`.
- Figure layout sees the label without a stretched bounding box, and a legend
  measures it without placing it again:
  `test_unclipped_label_keeps_the_tight_bounding_box`,
  `test_constrained_layout_makes_room_for_an_unclipped_label`,
  `test_legend_measures_the_label_without_placing_it_again`.
- A label draws on axes with no data origin (logit, masked log, polar with a
  radial limit above zero): `test_label_draws_on_scales_without_a_data_origin`,
  `test_label_draws_on_polar_axes_whose_radius_starts_above_zero`.
- A label follows only the stretch that holds its anchor, overruns along the
  end tangent, and ends on the earlier stretch at a boundary:
  `test_label_on_a_gapped_curve_rides_the_stretch_holding_its_anchor`,
  `test_label_overrunning_its_stretch_follows_its_tangent_across_the_gap`,
  `test_label_ending_at_a_boundary_ends_on_the_earlier_stretch`.
- Values outside a log or logit axis's domain leave the gap a NaN does:
  `test_values_outside_a_log_axis_domain_leave_a_gap`,
  `test_values_outside_a_logit_axis_domain_leave_a_gap`.
- A unit-typed curve places the label as the same curve in floats does, and a
  change of units moves it once: `test_unit_typed_curve_matches_float_curve`,
  `test_label_follows_a_change_of_axis_units`,
  `test_label_converts_its_curve_once_until_the_units_change`.
- An upright label on reversed arrays draws the same outline as the forward
  label, and keeps its interval of the curve under every anchor:
  `test_upright_label_on_reversed_arrays_matches_the_forward_label`,
  `test_upright_keeps_the_interval_of_the_curve`.
- The turn is decided by the chord across the label, not by the tangent at the
  anchor, and again on every draw, so an inverted axis is followed:
  `test_upright_decides_by_the_chord_across_the_label_not_the_anchor_tangent`,
  `test_upright_follows_an_inverted_axis_and_back`.

- The label is one artist. `ax.draw_artist(label)` draws the glyphs and the
  casing, an animated label leaves no casing in the background of a blit, the
  axes lists only the label, the label has one zorder, and the casing draws
  under the glyphs:
  `test_draw_artist_draws_the_glyphs_and_the_casing`,
  `test_animated_casing_does_not_stay_in_the_background`,
  `test_the_axes_holds_only_the_label_not_its_parts`,
  `test_the_label_draws_its_casing_and_glyphs_at_one_zorder`,
  `test_box_is_drawn_before_the_glyphs`.
- The label's properties reach what is drawn after construction, for the
  glyphs and the casing alike: `test_a_setter_called_after_construction_changes_what_is_drawn`,
  `test_the_glyphs_follow_the_label_clipping`,
  `test_a_clip_box_and_a_clip_path_set_after_construction_cut_the_label`,
  `test_gid_and_url_set_after_construction_reach_the_svg`,
  `test_the_url_reaches_every_glyph_and_the_casing`,
  `test_snap_set_after_construction_changes_the_glyphs`,
  `test_snap_set_after_construction_changes_the_casing`,
  `test_sketch_params_set_after_construction_change_the_glyphs`,
  `test_sketch_params_set_after_construction_change_the_casing`,
  `test_path_effects_set_after_construction_reach_the_glyphs`.
- A label made hidden is sized as any label once shown, a rasterized label
  raises no warning, and a label's filter runs once:
  `test_a_label_made_hidden_is_sized_as_any_label_once_shown`,
  `test_rasterized_set_off_after_construction_stops_rasterizing`,
  `test_an_agg_filter_runs_once_for_the_label_however_it_is_set`.
- A measurement with another renderer leaves what is drawn alone:
  `test_measuring_with_another_renderer_leaves_what_is_drawn_alone`.
- The casing takes the label's clipping, URL, snap, and sketch parameters but no
  path effect, and a math run is drawn and removed with its label:
  `test_the_casing_takes_no_path_effect`,
  `test_a_math_run_is_drawn_and_removed_with_its_label`,
  `test_animated_set_after_construction_hides_the_label_from_a_full_draw`.

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
  many short new labels starts LaTeX once rather than once per label.

## Ecosystem constraints

curved-text is listed in matplotlib's third-party package registry
(mpl-third-party). The implementation therefore uses public matplotlib API
only, verifies the declared matplotlib floor in CI, and adds a non-blocking CI
job against matplotlib pre-releases so upstream breakage surfaces here before
users meet it.
