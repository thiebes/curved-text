"""Draw text along an arbitrary curve in a matplotlib Axes."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, NamedTuple

import matplotlib.artist as martist
import matplotlib.colors as mcolors
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

# Unescaped mathtext delimiter, mirroring matplotlib's own escape rule.
_MATH_DELIMITER = re.compile(r"(?<!\\)\$")

# Longest straight outline segment, in mathtext layout units (1/100 em), that
# the bend map will not subdivide. Short chords keep bent rule boxes (fraction
# bars, radical overlines) smooth at any curvature where text is readable.
_MAX_SEGMENT_UNITS = 5.0

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


def _box_config(box) -> dict | None:
    """Normalize the ``box`` argument to a settings dict, or None when off.

    ``box`` may be a bool, a color string, or a dict of ``color`` / ``pad`` /
    ``alpha`` overrides. ``pad`` scales the band height relative to the tallest
    glyph.
    """
    if not box:
        return None
    config = {"color": "white", "pad": 1.1, "alpha": None}
    if isinstance(box, str):
        config["color"] = box
    elif isinstance(box, dict):
        config.update(box)
    return config


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
                out_codes.extend([Path.LINETO] * (n_extra + 1))
                prev = vert
                continue
        out_verts.append(vert)
        out_codes.append(code)
        if code != Path.CLOSEPOLY:
            prev = vert
    return np.asarray(out_verts), np.asarray(out_codes, dtype=Path.code_type)


class _MathRun(mtext.Text):
    """One mathtext run of a curved label, drawn by bending the expression's
    glyph outlines through the curve frame.

    Inheriting :class:`~matplotlib.text.Text` keeps keyword handling and
    measurement identical to the sibling per-character artists: the parent
    advances its cursor by window-extent width for every segment alike. Only
    rendering differs. At draw time the mathtext layout is mapped through
    ``(u, v) -> curve(u) + (v - datum) * normal(u)``, where ``u`` is arc
    length from the run's left edge and ``v`` is height above the baseline,
    with the datum at the layout box center so the run rides the curve exactly
    where ``va="center"`` would put it. Normals follow em-scale chords,
    matching the chord rotation of plain characters across coarse polyline
    vertices.
    """

    def __init__(self, text: str, **kwargs: Any) -> None:
        super().__init__(0.0, 0.0, text, **kwargs)
        self._frame: _CurveFrame | None = None
        self._s_left = 0.0
        self._offset_px = (0.0, 0.0)
        self._outline_cache: tuple | None = None

    def _set_frame(self, frame: _CurveFrame, s_left: float,
                   offset_px: tuple[float, float]) -> None:
        """Receive this draw's frame: the run starts at arc length ``s_left``
        and shifts by ``offset_px`` along the label's chord normal."""
        self._frame = frame
        self._s_left = float(s_left)
        self._offset_px = offset_px

    @martist.allow_rasterization
    def draw(self, renderer, *args, **kwargs) -> None:
        if not self.get_visible() or self._frame is None:
            return
        path = self._bent_path(renderer)
        if path is None:
            return
        # Honor path effects (e.g. a white withStroke halo to clear the line
        # behind the label) the same way the per-character Text glyphs do; the
        # effect strokes the bent outline, so the clearing follows the curve.
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
            renderer.open_group("mathrun", self.get_gid())
            renderer.draw_path(gc, path, IdentityTransform(), face)
            renderer.close_group("mathrun")
        finally:
            gc.restore()
        self.stale = False

    def _bent_path(self, renderer) -> Path | None:
        """The expression's outline bent along the frame, in display pixels."""
        verts, codes, datum = self._expression_outline()
        if len(verts) == 0:
            return None
        em_px = renderer.points_to_pixels(self.get_fontsize())
        px_per_unit = em_px / _text_to_path.FONT_SCALE
        s = self._s_left + verts[:, 0] * px_per_unit
        v = (verts[:, 1] - datum) * px_per_unit
        x, y, _ = self._frame.points_and_angles(s)
        angle = self._frame.chord_angles(s - em_px / 2.0, em_px)
        ox, oy = self._offset_px
        bent = np.column_stack([x - v * np.sin(angle) + ox,
                                y + v * np.cos(angle) + oy])
        return Path(bent, codes)

    def _expression_outline(self) -> tuple[np.ndarray, np.ndarray, float]:
        """Glyph outlines and rule boxes of the laid-out expression as one
        (vertices, codes) pair in layout units (1/100 em), plus the vertical
        datum above the baseline. Cached until text or font changes."""
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
        # Ride the curve on the surrounding text's x-height line, so the main
        # symbols sit level with neighbouring plain characters. Centering on the
        # run's own box instead would let a superscript or tall delimiter inflate
        # the box and drop the body below the rest of the label.
        size = prop.get_size_in_points()
        _, x_height, _ = _text_to_path.get_text_width_height_descent(
            "x", prop, ismath=False)
        datum = (x_height / 2.0) * _text_to_path.FONT_SCALE / size
        self._outline_cache = (key, (verts, codes, datum))
        return verts, codes, datum


