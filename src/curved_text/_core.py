"""Draw text along an arbitrary curve in a matplotlib Axes."""
# Developed with AI assistance under maintainer review; see the
# "Development and AI use" section of the README.
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, NamedTuple

import matplotlib.artist as martist
import matplotlib.colors as mcolors
import matplotlib.font_manager as font_manager
import matplotlib.lines as mlines
import matplotlib.text as mtext
import numpy as np
from matplotlib.patheffects import PathEffectRenderer
from matplotlib.path import Path
from matplotlib.textpath import TextToPath
from matplotlib.transforms import IdentityTransform

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from numpy.typing import ArrayLike

__all__ = ["CurvedText", "curved_text"]

_ANCHORS = ("start", "center", "end")
_VALIGN = ("baseline", "center", "ascender", "descender")
_BOX_KEYS = ("color", "pad", "alpha")
_CROWDING = ("none", "curvature")

# Crowding slack and cap for the ``"curvature"`` mode, both as fractions of the
# concave-edge shortening relative to the line height. ``_CROWD_SLACK`` is a
# deadband: the sidebearing whitespace already built into adjacent glyphs
# absorbs this much curvature before their ink visibly collides, so no gap is
# added below it and a gentle bend is left untouched. ``_MAX_CROWD`` caps the
# correction so even a very tight bend adds at most a bounded gap.
_CROWD_SLACK = 0.2
_MAX_CROWD = 0.6

# Unescaped mathtext delimiter, mirroring matplotlib's own escape rule.
_MATH_DELIMITER = re.compile(r"(?<!\\)\$")

# Longest straight outline segment, in mathtext layout units (1/100 em), that
# the bend map will not subdivide. Short chords keep bent rule boxes (fraction
# bars, radical overlines) smooth at any curvature where text is readable.
_MAX_SEGMENT_UNITS = 5.0

# Points sampled along the curve to draw the box casing as a polyline. Enough
# to look smooth across a label-width span at any realistic curvature.
_BOX_SAMPLES = 64

# Shared converter from text to glyph outlines; it caches font faces internally.
_text_to_path = TextToPath()


class _Run(NamedTuple):
    is_math: bool
    text: str


def _split_runs(text: str) -> list[_Run]:
    """Split ``text`` into plain runs and ``$...$`` mathtext runs.

    Mirrors matplotlib's parsing rules: a string with an odd number of
    unescaped dollar signs is literal text, and ``\\$`` in plain text renders
    as a dollar sign. Math runs keep their delimiters so they re-parse as
    written; empty plain runs between adjacent math runs are dropped.
    """
    delimiters = [m.start() for m in _MATH_DELIMITER.finditer(text)]
    if len(delimiters) % 2:
        delimiters = []
    runs = []
    cursor = 0
    for opening, closing in zip(delimiters[::2], delimiters[1::2]):
        if opening > cursor:
            runs.append(_Run(False, text[cursor:opening].replace(r"\$", "$")))
        runs.append(_Run(True, text[opening:closing + 1]))
        cursor = closing + 1
    if cursor < len(text) or not runs:
        runs.append(_Run(False, text[cursor:].replace(r"\$", "$")))
    return runs


def _box_config(box: bool | str | dict) -> dict | None:
    """Normalize the ``box`` argument to a settings dict, or None when off.

    ``box`` may be a bool, a color string, or a dict of ``color`` / ``pad`` /
    ``alpha`` overrides. ``pad`` scales the band height relative to the tallest
    glyph. Unknown dict keys raise, so a typo surfaces instead of vanishing.
    """
    if not box:
        return None
    config: dict = {"color": "white", "pad": 1.1, "alpha": None}
    if isinstance(box, str):
        config["color"] = box
    elif isinstance(box, dict):
        unknown = set(box) - set(_BOX_KEYS)
        if unknown:
            raise ValueError(
                f"box keys must be among {_BOX_KEYS}, got {sorted(unknown)}")
        config.update(box)
    return config


def _valign_datum(valign: str, prop) -> float:
    """Height above the baseline, in 1/100-em layout units, that rides the curve
    for the given vertical alignment.

    ``"baseline"`` is the shared default and returns 0, so the text baseline
    follows the curve. The others shift every segment by the same font-metric
    constant -- the curve passes through the vertical centre, the ascender line,
    or the descender line -- so plain glyphs and mathtext stay aligned and no
    per-glyph step is introduced (the shift is identical for every glyph).
    """
    if valign == "baseline":
        return 0.0
    font = font_manager.get_font(font_manager.findfont(prop))
    upm = font.units_per_EM
    ascender = font.ascender / upm * _text_to_path.FONT_SCALE
    descender = font.descender / upm * _text_to_path.FONT_SCALE
    if valign == "ascender":
        return ascender
    if valign == "descender":
        return descender
    return (ascender + descender) / 2.0  # "center"


class _CurveFrame:
    """Display-space curve geometry: cumulative arc length with an elementwise
    point-and-tangent lookup.

    Arc lengths past either end of the curve clip into the terminal segments,
    so lookups there extrapolate along the end tangents and an overrunning
    label rides a straight extension instead of being clipped.
    """

    def __init__(self, xf: np.ndarray, yf: np.ndarray) -> None:
        self._xf = xf
        self._yf = yf
        self._arc = np.insert(
            np.cumsum(np.hypot(np.diff(xf), np.diff(yf))), 0, 0.0)
        self._rads = np.arctan2(np.diff(yf), np.diff(xf))

    @property
    def length(self) -> float:
        return float(self._arc[-1])

    def points_and_angles(self, s):
        """Map arc length ``s`` (scalar or array, pixels) to the position on
        the curve and the local segment-tangent angle, elementwise."""
        i = np.clip(np.searchsorted(self._arc, s) - 1, 0, len(self._arc) - 2)
        d = self._arc[i + 1] - self._arc[i]
        f = np.where(d != 0.0, (s - self._arc[i]) / np.where(d != 0.0, d, 1.0),
                     0.0)
        x = self._xf[i] + f * (self._xf[i + 1] - self._xf[i])
        y = self._yf[i] + f * (self._yf[i + 1] - self._yf[i])
        return x, y, self._rads[i]

    def chord_angles(self, s, span):
        """Angle of the chord across ``[s, s + span]``, elementwise.

        This is the rotation a glyph of advance ``span`` takes: it follows the
        local tangent but averages over the glyph's own width, so it stays
        smooth across the vertices of a coarsely sampled polyline instead of
        snapping to each segment's angle. Degenerate chords (zero ``span`` or a
        zero-length stretch of curve) fall back to the segment tangent.
        """
        xl, yl, rad = self.points_and_angles(s)
        xr, yr, _ = self.points_and_angles(np.asarray(s) + span)
        return np.where((xr == xl) & (yr == yl), rad,
                        np.arctan2(yr - yl, xr - xl))

    def curvature(self, s, span):
        """Signed turning rate (radians per pixel) over ``[s, s + span]``.

        The tangent is sampled as the chord across each half of the span --
        ``[s, s + span/2]`` and ``[s + span/2, s + span]`` -- whose midpoints lie
        ``span/2`` apart. The wrapped angle between those two chords, divided by
        that ``span/2`` separation, estimates the curvature at the glyph's own
        length scale, the same scale :meth:`chord_angles` smooths rotation over;
        on a circle of radius ``R`` it recovers ``1/R``. Positive turns left. A
        straight stretch (or a degenerate ``span``) yields zero, so a straight
        guide is left untouched by any curvature-driven adjustment.
        """
        half = np.asarray(span, dtype=float) / 2.0
        a0 = self.chord_angles(s, half)
        a1 = self.chord_angles(np.asarray(s) + half, half)
        turn = np.arctan2(np.sin(a1 - a0), np.cos(a1 - a0))
        return np.where(half > 0.0, turn / np.where(half > 0.0, half, 1.0), 0.0)

    def offset(self, distance: float) -> _CurveFrame:
        """The parallel (offset) curve at perpendicular ``distance`` pixels.

        Each vertex is displaced along the local normal -- the bisector of its
        two adjacent segment tangents at interior vertices, the single segment
        tangent at the ends -- so the returned frame is the curve the label
        actually rides when offset. Walking glyphs along it (rather than
        projecting them off the base curve) keeps both the perpendicular
        clearance and the on-screen letter spacing uniform, because the cursor
        advances along the very curve the glyphs sit on. Positive ``distance``
        is to the left of the direction of travel; ``distance`` of zero returns
        this frame unchanged, so an un-offset label and a straight guide stay
        numerically identical.
        """
        if distance == 0.0:
            return self
        tx, ty = np.cos(self._rads), np.sin(self._rads)
        vtx = np.empty_like(self._xf)
        vty = np.empty_like(self._yf)
        vtx[0], vty[0] = tx[0], ty[0]
        vtx[-1], vty[-1] = tx[-1], ty[-1]
        # Interior vertices ride the bisector of the adjacent unit tangents; a
        # near-zero sum means the curve doubles back on itself, so fall back to
        # the incoming segment tangent there rather than divide by zero.
        mx, my = tx[:-1] + tx[1:], ty[:-1] + ty[1:]
        mlen = np.hypot(mx, my)
        safe = mlen > 1e-12
        denom = np.where(safe, mlen, 1.0)
        vtx[1:-1] = np.where(safe, mx / denom, tx[:-1])
        vty[1:-1] = np.where(safe, my / denom, ty[:-1])
        return _CurveFrame(self._xf - distance * vty, self._yf + distance * vtx)

    def remap_arc(self, other: _CurveFrame, s):
        """Map arc length ``s`` on this curve to the corresponding arc length on
        ``other``, a curve sharing this one's vertices (its :meth:`offset`).

        The point at fraction ``f`` of this curve's segment ``i`` maps to
        fraction ``f`` of ``other``'s segment ``i``. ``pos`` and ``anchor`` are
        given against the base curve, so this carries the anchor over to the
        offset curve the label is laid along -- the label lands where the user
        asked on the original curve while keeping even spacing on the offset
        one. On a straight guide the two curves have equal-length segments, so
        the map is the identity.
        """
        s = np.asarray(s, dtype=float)
        i = np.clip(np.searchsorted(self._arc, s) - 1, 0, len(self._arc) - 2)
        d = self._arc[i + 1] - self._arc[i]
        f = np.where(d != 0.0, (s - self._arc[i]) / np.where(d != 0.0, d, 1.0),
                     0.0)
        return other._arc[i] + f * (other._arc[i + 1] - other._arc[i])