class CurvedText(mtext.Text):
    """A string drawn along an (x, y) curve, one character at a time.

    Each character is an independent :class:`matplotlib.text.Text`, centered
    (``ha="center"``, ``va="center"``) on its own arc-length midpoint, placed in
    display coordinates and rotated to the chord across its own advance -- the
    direction from where the glyph starts on the curve to where it ends. The
    chord follows the local tangent but averages over the glyph's own width, so
    rotation stays smooth across the vertices of a coarsely sampled polyline
    instead of snapping to each segment's angle. The layout
    is recomputed on every draw, so the label keeps following the curve through
    figure layout, resizing, and interactive panning or zooming.

    Placement has three independent controls:

    ``pos``
        Where the label is anchored along the curve, as a fraction of the curve's
        arc length: ``0.0`` is the first point, ``1.0`` is the last.
    ``anchor``
        Which part of the label lands at ``pos``: ``"start"``, ``"center"``, or
        ``"end"``.
    ``offset``
        A perpendicular shift off the curve, in typographic points, along the
        normal of the label's chord (the line from its first to its last glyph).
        Positive is to the left of the direction of travel, which is visually
        above a left-to-right curve.

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
    curvature. Pass ``parse_math=False`` to treat dollar signs literally.
    ``text.usetex`` is not supported. Tall expressions compress vertically on
    the inside of tight bends, so choose label size relative to curvature
    accordingly.

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
        Perpendicular offset off the curve, in points.
    box : bool, str, or dict, default False
        A casing drawn behind the label to clear the lines it crosses. ``True``
        draws a white band; a color string sets its color; a dict accepts
        ``color``, ``pad`` (band height relative to the tallest glyph, default
        ``1.1``), and ``alpha``.
    **kwargs
        Passed to each per-character :class:`~matplotlib.text.Text` and each
        mathtext run (for example ``color``, ``fontsize``, ``alpha``,
        ``fontfamily``).
    """

    def __init__(self, x: ArrayLike, y: ArrayLike, text: str, axes: Axes, *,
                 pos: float = 0.5, anchor: str = "center", offset: float = 0.0,
                 box: bool | str | dict = False, **kwargs: Any) -> None:
        if anchor not in _ANCHORS:
            raise ValueError(f"anchor must be one of {_ANCHORS}, got {anchor!r}")
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
        axes.add_artist(self)
        # Optional casing behind the label: a fat line following the curve at
        # the label's height. Its geometry is set in ``draw`` (on the container),
        # so it must draw after the container and before the glyphs; ``set_zorder``
        # below places it between them.
        box_config = _box_config(box)
        self._box_pad = box_config["pad"] if box_config else 0.0
        self._box: mlines.Line2D | None = None
        if box_config is not None:
            self._box = mlines.Line2D([], [], color=box_config["color"],
                                      alpha=box_config["alpha"],
                                      solid_capstyle="round",
                                      solid_joinstyle="round")
            axes.add_line(self._box)
        self._segments: list[mtext.Text] = []
        runs = (_split_runs(text) if self.get_parse_math()
                else [_Run(False, text)])
        for run in runs:
            if run.is_math:
                segment = _MathRun(run.text, **kwargs)
                axes.add_artist(segment)
                self._segments.append(segment)
                continue
            for ch in run.text:
                t = mtext.Text(0.0, 0.0, " " if ch == " " else ch, **kwargs)
                t.set_ha("center")
                t.set_va("center")
                axes.add_artist(t)
                self._segments.append(t)
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

    def draw(self, renderer, *args, **kwargs) -> None:
        if not self._segments:
            return
        axes = self.axes
        # Work in display pixels: project the curve and build its arc-length
        # frame.
        pts = axes.transData.transform(np.column_stack([self._cx, self._cy]))
        frame = _CurveFrame(pts[:, 0], pts[:, 1])
        if not np.isfinite(frame.length) or frame.length <= 0.0:
            return
        inv = axes.transData.inverted()

        # Reset any rotation left by the previous draw before measuring, so each
        # width is the unrotated advance, not the wider rotated bounding box.
        for t in self._segments:
            t.set_rotation(0)
        extents = [t.get_window_extent(renderer=renderer)
                   for t in self._segments]
        widths = [e.width for e in extents]
        total = float(sum(widths))

        s0 = self._pos * frame.length
        if self._anchor == "center":
            cursor = s0 - total / 2.0
        elif self._anchor == "end":
            cursor = s0 - total
        else:
            cursor = s0

        # Offset the whole label along the normal of its chord (first to last
        # glyph); the frame extrapolates past the curve ends along their tangents.
        x0, y0, _ = frame.points_and_angles(cursor)
        x1, y1, _ = frame.points_and_angles(cursor + total)
        dx, dy = x1 - x0, y1 - y0
        norm = float(np.hypot(dx, dy))
        nx, ny = (-dy / norm, dx / norm) if norm else (0.0, 1.0)
        scale = self._offset * renderer.points_to_pixels(1.0)
        ox, oy = nx * scale, ny * scale

        # The casing follows the offset curve across the label's whole span at
        # the tallest glyph's height, so it clears the lines behind plain and
        # math segments alike (a single fill, immune to the per-character
        # cannibalization a wide ``path_effects`` stroke would cause).
        if self._box is not None:
            s_box = np.linspace(cursor, cursor + total, 64)
            bx, by, _ = frame.points_and_angles(s_box)
            box_xy = inv.transform(np.column_stack([bx + ox, by + oy]))
            height = max(e.height for e in extents)
            self._box.set_data(box_xy[:, 0], box_xy[:, 1])
            self._box.set_linewidth(
                self._box_pad * height / renderer.points_to_pixels(1.0))
            self._box.set_visible(True)

        # ``cursor`` walks the label's left edge along the arc. Each character
        # is centered on its own midpoint and rotated to the chord across its
        # own advance, which smooths the segment-wise tangent of a coarse
        # polyline at exactly the glyph's own length scale; a math run instead
        # receives the frame and bends its outlines through it when it draws.
        for t, w in zip(self._segments, widths):
            if isinstance(t, _MathRun):
                t._set_frame(frame, cursor, (ox, oy))
            else:
                px, py, _ = frame.points_and_angles(cursor + w / 2.0)
                rot = frame.chord_angles(cursor, w)
                t.set_position(inv.transform((px + ox, py + oy)))
                t.set_rotation(np.degrees(rot))
            t.set_visible(True)
            cursor += w


def curved_text(ax: Axes, x: ArrayLike, y: ArrayLike, text: str, *,
                pos: float = 0.5, anchor: str = "center", offset: float = 0.0,
                box: bool | str | dict = False, **kwargs: Any) -> CurvedText:
    """Draw ``text`` along the curve ``(x, y)`` on ``ax`` and return the artist.

    Thin convenience wrapper around :class:`CurvedText`; see it for the meaning of
    ``pos``, ``anchor``, ``offset``, and ``box``. The axes is the first argument
    here, matching matplotlib's axes-first helper functions, whereas
    :class:`CurvedText` takes it after ``x, y, text`` to match
    :class:`matplotlib.text.Text`.
    """
    return CurvedText(x, y, text, ax, pos=pos, anchor=anchor, offset=offset,
                      box=box, **kwargs)