def _densify(verts: np.ndarray, codes: np.ndarray,
             max_du: float = _MAX_SEGMENT_UNITS) -> tuple[np.ndarray, np.ndarray]:
    """Subdivide straight LINETO segments longer than ``max_du`` along x.

    The bend map displaces vertices but keeps segments straight between them,
    so a long horizontal segment (a fraction bar, a radical overline) would
    cut a chord across the curve. Bezier control points pass through: font
    outline segments are short, and mapping their control points directly is
    the standard path-bending approximation.
    """
    out_verts: list[np.ndarray] = []
    out_codes: list[int] = []
    prev = None
    for vert, code in zip(verts, codes):
        if code == Path.LINETO and prev is not None:
            n_extra = int(abs(vert[0] - prev[0]) // max_du)
            if n_extra:
                fractions = np.linspace(0.0, 1.0, n_extra + 2)[1:, None]
                out_verts.extend(prev + (vert - prev) * fractions)
                out_codes.extend([int(Path.LINETO)] * (n_extra + 1))
                prev = vert
                continue
        out_verts.append(vert)
        out_codes.append(code)
        if code != Path.CLOSEPOLY:
            prev = vert
    return np.asarray(out_verts), np.asarray(out_codes, dtype=Path.code_type)


class _OutlineSegment(mtext.Text):
    """A curved-label segment drawn by mapping a baseline-relative glyph outline
    through the curve frame.

    One segment is either a plain character (:class:`_PlainGlyph`) or a mathtext
    run (:class:`_MathRun`). Both subclass :class:`~matplotlib.text.Text` so the
    parent's cursor walk measures every segment the same way -- by window-extent
    width -- and, crucially, both keep the text baseline as the shared datum
    (``v = 0``), so plain glyphs and mathtext sit on one baseline by construction.

    Placement maps an outline point ``(u, v)`` -- arc length from the segment's
    left edge and height above the baseline, both in 1/100-em layout units -- into
    display pixels. ``v`` is shifted by the vertical-alignment datum
    (:func:`_valign_datum`), so the chosen line (baseline, centre, ascender, or
    descender) is what rides the curve. Because each glyph is placed by an
    isometry, the perpendicular distance from the curve equals ``v`` exactly --
    there is no per-glyph step, and plain and math are identical by construction.

    Subclasses differ only in where the outline comes from
    (:meth:`_outline_units`) and whether it is placed rigidly or bent along the
    curve (:attr:`_bend`). Any perpendicular offset is already baked into the
    frame (it is the parallel curve), so a segment rides it with no offset
    handling of its own.
    """

    #: Whether the outline bends along the curve (math runs) or is placed rigidly
    #: as a single undistorted glyph (plain characters).
    _bend = False

    def __init__(self, text: str, **kwargs: Any) -> None:
        super().__init__(0.0, 0.0, text, **kwargs)
        self._frame: _CurveFrame | None = None
        self._s_left = 0.0
        self._width_px = 0.0
        self._datum = 0.0
        self._outline_cache: tuple | None = None

    def _set_placement(self, frame: _CurveFrame, s_left: float,
                       width_px: float, datum: float) -> None:
        """Receive this draw's frame, the arc length of the segment's left edge on
        it (already the parallel curve when offset), the segment's flat advance
        width in pixels (the chord for a rigid glyph's rotation), and the
        vertical-alignment datum (height in 1/100-em layout units that rides the
        curve), computed once by the container so every segment shares it."""
        self._frame = frame
        self._s_left = float(s_left)
        self._width_px = float(width_px)
        self._datum = float(datum)

    @martist.allow_rasterization
    def draw(self, renderer, *args, **kwargs) -> None:
        if not self.get_visible() or self._frame is None:
            return
        path = self._placed_path(renderer)
        if path is None:
            return
        # Honor path effects (e.g. a white withStroke halo to clear the line
        # behind the label); the effect strokes the placed outline, so the
        # clearing follows the curve.
        path_effects = self.get_path_effects()
        if path_effects:
            renderer = PathEffectRenderer(path_effects, renderer)
        gc = renderer.new_gc()
        try:
            if self.get_clip_on():
                gc.set_clip_rectangle(self.get_clip_box())
                gc.set_clip_path(self.get_clip_path())
            gc.set_linewidth(0.0)
            gc.set_url(self.get_url())
            face = mcolors.to_rgba(self.get_color(), self.get_alpha())
            renderer.open_group("curved_segment", self.get_gid())
            renderer.draw_path(gc, path, IdentityTransform(), face)
            renderer.close_group("curved_segment")
        finally:
            gc.restore()
        self.stale = False

    def _placed_path(self, renderer) -> Path | None:
        """This segment's outline mapped onto the curve, in display pixels."""
        # draw() guards against a missing frame before calling this.
        assert self._frame is not None
        verts, codes = self._outline_units()
        if len(verts) == 0:
            return None
        em_px = renderer.points_to_pixels(self.get_fontsize())
        px_per_unit = em_px / _text_to_path.FONT_SCALE
        u = verts[:, 0] * px_per_unit
        v = (verts[:, 1] - self._datum) * px_per_unit
        if self._bend:
            # Bend each outline point through the frame: arc length advances with
            # ``u`` and the normal follows the local em-scale chord, so radicals
            # and fraction bars stay connected through curvature. Long straight
            # runs are pre-subdivided by ``_densify`` so they follow the curve.
            s = self._s_left + u
            x, y, _ = self._frame.points_and_angles(s)
            angle = self._frame.chord_angles(s - em_px / 2.0, em_px)
            placed = np.column_stack([x - v * np.sin(angle),
                                      y + v * np.cos(angle)])
        else:
            # Place the glyph rigidly: one rotation, by the chord across its own
            # advance, about its centre on the curve. A single isometry preserves
            # the glyph's shape (no distortion) while the baseline datum still
            # lands on the curve, so spacing and rotation match the bent runs.
            w = self._width_px
            cx, cy, _ = self._frame.points_and_angles(self._s_left + w / 2.0)
            angle = float(self._frame.chord_angles(self._s_left, w))
            cos, sin = np.cos(angle), np.sin(angle)
            u_centred = u - w / 2.0
            placed = np.column_stack([cx + u_centred * cos - v * sin,
                                      cy + u_centred * sin + v * cos])
        return Path(placed, codes)

    def _outline_units(self) -> tuple[np.ndarray, np.ndarray]:
        """Outline ``(vertices, codes)`` in 1/100-em layout units, baseline at
        ``v = 0`` and left edge at ``u = 0``. Implemented by subclasses."""
        raise NotImplementedError


class _PlainGlyph(_OutlineSegment):
    """One plain character, drawn as a rigid (undistorted) glyph outline whose
    baseline rides the curve."""

    _bend = False

    def _outline_units(self) -> tuple[np.ndarray, np.ndarray]:
        prop = self.get_fontproperties()
        key = (self.get_text(), hash(prop))
        if self._outline_cache is not None and self._outline_cache[0] == key:
            return self._outline_cache[1]
        text = self.get_text()
        if text in (" ", ""):  # whitespace advances the cursor but draws nothing
            outline = (np.empty((0, 2)), np.empty(0, dtype=Path.code_type))
        else:
            verts, codes = _text_to_path.get_text_path(prop, text, ismath=False)
            outline = (np.asarray(verts, float),
                       np.asarray(codes, dtype=Path.code_type))
        self._outline_cache = (key, outline)
        return outline


class _MathRun(_OutlineSegment):
    """One mathtext run, drawn by bending the expression's glyph outlines and rule
    boxes through the curve so radicals, fractions, and sized delimiters stay
    connected at any curvature. Its baseline is the same shared datum as the plain
    glyphs, so the run's main symbols sit level with neighbouring characters."""

    _bend = True

    def _outline_units(self) -> tuple[np.ndarray, np.ndarray]:
        prop = self.get_fontproperties()
        key = (self.get_text(), hash(prop))
        if self._outline_cache is not None and self._outline_cache[0] == key:
            return self._outline_cache[1]
        glyph_info, glyph_map, rects = _text_to_path.get_glyphs_mathtext(
            prop, self.get_text())
        pieces = []
        for glyph_id, x_pen, y_pen, scale in glyph_info:
            outline_verts, outline_codes = glyph_map[glyph_id]
            if len(outline_verts) == 0:  # whitespace glyphs have no outline
                continue
            placed = np.asarray(outline_verts, float) * scale + [x_pen, y_pen]
            pieces.append(_densify(placed, np.asarray(outline_codes)))
        for rect_verts, rect_codes in rects:
            pieces.append(_densify(np.asarray(rect_verts, float),
                                   np.asarray(rect_codes)))
        if pieces:
            verts = np.concatenate([p[0] for p in pieces])
            codes = np.concatenate([p[1] for p in pieces])
        else:
            verts = np.empty((0, 2))
            codes = np.empty(0, dtype=Path.code_type)
        outline = (verts, codes)
        self._outline_cache = (key, outline)
        return outline


class CurvedText(mtext.Text):
    """A string drawn along an (x, y) curve, one character at a time.

    Every glyph -- plain character or mathtext run -- is laid out on one shared
    text baseline and mapped onto the curve from its glyph outline: a plain
    character rigidly (one rotation by the chord across its own advance, so its
    shape is undistorted), a mathtext run by bending its outlines so radicals and
    fractions stay connected. ``valign`` chooses which line of the text rides the
    curve -- the vertical centre by default. Because both kinds share the baseline,
    plain and math sit level by construction, and because each glyph is placed by
    an isometry there is no per-glyph drift. The rotation chord follows the local
    tangent but averages over the glyph's own width, so rotation stays smooth
    across the vertices of a coarsely sampled polyline instead of snapping to each
    segment's angle. The layout is recomputed on every draw, so the label keeps
    following the curve through figure layout, resizing, and interactive panning
    or zooming.

    Placement controls:

    ``pos``
        Where the label is anchored along the curve, as a fraction of the curve's
        arc length: ``0.0`` is the first point, ``1.0`` is the last.
    ``anchor``
        Which part of the label lands at ``pos``: ``"start"``, ``"center"``, or
        ``"end"``.
    ``offset``
        A perpendicular shift off the curve, in typographic points. The label is
        laid along the parallel (offset) curve at that distance, so the clearance
        from the curve is uniform along the whole label and the letter spacing
        stays even, even where the curvature is steep or asymmetric. Positive is
        to the left of the direction of travel, which is visually above a
        left-to-right curve. ``pos`` and ``anchor`` stay measured against the
        original curve and are carried perpendicularly onto the offset curve, so
        an offset label sits directly off the spot the same ``pos`` marks on the
        bare curve.
    ``valign``
        Which line of the text rides the curve: ``"center"`` (the default -- the
        text straddles the curve), ``"baseline"`` (the baseline follows the curve,
        so the body sits above it with descenders below), ``"ascender"``, or
        ``"descender"``. The choice is a single font-metric shift applied
        identically to every glyph and to the mathtext runs, so it never
        introduces a per-glyph step and keeps plain and math aligned. Combine with
        ``offset`` to lift the chosen line off the curve.

    A label that overruns either end of the curve -- because of ``pos`` and
    ``anchor`` -- is not clipped. The curve is extended along its end tangent and
    the overrunning glyphs are placed on that straight extension.

    Set ``box`` to draw a casing behind the label -- a band that follows the
    curve at the label's height, drawn under the glyphs -- so the label stays
    legible where it crosses the lines it labels. For a lighter, glyph-hugging
    casing instead, pass a white ``withStroke`` through ``path_effects``; a wide
    stroke there merges adjacent per-character glyphs, so ``box`` is the way to
    get solid coverage under plain text.

    Mathtext is supported: each ``$...$`` run in ``text`` is laid out by
    matplotlib's mathtext engine and bent continuously along the curve --
    every glyph outline and rule box is mapped through the curve's arc-length
    frame, so radicals, fractions, and sized delimiters stay connected at any
    curvature. The run rides the same baseline as the surrounding plain glyphs, so
    its main symbols sit level with them. Pass ``parse_math=False`` to treat
    dollar signs literally. ``text.usetex`` is not supported. Tall expressions
    compress vertically on the inside of tight bends, so choose label size
    relative to curvature accordingly.

    Both plain glyphs and mathtext runs are rendered from their glyph outlines
    rather than as hinted ``Text`` artists. On a rotated label this is what lets a
    single baseline be pinned exactly; the only cost is the loss of pixel-grid
    hinting, which is marginal on rotated text and matches how mathtext has always
    rendered.

    Parameters
    ----------
    x, y : array-like
        The curve in data coordinates: 1-D, equal length, at least two points,
        finite, and ordered along the curve.
    text : str
        The string to draw. May contain mathtext runs (``$...$``).
    axes : matplotlib.axes.Axes
        The axes to draw into.
    pos : float, default 0.5
        Arc-length fraction in ``[0, 1]`` for the anchor point.
    anchor : {"start", "center", "end"}, default "center"
        Which part of the label sits at ``pos``.
    offset : float, default 0.0
        Perpendicular offset off the curve, in points. The label is laid along
        the parallel (offset) curve at that distance.
    box : bool, str, or dict, default False
        A casing drawn behind the label to clear the lines it crosses. ``True``
        draws a white band; a color string sets its color; a dict accepts
        ``color``, ``pad`` (band height relative to the tallest glyph, default
        ``1.1``), and ``alpha``. The band has rounded ends, so it extends about
        half its height past the first and last glyph.
    crowding : {"none", "curvature"}, default "none"
        How to space glyphs around bends. ``"none"`` advances each glyph by its
        own width, so on the concave side of a tight bend the rotated glyph
        boxes can overlap. ``"curvature"`` opens an even letterspacing gap that
        grows with the local curvature and the glyph height, so the inside edges
        stop colliding; the gap is the same between every pair of letters, and a
        deadband leaves gentle bends and straight runs unchanged.
    valign : {"center", "baseline", "ascender", "descender"}, default "center"
        Which line of the text rides the curve. ``"center"`` straddles the text on
        the curve (the default); ``"baseline"`` follows the text baseline so the
        body sits above the curve; the others ride the ascender or descender line.
        Each is a constant font-metric shift applied to the whole label.
    **kwargs
        Passed to each per-character glyph and each mathtext run (for example
        ``color``, ``fontsize``, ``alpha``, ``fontfamily``).
    """

    def __init__(self, x: ArrayLike, y: ArrayLike, text: str, axes: Axes, *,
                 pos: float = 0.5, anchor: str = "center", offset: float = 0.0,
                 box: bool | str | dict = False, crowding: str = "none",
                 valign: str = "center", **kwargs: Any) -> None:
        if anchor not in _ANCHORS:
            raise ValueError(f"anchor must be one of {_ANCHORS}, got {anchor!r}")
        if crowding not in _CROWDING:
            raise ValueError(
                f"crowding must be one of {_CROWDING}, got {crowding!r}")
        if valign not in _VALIGN:
            raise ValueError(f"valign must be one of {_VALIGN}, got {valign!r}")
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if x.ndim != 1 or x.shape != y.shape or x.size < 2:
            raise ValueError("x and y must be 1-D arrays of equal length >= 2")
        if not (np.isfinite(x).all() and np.isfinite(y).all()):
            raise ValueError("x and y must contain only finite values")
        super().__init__(float(x[0]), float(y[0]), " ", **kwargs)
        self._cx = x
        self._cy = y
        self._pos = float(pos)
        self._anchor = anchor
        self._offset = float(offset)
        self._crowding = crowding
        self._valign = valign
        axes.add_artist(self)
        # Optional casing behind the label: a fat line following the curve at
        # the label's height. Its geometry is set in ``draw`` (on the container),
        # so it must draw after the container and before the glyphs; ``set_zorder``
        # below places it between them.
        box_config = _box_config(box)
        self._box_pad = 1.1
        self._box: mlines.Line2D | None = None
        if box_config is not None:
            self._box_pad = box_config["pad"]
            self._box = mlines.Line2D([], [], color=box_config["color"],
                                      alpha=box_config["alpha"],
                                      solid_capstyle="round",
                                      solid_joinstyle="round")
            axes.add_line(self._box)
        self._segments: list[_OutlineSegment] = []
        runs = (_split_runs(text) if self.get_parse_math()
                else [_Run(False, text)])
        for run in runs:
            if run.is_math:
                segment = _MathRun(run.text, **kwargs)
                axes.add_artist(segment)
                self._segments.append(segment)
                continue
            for ch in run.text:
                glyph = _PlainGlyph(ch, **kwargs)
                axes.add_artist(glyph)
                self._segments.append(glyph)
        # Apply the layered zorders now that the casing and glyphs exist: the
        # container draws first (it positions them), then the casing, then the
        # glyphs on top.
        self.set_zorder(self.get_zorder())

    def set_zorder(self, zorder) -> None:
        # Glyphs sit one level above the container; the casing sits between, so
        # it clears the data lines but stays under the glyphs. ``super().__init__``
        # may set the zorder before these attributes exist, so guard against
        # running during base-class construction.
        super().set_zorder(zorder)
        box = getattr(self, "_box", None)
        if box is not None:
            box.set_zorder(self.get_zorder() + 0.5)
        for t in getattr(self, "_segments", ()):
            t.set_zorder(self.get_zorder() + 1)

    def _hide_box(self) -> None:
        # The casing is an axes-owned artist drawn independently, so when ``draw``
        # bails out before positioning it the band must be hidden explicitly or
        # the previous draw's geometry stays painted.
        if self._box is not None:
            self._box.set_visible(False)

    def remove(self) -> None:
        # The glyphs and casing are independent artists on the axes; remove them
        # with the container so removal does not leave them behind as orphans.
        for t in self._segments:
            t.remove()
        self._segments = []
        if self._box is not None:
            self._box.remove()
            self._box = None
        super().remove()

    def _advances(self, frame: _CurveFrame, widths: list[float],
                  heights: list[float], flat_start: float) -> list[float]:
        """Arc-length advance for each segment along ``frame``.

        In the default ``"none"`` mode the advance is the flat glyph width, so
        the layout is unchanged. In ``"curvature"`` mode each advance is widened
        where the curve bends, to keep the concave edges of adjacent rigid glyph
        boxes from overlapping on the inside of the bend. A box of height ``h``
        whose center rides a curve of local curvature ``kappa`` has its concave
        edge, a distance ``h/2`` toward the center of curvature, lose roughly
        ``(h/2)*|kappa|`` of arc length per unit advance to its neighbor; the
        ``crowd`` factor below is that fraction, clamped at ``_MAX_CROWD``.

        Only the crowding past ``_CROWD_SLACK`` is corrected: a gentle bend eats
        into the sidebearing whitespace already between the letters without
        their ink colliding, so the gap stays zero there and the layout barely
        changes until the letters are genuinely crowded. The clearance is then
        added as a width-independent letterspacing gap, ``(crowd - slack) * h``
        (scaled by the line height, a typographic constant), not as a multiple
        of the glyph's own width: multiplying by the width would give wide
        glyphs a proportionally larger trailing gap, which reads as uneven
        tracking on an arc, whereas a constant gap keeps the spacing even where
        the curvature is uniform. The center sits in the middle of its widened
        slot, so the gap is split evenly before and after each glyph. The
        curvature is sampled along the un-widened layout starting at
        ``flat_start``.
        """
        if self._crowding == "none":
            return list(widths)
        advances = []
        cursor = flat_start
        for w, h in zip(widths, heights):
            kappa = float(frame.curvature(cursor, w))
            crowd = min(abs(kappa) * h / 2.0, _MAX_CROWD)
            advances.append(w + max(0.0, crowd - _CROWD_SLACK) * h)
            cursor += w
        return advances

    def draw(self, renderer, *args, **kwargs) -> None:
        if not self._segments or self.axes is None:
            self._hide_box()
            return
        axes = self.axes
        # Work in display pixels: project the curve and build its arc-length
        # frame, then shift that frame perpendicularly to the parallel (offset)
        # curve the label actually rides. Laying glyphs along the offset curve
        # -- rather than projecting them off the base curve -- keeps the
        # clearance from the curve and the on-screen letter spacing uniform at
        # once, because the cursor advances along the curve the glyphs sit on.
        # ``pos``/``anchor`` stay defined against the base curve and are carried
        # onto the offset curve below, so the label lands where the user asked.
        pts = axes.transData.transform(np.column_stack([self._cx, self._cy]))
        offset_px = self._offset * renderer.points_to_pixels(1.0)
        base = _CurveFrame(pts[:, 0], pts[:, 1])
        frame = base.offset(offset_px)
        if not np.isfinite(frame.length) or frame.length <= 0.0:
            # A degenerate curve has no span to position the casing on; hide it
            # rather than leave the previous draw's band stranded on screen.
            self._hide_box()
            return
        inv = axes.transData.inverted()

        # The vertical-alignment datum is a font-metric constant (size
        # independent) and identical for every segment, so derive it once here
        # and hand it to each segment rather than re-deriving it per glyph.
        prop = self.get_fontproperties()
        datum = _valign_datum(self._valign, prop)

        # Measure each segment's unrotated advance width and height. Segments
        # render their own outlines and never set a Text rotation, so the window
        # extent is always the unrotated box.
        extents = [t.get_window_extent(renderer=renderer)
                   for t in self._segments]
        widths = [e.width for e in extents]
        heights = [e.height for e in extents]

        # Anchor at ``pos`` of the base curve, carried onto the offset curve, so
        # the user's placement reads against the curve they passed in. ``lead``
        # is the fraction of the label that sits before the anchor point.
        s0 = float(base.remap_arc(frame, self._pos * base.length))
        lead = {"start": 0.0, "center": 0.5, "end": 1.0}[self._anchor]

        # Per-glyph advances along the offset curve. In ``"curvature"`` mode
        # these are widened on bends (see ``_advances``); the curve is sampled
        # along the un-widened layout, anchored the same way, which is accurate
        # enough since the widening shifts positions only slightly. The label
        # then spans ``total`` pixels from the re-anchored cursor.
        flat_total = float(sum(widths))
        advances = self._advances(frame, widths, heights, s0 - lead * flat_total)
        total = float(sum(advances))
        cursor = s0 - lead * total

        # The casing follows the curve across the label's whole span at the
        # tallest glyph's height, so it clears the lines behind plain and math
        # segments alike (a single fill, immune to the per-character
        # cannibalization a wide ``path_effects`` stroke would cause). The label
        # rides the frame on its ``valign`` datum, so the glyph band is centred a
        # little off the frame; shift the casing centreline by that band offset so
        # it sits over the ink rather than over the bare datum line.
        if self._box is not None:
            ppu = (renderer.points_to_pixels(prop.get_size_in_points())
                   / _text_to_path.FONT_SCALE)
            # The glyph band's ink centre rides the "center" datum; the frame
            # rides the chosen ``valign`` datum, so shift the casing centreline by
            # the gap between the two so it covers the ink, not the bare datum.
            band_px = (_valign_datum("center", prop) - datum) * ppu
            s_box = np.linspace(cursor, cursor + total, _BOX_SAMPLES)
            bx, by, bang = frame.points_and_angles(s_box)
            bx = bx - band_px * np.sin(bang)
            by = by + band_px * np.cos(bang)
            box_xy = inv.transform(np.column_stack([bx, by]))
            height = max(e.height for e in extents)
            self._box.set_data(box_xy[:, 0], box_xy[:, 1])
            self._box.set_linewidth(
                self._box_pad * height / renderer.points_to_pixels(1.0))
            self._box.set_visible(True)

        # ``cursor`` walks the label's left edge along the arc. Each segment maps
        # its baseline-relative outline onto the curve when it draws: a plain
        # glyph rigidly (one rotation by the chord across its own advance, so it
        # stays undistorted), a math run by bending its outlines. Centering each
        # segment's flat width in its (possibly widened) slot lets crowding space
        # plain glyphs and math runs alike, and the shared baseline datum keeps
        # them level.
        for t, w, adv in zip(self._segments, widths, advances):
            t._set_placement(frame, cursor + (adv - w) / 2.0, w, datum)
            t.set_visible(True)
            cursor += adv


def curved_text(ax: Axes, x: ArrayLike, y: ArrayLike, text: str, *,
                pos: float = 0.5, anchor: str = "center", offset: float = 0.0,
                box: bool | str | dict = False, crowding: str = "none",
                valign: str = "center", **kwargs: Any) -> CurvedText:
    """Draw ``text`` along the curve ``(x, y)`` on ``ax`` and return the artist.

    Thin convenience wrapper around :class:`CurvedText`; see it for the meaning of
    ``pos``, ``anchor``, ``offset``, ``box``, ``crowding``, and ``valign``. The
    axes is the first argument here, matching matplotlib's axes-first helper
    functions, whereas :class:`CurvedText` takes it after ``x, y, text`` to match
    :class:`matplotlib.text.Text`.
    """
    return CurvedText(x, y, text, ax, pos=pos, anchor=anchor, offset=offset,
                      box=box, crowding=crowding, valign=valign, **kwargs)
