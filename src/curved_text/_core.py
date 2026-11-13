"""Draw text along an arbitrary curve in a matplotlib Axes."""
# Developed with AI assistance under maintainer review; see the
# "Development and AI use" section of the README.
from __future__ import annotations

import copy
import functools
import inspect
import itertools
import math
import numbers
import re
import unicodedata
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

import matplotlib as mpl
import matplotlib.artist as martist
import matplotlib.colors as mcolors
import matplotlib.dviread as dviread
import matplotlib.font_manager as font_manager
import matplotlib.lines as mlines
import matplotlib.text as mtext
import numpy as np
from matplotlib.backends.backend_agg import RendererAgg
from matplotlib.patheffects import PathEffectRenderer
from matplotlib.path import Path
from matplotlib.texmanager import TexManager
from matplotlib.textpath import TextToPath
from matplotlib.transforms import Bbox, IdentityTransform

if TYPE_CHECKING:
    from collections.abc import Sequence

    from matplotlib.axes import Axes
    from matplotlib.cbook import CallbackRegistry
    from numpy.typing import ArrayLike

__all__ = ["CurvedText", "curved_text"]

_ANCHORS = ("start", "center", "end")
_VALIGN = ("baseline", "center", "ascender", "descender")
_BOX_KEYS = ("color", "pad", "alpha")
# Keywords the label keeps to itself and does not forward to its segments
# (see ``CurvedText.__init__``).
_LABEL_ONLY_KEYWORDS = frozenset({"visible", "rasterized"})
_CROWDING = ("none", "curvature")

# Crowding slack and cap for the ``"curvature"`` mode, both as fractions of the
# concave-edge shortening relative to the line height. ``_CROWD_SLACK`` is a
# deadband: the sidebearing whitespace already built into adjacent glyphs
# absorbs this much curvature before their ink visibly collides, so no gap is
# added below it and a gentle bend is left untouched. ``_MAX_CROWD`` caps the
# correction so even a very tight bend adds at most a bounded gap.
_CROWD_SLACK = 0.2
_MAX_CROWD = 0.6

# Rounding of the path a label rides (``min_radius``). A bend tighter than the
# label's ink on the inside of the bend folds the ink, so the path is rounded to
# a minimum radius: ``_MIN_RADIUS_CLEARANCE`` times the ink extent on that side
# for ``"auto"``.
#
# Gate: the rounding is skipped where the chord-scale curvature times the radius
# stays below ``_ROUND_GATE``. The curvature is probed every ``_ROUND_PROBE``
# ball radii.
#
# Ball test: the rounding works on a copy of the curve resampled every
# ``_ROUND_STEP`` ball radii (at least ``_ROUND_MIN_STEP_PX``, which bounds the
# number of samples), and tests each point against the curve within
# ``_ROUND_REACH`` ball radii of arc length with a slack of ``_ROUND_TOL_PX``
# (so a straight stretch is not flagged by round-off). A radius below
# ``_ROUND_TOL_PX`` cannot be told from round-off, and one above
# ``_ROUND_MAX_RADIUS_PX`` is as good as straight.
#
# Sampled part: its grid sits on whole steps of arc length, so a small move of
# the label does not move the vertices. A bend that comes within reach of an
# end of the part doubles the margin and samples again, at most
# ``_ROUND_MAX_DOUBLINGS`` times, so the rounding beside the label does not
# depend on where the part ends.
#
# Blend: where the balls either side of a run of points are more than
# ``_ROUND_BLEND_STEPS`` steps or ``_ROUND_BLEND_RADIUS`` radii apart, no single
# ball fits, and the run is blended instead of laid on an arc.
_MIN_RADIUS_CLEARANCE = 1.5
_ROUND_STEP = 1 / 16
_ROUND_MIN_STEP_PX = 0.25
_ROUND_REACH = 2 * math.pi
_ROUND_TOL_PX = 0.25
_ROUND_GATE = 0.5
_ROUND_PROBE = 0.5
_ROUND_MAX_DOUBLINGS = 3
_ROUND_MAX_RADIUS_PX = 1e7
_ROUND_BLEND_STEPS = 2.0
_ROUND_BLEND_RADIUS = 0.05

# Smoothing of the path a label rides (``smooth``). A line of measured data has
# wiggles at the width of a glyph, which tilt and step neighboring glyphs, so the
# path is smoothed by a Gaussian along its arc length, in display pixels,
# corrected for the shrinking of bends that a Gaussian alone causes (twice the
# smoothed path less the smoothed path smoothed again, which leaves the shape of
# a smooth bend alone to second order).
#
# The filter. ``"auto"`` takes ``_SMOOTH_AUTO_EM`` of the font size as the
# Gaussian's standard deviation (sigma). Only the part of the stretch the label
# covers, with a margin of ``_SMOOTH_MARGIN`` sigmas or twice the label either
# side, is smoothed, for the rounding and the offset to reach. It is resampled
# every ``_SMOOTH_STEP`` sigmas (at least ``_SMOOTH_MIN_STEP_PX`` pixels, and at
# most ``_SMOOTH_MAX_SAMPLES`` samples over the part), and the kernel reaches
# ``_SMOOTH_REACH`` sigmas, in at most ``_SMOOTH_MAX_REACH`` samples. A sigma
# below ``_SMOOTH_MIN_PX`` pixels is not smoothing.
_SMOOTH_AUTO_EM = 0.75         # ems of font size
_SMOOTH_MARGIN = 24.0          # sigmas
_SMOOTH_STEP = 1 / 8           # sigmas
_SMOOTH_MIN_STEP_PX = 0.25     # pixels
_SMOOTH_MAX_SAMPLES = 20000    # samples
_SMOOTH_REACH = 4.0            # sigmas
_SMOOTH_MAX_REACH = 256        # samples
_SMOOTH_MIN_PX = 0.5           # pixels

# The gate. ``"auto"`` smooths only where the path wiggles under the label, so a
# label on a curve with fewer than ``_SMOOTH_REVERSALS`` wiggles, a bend however
# tight included, is drawn exactly as without smoothing; a width given in points
# always smooths. A path wiggles where the direction of its chords, laid end to
# end across the label, each ``_SMOOTH_CHORD`` sigmas long (half an em for
# ``"auto"``), turns one way and then the other, counting only turns of
# ``_SMOOTH_DEADBAND`` or more. A bend turns the chords one way all through it,
# and a wiggle is a turn back. The test is a heuristic, tuned on real monthly
# prices and the gallery's curves.
_SMOOTH_CHORD = 2 / 3          # sigmas
_SMOOTH_DEADBAND = math.radians(2.0)
_SMOOTH_REVERSALS = 2          # turns back

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

# matplotlib 3.11 lays text out through HarfBuzz, which also shapes it, and its
# layout takes OpenType features; earlier versions only kern.
_LAYOUT_TAKES_FEATURES = "features" in inspect.signature(
    TextToPath.get_glyphs_with_font).parameters

# Kerns cached per font and character pair. A label's pairs recur on every draw
# and across labels, but the pairs a session can meet are unbounded.
_KERN_CACHE_SIZE = 4096

# Bidirectional classes of right-to-left characters. Curved labels draw
# characters in logical order, so a kern would land on the wrong pair.
_RTL_CLASSES = ("R", "AL")

# TeX source for a plain character under usetex. A plain glyph is one literal
# character, so characters TeX reads as markup are escaped, and characters the
# default OT1 encoding typesets as a different glyph ("<" as an inverted "!")
# are spelled out by name.
_CHAR_TO_TEX = {
    "#": r"\#", "$": r"\$", "%": r"\%", "&": r"\&", "_": r"\_",
    "{": r"\{", "}": r"\}", "\\": r"\textbackslash{}",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    "<": r"\textless{}", ">": r"\textgreater{}", "|": r"\textbar{}",
}

# A 1sp (1/65536 pt) rule. matplotlib's DVI reader sizes its output from the
# glyphs and rules TeX sets, and glue alone sets neither, so a rule at each end
# of a space or a run makes the reader measure the space there.
_TEX_EDGE = r"\rule{1sp}{1sp}"

# TeX source for a whitespace character typeset on its own: an interword space
# between two edge rules. A bare space would advance zero. TeX itself reads a
# tab as a space.
_TEX_SPACE = _TEX_EDGE + r"\ " + _TEX_EDGE

# Character pairs TeX fonts join into one glyph: the f ligatures, dashes from
# hyphens, curly quotes from "``" and "''", inverted marks from "!`" and "?`",
# and in T1 fonts the guillemets and a low quote. An empty group between the two
# keeps one glyph per character, as each plain character is its own segment.
_TEX_LIGATURES = frozenset(
    {"ff", "fi", "fl", "--", "``", "''", "!`", "?`", ",,", "<<", ">>"})

# Unicode categories of printing characters that may not set exactly one item
# of their own in a TeX run, so a run cannot pair its items with them by count:
# control and format characters can set nothing (a soft hyphen prints nothing),
# and combining marks join the character before. A run with one is typeset one
# character at a time. Whitespace, some of it control characters such as a tab,
# is a control space in a run and sets no item, so it is not counted.
_TEX_UNPAIRED_CATEGORIES = frozenset({"Cc", "Cf", "Mn", "Me"})

# Usetex plain runs whose layout is kept. Every draw reads each run of every
# label, and a run missing from the cache is read back from its DVI file, so the
# cache holds the runs of a large figure; each holds its glyph outlines.
_TEX_RUN_CACHE_SIZE = 1024

# TeX source matplotlib measures every usetex text against: its box is the least
# height and depth matplotlib gives a line of usetex text.
_TEX_MIN_LINE_PROBE = "lp"

# TeX source whose height and depth stand for the ascender and descender lines
# under usetex. Parentheses reach the ascender line, and "g" and "y" reach the
# descender line where the parentheses stop short of it, as in typewriter fonts
# and Times. TeX sizes the box from the font's own metrics, so the lines follow
# whichever font the preamble, family, and size select, at the scale LaTeX
# draws it.
_TEX_LINE_PROBE = "()gy"


class _Run(NamedTuple):
    is_math: bool
    text: str


class _TexRunLayout(NamedTuple):
    """A usetex plain run typeset by one LaTeX pass, per character, in 1/100-em
    layout units.

    ``outlines`` holds each character's outline with its left edge at ``u = 0``
    (empty for whitespace). ``widths`` holds each character's own width, the
    chord its glyph is rotated by; a space's is its span. ``spans`` holds the
    distance from each character's left edge to the next character's, which
    adds TeX's kern. ``heights`` holds, to within a fraction of a pixel, the
    height matplotlib gives each character typeset on its own, depth included.
    """
    outlines: tuple[tuple[np.ndarray, np.ndarray], ...]
    widths: tuple[float, ...]
    spans: tuple[float, ...]
    heights: tuple[float, ...]


class _TexItem(NamedTuple):
    """A glyph or rule a TeX run sets: its position along the run, its own
    width, and its outline ``(vertices, codes)``, all in the converter's
    units."""
    x: float
    width: float
    outline: tuple[np.ndarray, np.ndarray]


class _FontLines(NamedTuple):
    """Ascender and descender heights above the baseline, in 1/100-em layout
    units. The descender lies below the baseline, so it is negative."""
    ascender: float
    descender: float


class _SegmentPlace(NamedTuple):
    """Where one segment goes: the frame it rides, the arc length of its left
    edge on it, its own width in pixels, and the vertical-alignment datum in
    layout units. The frame holds display pixels for one renderer, so a place
    made for another renderer does not fit."""
    frame: _CurveFrame
    s_left: float
    width_px: float
    datum: float


class _BoxPlace(NamedTuple):
    """The casing's centerline in display pixels and its line width in points."""
    xy_px: np.ndarray
    linewidth: float


class _Placement(NamedTuple):
    """One placement of a label for one renderer: a place for each segment, in
    order, and the casing's, when the label has one. It is a value, kept
    apart from what the segments draw, so measuring a label for any renderer
    changes nothing on screen."""
    segments: tuple[_SegmentPlace, ...]
    box: _BoxPlace | None


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


def _checked_length(name: str, value: float | str | None
                    ) -> float | str | None:
    """A length argument as the label stores it: ``None`` (also for 0),
    ``"auto"``, or a positive length in points. Anything else raises, naming
    the argument ``name``."""
    if value is None:
        return None
    if isinstance(value, str):
        if value != "auto":
            raise ValueError(
                f"{name} must be None, 'auto', or a number, got {value!r}")
        return value
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, numbers.Real):
        raise TypeError(
            f"{name} must be None, 'auto', or a number, got {value!r}")
    if not math.isfinite(value) or value < 0:
        raise ValueError(
            f"{name} must be finite and at least 0, got {value!r}")
    return float(value) or None


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


def _axis_floats(axis: Any, values: Any) -> np.ndarray:
    """``values`` converted by ``axis``'s units into a float array, with masked
    entries set to NaN, as matplotlib's own lines read their data."""
    return np.ma.asarray(axis.convert_units(values), dtype=float).filled(np.nan)


def _at_position(values: Any, index: int) -> Any:
    """The element of ``values`` at position ``index``, as given: a pandas
    Series indexes by label, so ``values[index]`` can miss."""
    return next(itertools.islice(iter(values), index, None))


def _font_lines(prop: font_manager.FontProperties, *,
                usetex: bool) -> _FontLines:
    """The ascender and descender lines of the font the text is drawn in.

    Without usetex that is the matplotlib font ``prop`` names, whose lines are
    the ascender and descender FreeType reports. Under usetex it is the TeX font
    LaTeX sets the text in (:func:`_tex_font_lines`).
    """
    if usetex:
        return _tex_font_lines(prop.get_size_in_points())
    font = font_manager.get_font(font_manager.findfont(prop))
    units = _text_to_path.FONT_SCALE / font.units_per_EM
    return _FontLines(font.ascender * units, font.descender * units)


def _tex_font_lines(size: float) -> _FontLines:
    """The ascender and descender lines of the TeX font LaTeX sets text in at
    ``size`` points: the height and depth TeX gives ``_TEX_LINE_PROBE``.

    LaTeX chooses that font from the preamble, the ``font.family`` rcParam,
    and the size (cmss8 at 8 pt, cmss17 at 30 pt), and TeX takes the box from
    the font's metrics at the size it draws the font, so a font the preamble
    loads scaled (``helvet`` with ``scaled=0.92``) yields lines scaled with its
    glyphs. The measurement is matplotlib's own for usetex text, and after the
    first draw it reads LaTeX's cached DVI file. matplotlib reports the height
    including the depth, in points, so scaling by ``FONT_SCALE / size`` gives
    the 1/100-em layout units the usetex outlines are brought to
    (:func:`_layout_units`).
    """
    _, height, depth = TexManager().get_text_width_height_descent(
        _TEX_LINE_PROBE, size)
    units = _text_to_path.FONT_SCALE / size
    return _FontLines((height - depth) * units, -depth * units)


def _tex_min_line_height(size: float) -> float:
    """The least height, depth included, matplotlib gives a line of usetex text
    at ``size`` points, in 1/100-em layout units: the height of the box TeX
    gives ``_TEX_MIN_LINE_PROBE``, as for :func:`_tex_font_lines`."""
    _, height, _ = TexManager().get_text_width_height_descent(
        _TEX_MIN_LINE_PROBE, size)
    return height * _text_to_path.FONT_SCALE / size


def _valign_datum(valign: str, lines: _FontLines) -> float:
    """Height above the baseline, in 1/100-em layout units, that lies on the
    curve for the given vertical alignment.

    ``"baseline"`` returns 0, so the text baseline follows the curve unshifted.
    The others shift every segment by the same font-metric constant: the curve
    passes through the vertical center, the ascender line, or the descender
    line. Plain glyphs and mathtext stay aligned, and no per-glyph step is
    introduced, because the shift is identical for every glyph.
    """
    if valign == "baseline":
        return 0.0
    if valign == "ascender":
        return lines.ascender
    if valign == "descender":
        return lines.descender
    return (lines.ascender + lines.descender) / 2.0  # "center"


def _kern_units(prop: font_manager.FontProperties, left: str,
                right: str) -> float:
    """The kern between two characters of the matplotlib font ``prop`` names,
    in 1/100-em layout units, as matplotlib's own text layout applies it
    (:func:`_font_kern_units`)."""
    return _font_kern_units(font_manager.findfont(prop), left, right,
                            mpl.rcParams["text.hinting_factor"],
                            mpl.rcParams["text.kerning_factor"])


@functools.lru_cache(maxsize=_KERN_CACHE_SIZE)
def _font_kern_units(fname: str, left: str, right: str, hinting_factor: Any,
                     kerning_factor: Any) -> float:
    """The kern between two characters of the font file ``fname``, in 1/100-em
    layout units: how far kerning alone moves the right glyph in matplotlib's
    own layout of the pair.

    Taking it from matplotlib's layout, rather than from the font's ``kern``
    table, follows whichever source matplotlib kerns from: the ``kern`` table up
    to 3.10, and the GPOS table through HarfBuzz from 3.11, where many fonts
    keep their only kerning or a different one. Before 3.11 the layout sets the
    right glyph at the left glyph's unhinted advance plus the kern. From 3.11
    the layout also shapes the pair (it reorders right-to-left text, picks
    Arabic joining forms, attaches combining marks, hides format characters
    such as the soft hyphen, and rounds advances), so the kern is the
    difference between the pair laid out with and without the ``kern``
    feature, which cancels the rest.

    Zero when the font lacks either character, when the layout does not yield
    one glyph per character (a ligature), and for right-to-left characters.
    ``hinting_factor`` and ``kerning_factor`` are the rcParams of those names:
    matplotlib keys its font objects on them and, before 3.11, kerns through
    them, so they key this cache too.
    """
    if any(unicodedata.bidirectional(c) in _RTL_CLASSES for c in (left, right)):
        return 0.0
    font = font_manager.get_font(fname)
    if not font.get_char_index(ord(left)) or not font.get_char_index(ord(right)):
        return 0.0
    font.set_size(_text_to_path.FONT_SCALE, _text_to_path.DPI)
    pair = left + right
    kerned = _text_to_path.get_glyphs_with_font(font, pair)[0]
    if _LAYOUT_TAKES_FEATURES:
        unkerned = _text_to_path.get_glyphs_with_font(  # type: ignore[call-arg]
            font, pair, features=("-kern",))[0]
    else:
        unkerned = kerned
    if len(kerned) != 2 or len(unkerned) != 2:
        return 0.0
    _, x_kerned, _, _ = kerned[1]
    if _LAYOUT_TAKES_FEATURES:
        _, x_unkerned, _, _ = unkerned[1]
    else:
        # FreeType's linear advance is unhinted, in 16.16 fixed point.
        x_unkerned = font.load_char(ord(left)).linearHoriAdvance / 65536
    return (x_kerned - x_unkerned) * _layout_units(_text_to_path)


class _CurveFrame:
    """Display-space curve geometry: cumulative arc length with an elementwise
    point-and-tangent lookup.

    Arc lengths past either end of the curve clip into the two end links,
    so lookups there extrapolate along the end tangents and an overrunning
    label follows a straight extension instead of being clipped.
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
        the curve and the tangent angle of the local link, elementwise."""
        i = np.clip(np.searchsorted(self._arc, s) - 1, 0, len(self._arc) - 2)
        d = self._arc[i + 1] - self._arc[i]
        f = np.where(d != 0.0, (s - self._arc[i]) / np.where(d != 0.0, d, 1.0),
                     0.0)
        x = self._xf[i] + f * (self._xf[i + 1] - self._xf[i])
        y = self._yf[i] + f * (self._yf[i + 1] - self._yf[i])
        return x, y, self._rads[i]

    def chord_angles(self, s, span):
        """Angle of the chord across ``[s, s + span]``, elementwise.

        The chord gives the rotation of a glyph of width ``span``: it follows the
        local tangent but averages over the glyph's own width, so it stays
        smooth across the vertices of a coarsely sampled polyline instead of
        snapping to the angle of each link between two points. Degenerate chords
        (zero ``span`` or a zero-length piece of the curve) fall back to the
        tangent of the link.
        """
        xl, yl, rad = self.points_and_angles(s)
        xr, yr, _ = self.points_and_angles(np.asarray(s) + span)
        return np.where((xr == xl) & (yr == yl), rad,
                        np.arctan2(yr - yl, xr - xl))

    def curvature(self, s, span):
        """Signed turning rate (radians per pixel) over ``[s, s + span]``.

        The tangent is sampled as the chord across each half of the span,
        ``[s, s + span/2]`` and ``[s + span/2, s + span]``, whose midpoints lie
        ``span/2`` apart. The wrapped angle between those two chords, divided by
        that ``span/2`` separation, estimates the curvature at the glyph's own
        length scale, the same scale :meth:`chord_angles` smooths rotation over.
        On a circle of radius ``R`` it recovers ``1/R``. Positive turns left. A
        straight piece of the curve (or a degenerate ``span``) yields zero, so a
        straight guide is left untouched by any curvature-driven adjustment.
        """
        half = np.asarray(span, dtype=float) / 2.0
        a0 = self.chord_angles(s, half)
        a1 = self.chord_angles(np.asarray(s) + half, half)
        turn = np.arctan2(np.sin(a1 - a0), np.cos(a1 - a0))
        return np.where(half > 0.0, turn / np.where(half > 0.0, half, 1.0), 0.0)

    def offset(self, distance: float) -> _CurveFrame:
        """The parallel (offset) curve at perpendicular ``distance`` pixels.

        Each vertex is displaced along the local normal: the bisector of the
        tangents of its two adjacent links at interior vertices, the tangent of
        the single link at the ends. The returned frame is the curve the label
        follows when offset. Walking glyphs along it, instead of projecting them
        off the base curve, keeps both the perpendicular clearance and the
        on-screen letter spacing uniform, because the cursor advances along the
        very curve the glyphs sit on. Positive ``distance``
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
        # Interior vertices lie on the bisector of the adjacent unit tangents; a
        # near-zero sum means the curve doubles back on itself, so fall back to
        # the incoming segment tangent there rather than divide by zero.
        mx, my = tx[:-1] + tx[1:], ty[:-1] + ty[1:]
        mlen = np.hypot(mx, my)
        safe = mlen > 1e-12
        denom = np.where(safe, mlen, 1.0)
        vtx[1:-1] = np.where(safe, mx / denom, tx[:-1])
        vty[1:-1] = np.where(safe, my / denom, ty[:-1])
        return _CurveFrame(self._xf - distance * vty, self._yf + distance * vtx)

    def rounded(self, radius: float, side: int, step: float
                ) -> tuple[_CurveFrame, bool]:
        """This curve with every bend toward ``side`` (+1 left, -1 right) that
        is tighter than ``radius`` pixels replaced by a circular arc of that
        radius, with the same number of vertices, and whether a bend comes
        within the ball's reach of either end of the curve.

        The curve is sampled every ``step`` pixels. A ball of ``radius`` rolled
        along ``side`` of it touches the curve at a point when its center, on
        the parallel curve, is no closer than ``radius`` to any other point
        within ``_ROUND_REACH`` radii of arc length. Each run of points the ball
        cannot touch is laid on the arc of the ball wedged in the corner, which
        keeps the curve continuous. Bends gentler than the ball are left
        exactly as they are, and so is a run that reaches an end of the curve.
        The curve itself is returned, not a copy, when nothing changes.

        A point near an end does not see all the curve within reach of it, so a
        run that comes within reach of an end is not the run a longer curve
        would give: the flag is true then, to ask the caller for a longer one.
        """
        n = len(self._xf)
        if radius <= 0.0 or n < 3:
            return self, False
        centers = self.offset(side * radius)
        px, py, cx, cy = self._xf, self._yf, centers._xf, centers._yf
        limit = (radius - _ROUND_TOL_PX) ** 2
        reach = min(math.ceil(_ROUND_REACH * radius / step), n - 1)
        invalid = np.zeros(n, dtype=bool)
        for k in range(1, reach + 1):
            # Point i is compared with point i + k, and point i + k with point
            # i, so each pair is tested from both ends: the center belongs to
            # one point and the curve to the other.
            invalid[:-k] |= (cx[:-k] - px[k:]) ** 2 + (cy[:-k] - py[k:]) ** 2 < limit
            invalid[k:] |= (cx[k:] - px[:-k]) ** 2 + (cy[k:] - py[:-k]) ** 2 < limit
        if not invalid.any():
            return self, False
        x, y = px.copy(), py.copy()
        bad = np.flatnonzero(invalid)
        near_end = False
        for run in np.split(bad, np.flatnonzero(np.diff(bad) > 1) + 1):
            a, b = int(run[0]), int(run[-1])
            near_end |= a < reach or b >= n - reach
            if a == 0 or b == n - 1:
                continue
            fraction = np.arange(1, b - a + 2) / (b - a + 2)
            gap = np.hypot(cx[b + 1] - cx[a - 1], cy[b + 1] - cy[a - 1])
            if gap > max(_ROUND_BLEND_STEPS * step, _ROUND_BLEND_RADIUS * radius):
                # The balls either side of the run do not meet at one point, so
                # no single ball fits: blend the two ends with their tangents.
                chord = np.hypot(px[b + 1] - px[a - 1], py[b + 1] - py[a - 1])
                m0 = chord * np.array([np.cos(self._rads[a - 1]),
                                       np.sin(self._rads[a - 1])])
                end = self._rads[min(b + 1, n - 2)]
                m1 = chord * np.array([np.cos(end), np.sin(end)])
                p0 = np.array([px[a - 1], py[a - 1]])
                p1 = np.array([px[b + 1], py[b + 1]])
                t = fraction[:, None]
                blend = ((2 * t ** 3 - 3 * t ** 2 + 1) * p0
                         + (t ** 3 - 2 * t ** 2 + t) * m0
                         + (-2 * t ** 3 + 3 * t ** 2) * p1
                         + (t ** 3 - t ** 2) * m1)
                x[a:b + 1], y[a:b + 1] = blend[:, 0], blend[:, 1]
                continue
            ccx = (cx[a - 1] + cx[b + 1]) / 2.0
            ccy = (cy[a - 1] + cy[b + 1]) / 2.0
            phi0 = np.arctan2(py[a - 1] - ccy, px[a - 1] - ccx)
            phi1 = np.arctan2(py[b + 1] - ccy, px[b + 1] - ccx)
            sweep = np.mod(side * (phi1 - phi0), 2.0 * np.pi) * side
            r0 = np.hypot(px[a - 1] - ccx, py[a - 1] - ccy)
            r1 = np.hypot(px[b + 1] - ccx, py[b + 1] - ccy)
            rad = r0 + fraction * (r1 - r0)
            x[a:b + 1] = ccx + rad * np.cos(phi0 + fraction * sweep)
            y[a:b + 1] = ccy + rad * np.sin(phi0 + fraction * sweep)
        return _CurveFrame(x, y), near_end

    def remap_arc(self, other: _CurveFrame, s):
        """Map arc length ``s`` on this curve to the corresponding arc length on
        ``other``, a curve sharing this one's vertices (its :meth:`offset`).

        The point at fraction ``f`` of this curve's link ``i`` maps to
        fraction ``f`` of ``other``'s link ``i``. ``pos`` and ``anchor`` are
        given against the base curve, so this carries the anchor over to the
        offset curve the label is laid along. The label lands where the user
        asked on the original curve while keeping even spacing on the offset
        one. On a straight guide the two curves have equal-length links, so
        the map is the identity.
        """
        s = np.asarray(s, dtype=float)
        i = np.clip(np.searchsorted(self._arc, s) - 1, 0, len(self._arc) - 2)
        d = self._arc[i + 1] - self._arc[i]
        f = np.where(d != 0.0, (s - self._arc[i]) / np.where(d != 0.0, d, 1.0),
                     0.0)
        return other._arc[i] + f * (other._arc[i + 1] - other._arc[i])


# How close, relative to the drawn length, ``pos`` must come to the point where
# one stretch ends and the next starts to count as that point: rounding in
# ``pos * length`` must not move the anchor off the boundary onto the other
# stretch.
_BOUNDARY_TOLERANCE = 1e-9

# How short, relative to the span it crosses, a chord must be to count as having
# no length, and how far from vertical (relative to its length) to count as
# vertical: rounding must not decide the reading direction of a label.
_CHORD_TOLERANCE = 1e-9


# The open interval of values each axis scale with a bounded domain can place.
# With ``nonpositive="clip"``, the default on a log axis, a log axis sends 0
# and below, and a logit axis anything outside (0, 1), to a finite pixel far
# outside the axes, where a line's segment toward it leaves the view but a
# label would follow it out.
_SCALE_DOMAINS = {"log": (0.0, np.inf), "logit": (0.0, 1.0)}


def _gaps_outside_domain(scale: str, values: np.ndarray) -> np.ndarray:
    """``values`` with those outside the domain of the axis ``scale`` set to
    NaN, so they leave a gap as a masked point does; values on any other
    scale, including custom ones, as they are."""
    domain = _SCALE_DOMAINS.get(scale)
    if domain is None:
        return values
    low, high = domain
    with np.errstate(invalid="ignore"):
        return np.where((values > low) & (values < high), values, np.nan)


def _shown(curve_px: np.ndarray) -> np.ndarray:
    """Which points of the curve, in display pixels, the axes show: those with
    finite coordinates. A NaN, infinite, or masked point is not shown, and nor
    is a point the axes' scale masks or one outside a log or logit axis's
    domain (:func:`_gaps_outside_domain`)."""
    return np.isfinite(curve_px).all(axis=1)


def _stretch_at(curve_px: np.ndarray, pos: float,
                anchor: str) -> tuple[np.ndarray, float] | None:
    """The stretch (a connected piece of the curve between gaps), in display
    pixels, that holds the point
    ``pos`` of the way along the drawn length, and that point's arc length
    along the stretch; None when nothing is drawn.

    A line breaks at a point that is not shown and draws nothing at an
    isolated point, so the drawn length is that of the links between two
    shown points. A point where one stretch ends and the next starts belongs
    to the stretch the label extends onto: the earlier one for
    ``anchor="end"``, the later one otherwise. ``pos`` below 0 or above 1 lies
    before the first stretch or past the last. Only links with a length
    hold the point, and the stretch is returned without the links of no
    length at its ends, such as a repeated last point, so a label that
    overruns it follows a real end tangent."""
    shown = _shown(curve_px)
    drawn = shown[:-1] & shown[1:]
    with np.errstate(invalid="ignore"):
        steps = np.diff(curve_px, axis=0)
    lengths = np.where(drawn, np.hypot(steps[:, 0], steps[:, 1]), 0.0)
    measured = np.flatnonzero(lengths > 0.0)
    if not len(measured):
        return None
    ends = np.cumsum(lengths)
    total = float(ends[-1])
    target = pos * total
    breaks = np.flatnonzero(~drawn)
    if len(breaks):
        boundary = float(ends[breaks[np.argmin(np.abs(ends[breaks] - target))]])
        if abs(boundary - target) <= _BOUNDARY_TOLERANCE * total:
            target = boundary
    side: Literal["left", "right"] = "left" if anchor == "end" else "right"
    segment = int(np.clip(np.searchsorted(ends, target, side=side),
                          measured[0], measured[-1]))
    # The stretch runs between the undrawn segments around ``segment``, from
    # its first segment with a length to its last.
    first = int(breaks[breaks < segment].max(initial=-1)) + 1
    last = int(breaks[breaks > segment].min(initial=len(drawn)))
    inside = measured[(measured >= first) & (measured < last)]
    first, last = int(inside[0]), int(inside[-1]) + 1
    before = float(ends[first - 1]) if first else 0.0
    return curve_px[first:last + 1], target - before


def _path_reversals(x: np.ndarray, y: np.ndarray, chord: int, first: int,
                    last: int) -> int:
    """The number of times the turn of the path's direction changes sign.

    ``(x, y)`` is an evenly sampled path, and ``first`` and ``last`` are the
    indices of the samples it is judged between. The path is laid out as chords
    of ``chord`` samples, end to end. A turn is the change of direction from one
    chord to the next, wrapped to half a turn either way; one smaller than
    ``_SMOOTH_DEADBAND`` is ignored and does not break a run of turns the same
    way. Chords that start at the same phase of a wiggle as they end see no
    wiggle, so the path is laid out from three starting offsets, and the most
    reversals of the three count. Zero where fewer than three chords fit.
    """
    first, last = max(first, 0), min(last, len(x) - 1)
    most = 0
    for offset in sorted({0, chord // 3, 2 * chord // 3}):
        starts = np.arange(first + offset, last - chord + 1, chord)
        if len(starts) < 3:
            continue
        direction = np.arctan2(y[starts + chord] - y[starts],
                               x[starts + chord] - x[starts])
        turns = (np.diff(direction) + np.pi) % (2.0 * np.pi) - np.pi
        sides = np.sign(turns[np.abs(turns) >= _SMOOTH_DEADBAND])
        most = max(most, int(np.count_nonzero(sides[1:] != sides[:-1])))
    return most


def _smoothing_window(length: float, covered: tuple[float, float],
                      sigma: float) -> tuple[float, float, int]:
    """The part of a stretch of ``length`` pixels that is smoothed: its start
    (arc length along the stretch, pixels), the step between its samples
    (pixels) and the number of steps.

    The part runs from a margin before ``covered`` to a margin after it, within
    the stretch, so rounding and the offset find smoothed path to work on. The
    step depends on ``sigma`` alone, and the start and the end sit on whole
    steps of arc length, so the samples are the same wherever the label moves
    along the stretch, and a label that is moved a little moves only by the
    same little. A label past an end of the stretch gets the last step of it,
    so it rides the smoothed end tangent as one on the stretch does.
    """
    margin = max(_SMOOTH_MARGIN * sigma, 2.0 * (covered[1] - covered[0]))
    step = max(_SMOOTH_STEP * sigma, _SMOOTH_MIN_STEP_PX)
    # Over the most samples allowed the step doubles, which keeps the grid.
    crowded = ((covered[1] - covered[0] + 2.0 * margin) / step
               / _SMOOTH_MAX_SAMPLES)
    if crowded > 1.0:
        step *= 2.0 ** math.ceil(math.log2(crowded))
    stop = math.ceil(min(length, covered[1] + margin) / step) * step
    start = min(math.floor((covered[0] - margin) / step) * step, stop - step)
    start = max(start, 0.0)
    return start, step, max(1, round((stop - start) / step))


def _smoothed_stretch(points: np.ndarray, s_anchor: float, sigma: float,
                      covered: tuple[float, float], only_if_wiggly: bool
                      ) -> tuple[np.ndarray, float, float | None]:
    """The part of the stretch ``points`` (display pixels) around the label,
    smoothed by a Gaussian of standard deviation ``sigma`` pixels along its arc
    length, with the correction for the shrinking of bends; the arc length on it
    of the point at ``s_anchor`` on the stretch; and the arc length along the
    stretch at which the part starts.

    ``covered`` is the interval of arc length, in pixels along the stretch, that
    the label covers, and ``_smoothing_window`` chooses the part. It is
    resampled evenly by arc length from the stretch itself, which a frame
    extends past each end along its end tangent, so an end does not pull in.
    The samples stay one to one after smoothing, which carries the anchor
    across; an anchor off the part, as ``pos`` outside 0 to 1 puts it, keeps
    its distance from the end. The arc length it returns is measured along the
    smoothed part, from where the part starts.

    The stretch itself comes back, unchanged, with no start (None), where
    ``sigma`` is too small to matter or, with ``only_if_wiggly``, the path does
    not wiggle where the label covers it (``_path_reversals``).
    """
    if sigma < _SMOOTH_MIN_PX:
        return points, s_anchor, None
    frame = _CurveFrame(points[:, 0], points[:, 1])
    if not np.isfinite(frame.length) or frame.length <= 0.0:
        return points, s_anchor, None
    start, step, count = _smoothing_window(frame.length, covered, sigma)
    reach = min(math.ceil(_SMOOTH_REACH * sigma / step), _SMOOTH_MAX_REACH)
    x, y, _ = frame.points_and_angles(
        start + step * np.arange(-2 * reach, count + 2 * reach + 1))
    # The samples before smoothing are the middle of the padded ones.
    middle = slice(2 * reach, 2 * reach + count + 1)
    if only_if_wiggly and _path_reversals(
            x[middle], y[middle], max(1, round(_SMOOTH_CHORD * sigma / step)),
            math.floor((covered[0] - start) / step),
            math.ceil((covered[1] - start) / step)) < _SMOOTH_REVERSALS:
        return points, s_anchor, None
    kernel = np.exp(-0.5 * (step * np.arange(-reach, reach + 1) / sigma) ** 2)
    kernel /= kernel.sum()
    smoothed = np.empty((count + 1, 2))
    for column, values in enumerate((x, y)):
        once = np.convolve(values, kernel, "valid")
        twice = np.convolve(once, kernel, "valid")
        smoothed[:, column] = 2.0 * once[reach:reach + count + 1] - twice
    arc = _CurveFrame(smoothed[:, 0], smoothed[:, 1])._arc
    # ``beyond`` is how far, in steps, the anchor is off either end of the part;
    # ``np.interp`` clamps there, so the distance is added back.
    index = (s_anchor - start) / step
    beyond = index - min(max(index, 0.0), float(count))
    return (smoothed,
            float(np.interp(index, np.arange(count + 1), arc) + beyond * step),
            start)


def _reads_leftward(frame: _CurveFrame, s_anchor: float, lead: float,
                    span: float) -> bool:
    """Whether text laid along ``frame`` across ``span`` pixels, with the
    fraction ``lead`` of it before the arc length ``s_anchor``, reads leftward
    on screen: its chord points left, or straight down.

    A vertical chord counts as upward, so a label on a vertical curve reads
    from bottom to top, as :class:`~matplotlib.text.Text` does at a rotation of
    90 degrees. A chord of no length, as on a closed curve whose label covers
    all of it, is judged by the tangent at the anchor.
    """
    start = s_anchor - lead * span
    xs, ys, rad = frame.points_and_angles(np.array([start, start + span,
                                                     s_anchor]))
    dx, dy = xs[1] - xs[0], ys[1] - ys[0]
    if np.hypot(dx, dy) <= _CHORD_TOLERANCE * span:
        dx, dy = np.cos(rad[2]), np.sin(rad[2])
    if abs(dx) <= _CHORD_TOLERANCE * np.hypot(dx, dy):
        return bool(dy < 0.0)
    return bool(dx < 0.0)


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


def _tex_source(char: str) -> str:
    """The literal TeX source for one plain character under usetex."""
    if char.isspace():
        return _TEX_SPACE
    return _CHAR_TO_TEX.get(char, char)


def _tex_run_layout(chars: str, size: float) -> _TexRunLayout | None:
    """The plain run ``chars`` typeset by LaTeX in one pass at ``size`` points
    (:func:`_typeset_tex_run`), or None when its characters are typeset one at
    a time."""
    # The rcParams matplotlib's TexManager writes a LaTeX job's preamble from:
    # the user's preamble, the font family, and each family's font list, from
    # which it picks the font package ("Times" in font.serif loads mathptmx).
    # Font lists are lists; their text form is hashable and keeps every entry.
    rc = mpl.rcParams
    tex_config = tuple(str(value) for value in (
        rc["text.latex.preamble"], rc["font.family"], rc["font.serif"],
        rc["font.sans-serif"], rc["font.cursive"], rc["font.monospace"]))
    return _typeset_tex_run(chars, size, tex_config)


@functools.lru_cache(maxsize=_TEX_RUN_CACHE_SIZE)
def _typeset_tex_run(chars: str, size: float,
                     tex_config: tuple[str, ...]) -> _TexRunLayout | None:
    """Typeset the plain run ``chars`` with one LaTeX pass and split it per
    character.

    One pass, rather than one per distinct character, keeps TeX's kerning
    between neighbors. Each printing character sets one glyph, or one rule
    (``\\_`` draws a rule in the default encoding); taken in order along the
    run, the items pair with the printing characters. The run returns None, to
    be typeset one character at a time, when a printing character may not set
    exactly one item of its own (``_TEX_UNPAIRED_CATEGORIES``), or when the run
    sets a different number of items (an accented letter can set an accent and
    a letter).

    ``tex_config`` holds the rcParams matplotlib's TexManager writes the LaTeX
    preamble from (see :func:`_tex_run_layout`); it keys the cache only, so a
    change to any of them typesets the run again.
    """
    printing_chars = [char for char in chars if not char.isspace()]
    if any(unicodedata.category(char) in _TEX_UNPAIRED_CATEGORIES
           for char in printing_chars):
        return None
    converter = _tex_to_path(size)
    source = _tex_run_source(chars)
    with dviread.Dvi(TexManager().make_dvi(source, converter.FONT_SCALE),
                     converter.DPI) as dvi:
        page, = dvi
    # get_glyphs_tex reads the same page, listing the glyphs in the order of
    # ``page.text`` and the rules in the order of ``page.boxes``, which pairs
    # each item's outline with its position and width. The first and last rules
    # are the edge rules that bound the run, not characters.
    glyph_info, glyph_map, rects = converter.get_glyphs_tex(
        font_manager.FontProperties(size=size), source)
    start, *rules, end = page.boxes
    items = sorted(
        [_TexItem(text.x, text.width, _place_glyph(glyph_map, *info))
         for text, info in zip(page.text, glyph_info)]
        + [_TexItem(box.x, box.width,
                    (np.asarray(verts, float), np.asarray(codes)))
           for box, (verts, codes) in zip(rules, rects[1:-1])],
        key=lambda item: item.x)
    if len(items) != len(printing_chars):
        return None
    lefts = _char_lefts(chars, items, start.x + start.width, end.x)
    units = _layout_units(converter)
    spans = np.diff(np.append(lefts, end.x)) * units
    min_height = _tex_min_line_height(size)
    empty = (np.empty((0, 2)), np.empty(0, dtype=Path.code_type))
    outlines, widths, heights = [], [], []
    printing_items = iter(items)
    for char, span in zip(chars, spans):
        if char.isspace():
            outlines.append(empty)
            widths.append(span)
            heights.append(min_height)
            continue
        item = next(printing_items)
        verts = (item.outline[0] - [item.x, 0.0]) * units
        codes = np.asarray(item.outline[1], dtype=Path.code_type)
        outlines.append((verts, codes))
        widths.append(item.width * units)
        # matplotlib measures a character on its own at least as tall as "lp",
        # and taller when the character's TeX box is; its ink stands in for that
        # box, to within a fraction of a pixel.
        heights.append(max(min_height, Path(verts, codes).get_extents().height))
    return _TexRunLayout(tuple(outlines), tuple(widths), tuple(spans),
                         tuple(heights))


def _tex_run_source(chars: str) -> str:
    """The TeX source that typesets the plain run ``chars`` in one pass.

    Each printing character keeps its literal source (:func:`_tex_source`), and
    each whitespace character is a control space, an interword space TeX
    neither drops nor collapses. An empty group breaks each ligature pair, an
    edge rule marks each end of the run, and a box keeps the run on one line.
    """
    pieces = [r"\mbox{", _TEX_EDGE]
    for previous, char in zip(" " + chars, chars):
        if previous + char in _TEX_LIGATURES:
            pieces.append("{}")
        pieces.append(r"\ " if char.isspace() else _tex_source(char))
    pieces += [_TEX_EDGE, "}"]
    return "".join(pieces)


def _place_glyph(glyph_map: dict, glyph_id: str, x_pen: float, y_pen: float,
                 scale: float) -> tuple[np.ndarray, np.ndarray]:
    """One glyph of a converter's layout (``get_glyphs_tex`` or
    ``get_glyphs_mathtext``) at its pen position, in the converter's units."""
    verts, codes = glyph_map[glyph_id]
    verts = np.asarray(verts, float).reshape(-1, 2)
    return verts * scale + [x_pen, y_pen], np.asarray(codes)


def _char_lefts(chars: str, items: list[_TexItem], start: float,
                end: float) -> list[float]:
    """The left edge of each character of a run, from its ``items`` in order
    along the run, which spans ``start`` to ``end``.

    A printing character starts at its item. Whitespace sets no item, so each
    stretch of it splits the gap between the item before (or ``start``) and the
    item after (or ``end``) evenly, every space being one interword space.
    """
    lefts: list[float] = []
    edge = start
    index = 0
    for is_space, group in itertools.groupby(chars, key=str.isspace):
        count = len(list(group))
        if is_space:
            following = items[index].x if index < len(items) else end
            lefts += [edge + (following - edge) * k / count for k in range(count)]
            continue
        for item in items[index:index + count]:
            lefts.append(item.x)
            edge = item.x + item.width
        index += count
    return lefts


@functools.cache
def _tex_to_path(size: float) -> TextToPath:
    """A converter that runs LaTeX at ``size`` points and lays the outline out
    in 1/100-em layout units, as the shared converter does.

    matplotlib measures a usetex advance by running LaTeX at the label's own
    size, and TeX fonts change design with size (cmss8 at 8 pt, cmss12 at
    12 pt). The shared converter runs LaTeX at its fixed 100 pt ``FONT_SCALE``,
    which selects a different design from the one measured. Laying the outline
    out at the label size draws the measured design, and matplotlib's
    measurement and the outline share one cached LaTeX run.

    The converter loads usetex glyphs with FreeType hinting at ``FONT_SCALE``
    points and ``DPI`` dots per inch. At the default 72 dpi a 10 pt glyph is
    hinted on a 10-pixel em, which snaps an x-height of 0.44 em to 0.50 em.
    Raising ``DPI`` so the em spans at least 100 pixels makes the hinting
    negligible. FreeType takes the DPI as a whole number while matplotlib places
    the glyphs at the exact value, so ``DPI`` is rounded up to a whole number,
    and :func:`_layout_units` absorbs the rest.
    """
    converter = TextToPath()
    converter.FONT_SCALE = size
    converter.DPI = math.ceil(
        _text_to_path.DPI * _text_to_path.FONT_SCALE / size)
    return converter


def _layout_units(converter: TextToPath) -> float:
    """1/100-em layout units per unit of ``converter``'s outline.

    A converter lays out ``FONT_SCALE * DPI / 72`` pixels per em. That is 100
    for the shared converter, so the factor is 1 there, and within 1% of 1
    for a :func:`_tex_to_path` converter at any size up to 72 pt.
    """
    em_px = converter.FONT_SCALE * converter.DPI / _text_to_path.DPI
    return _text_to_path.FONT_SCALE / em_px


def _px_per_unit(renderer, size_points: float) -> float:
    """Display pixels per 1/100-em layout unit, for text ``size_points`` high.

    Outlines and advances come in layout units, 100 to the em at the shared
    converter's ``FONT_SCALE``, so this is the em in pixels over that scale. A
    :func:`_tex_to_path` outline also needs :func:`_layout_units`.
    """
    return renderer.points_to_pixels(size_points) / _text_to_path.FONT_SCALE


def _measuring_renderer(figure) -> RendererAgg:
    """A renderer to measure a label with outside a draw: the canvas's own on
    Agg canvases, which make one on request, or else an Agg renderer at the
    figure's dpi (:func:`_agg_renderer`). A canvas such as PDF makes its
    renderer only while drawing, at 72 dpi. A label's placement depends on the
    renderer chiefly through the dpi; text metrics differ between backends by a
    fraction of a pixel, so the label measures to within that of how any canvas
    at that dpi draws it."""
    get_renderer = getattr(figure.canvas, "get_renderer", None)
    if get_renderer is not None:
        return get_renderer()
    return _agg_renderer(figure.dpi)


@functools.lru_cache(maxsize=8)
def _agg_renderer(dpi: float) -> RendererAgg:
    """A one-pixel Agg renderer at ``dpi``, kept per dpi. Measuring needs its
    text metrics and resolution, not a canvas, and keeping it lets a
    measurement reuse the label's placement (``CurvedText._placement_key``)."""
    return RendererAgg(1, 1, dpi)


class _OutlineSegment(mtext.Text):
    """A curved-label segment drawn by mapping a baseline-relative glyph outline
    through the curve frame.

    One segment is either a plain character (:class:`_PlainGlyph`) or a math run
    (:class:`_MathRun`). Both subclass :class:`~matplotlib.text.Text` so the
    parent's cursor walk measures every segment the same way, through
    :meth:`_size_px`. Both keep the text baseline as the shared datum
    (``v = 0``), so plain glyphs and math runs sit on one baseline by construction.

    Placement maps an outline point ``(u, v)`` (arc length from the segment's
    left edge and height above the baseline, both in 1/100-em layout units) into
    display pixels. ``v`` is shifted by the vertical-alignment datum
    (:func:`_valign_datum`), so the chosen line (baseline, center, ascender, or
    descender) is what lies on the curve. Because each glyph is placed by an
    isometry, the perpendicular distance from the curve equals ``v`` exactly.
    There is no per-glyph step, and plain and math are identical by construction.

    Subclasses differ only in where the outline comes from
    (:meth:`_build_outline`) and whether it is placed rigidly or bent along the
    curve (:attr:`_bend`). Any perpendicular offset is already baked into the
    frame (it is the parallel curve), so a segment follows the frame with no
    offset handling of its own.
    """

    #: Whether the outline bends along the curve (math runs) or is placed rigidly
    #: as a single undistorted glyph (plain characters).
    _bend = False

    def __init__(self, text: str, **kwargs: Any) -> None:
        super().__init__(0.0, 0.0, text, **kwargs)
        # The container positions and draws every segment, and the axes never
        # sees one, so the Text position is not where the segment appears.
        # The container measures the segment's size there (``_size_px``),
        # so the position is the display origin, which has a pixel on every
        # axis scale; the data origin has none on a logit axis, a log axis that
        # masks non-positive values, or polar axes whose radial limits start
        # above zero. The axes keep a transform already set.
        # A ``transform`` keyword forwarded from the label is replaced on
        # purpose: the segment draws in display pixels and never uses it.
        self.set_transform(IdentityTransform())
        self._outline_cache: tuple | None = None
        self._band_cache: tuple | None = None

    def _size_px(self, renderer) -> tuple[float, float]:
        """This segment's unrotated width and height in display pixels, as
        matplotlib measures its text at its Text position, the display origin.
        Segments never set a Text rotation, so the window extent is the
        unrotated box."""
        extent = mtext.Text.get_window_extent(self, renderer=renderer)
        return extent.width, extent.height

    def draw(self, renderer, *args, **kwargs) -> None:
        """Nothing. A segment draws only where its label tells it to
        (:meth:`_draw_at`); matplotlib's own ``Text.draw`` would draw the text
        at the display origin."""

    def _draw_at(self, renderer, place: _SegmentPlace) -> None:
        """Draw the segment's outline at ``place``, with the properties the
        label gave it for this draw (:meth:`CurvedText._pass_properties`)."""
        path = self._placed_path(renderer, place)
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
            gc.set_snap(self.get_snap())
            sketch = self.get_sketch_params()
            if sketch is not None:
                gc.set_sketch_params(*sketch)
            gc.set_url(self.get_url())
            face = mcolors.to_rgba(self.get_color(), self.get_alpha())
            renderer.open_group("curved_segment", self.get_gid())
            renderer.draw_path(gc, path, IdentityTransform(), face)
            renderer.close_group("curved_segment")
        finally:
            gc.restore()

    def _placed_path(self, renderer, place: _SegmentPlace) -> Path | None:
        """This segment's outline mapped onto the curve, in display pixels,
        for ``place``, a placement of the label made for this renderer (the
        frame holds pixels, so a place made for another renderer does not
        fit)."""
        frame, s_left, width_px, datum = place
        verts, codes = self._outline_units()
        if len(verts) == 0:
            return None
        size = self.get_fontproperties().get_size_in_points()
        em_px = renderer.points_to_pixels(size)
        px_per_unit = _px_per_unit(renderer, size)
        u = verts[:, 0] * px_per_unit
        v = (verts[:, 1] - datum) * px_per_unit
        if self._bend:
            # Bend each outline point through the frame: arc length advances with
            # ``u`` and the normal follows the local em-scale chord, so radicals
            # and fraction bars stay connected through curvature. Long straight
            # runs are pre-subdivided by ``_densify`` so they follow the curve.
            s = s_left + u
            x, y, _ = frame.points_and_angles(s)
            angle = frame.chord_angles(s - em_px / 2.0, em_px)
            placed = np.column_stack([x - v * np.sin(angle),
                                      y + v * np.cos(angle)])
        else:
            # Place the glyph rigidly: one rotation, by the chord across its own
            # width, about its center on the curve. A single isometry preserves
            # the glyph's shape (no distortion) while the baseline datum still
            # lands on the curve, so spacing and rotation match the bent runs.
            w = width_px
            cx, cy, _ = frame.points_and_angles(s_left + w / 2.0)
            angle = float(frame.chord_angles(s_left, w))
            cos, sin = np.cos(angle), np.sin(angle)
            u_centred = u - w / 2.0
            placed = np.column_stack([cx + u_centred * cos - v * sin,
                                      cy + u_centred * sin + v * cos])
        return Path(placed, codes)

    def _content_key(self) -> tuple:
        """What the segment's outline and size are built from: its text, font,
        and usetex setting."""
        return (self.get_text(), hash(self.get_fontproperties()),
                self.get_usetex())

    def _outline_units(self) -> tuple[np.ndarray, np.ndarray]:
        """Outline ``(vertices, codes)`` in 1/100-em layout units, baseline at
        ``v = 0`` and left edge at ``u = 0``, cached on the segment's content
        (:meth:`_content_key`)."""
        key = self._content_key()
        if self._outline_cache is None or self._outline_cache[0] != key:
            self._outline_cache = (key, self._build_outline(
                self.get_fontproperties(), self.get_text(), self.get_usetex()))
        return self._outline_cache[1]

    def _ink_band(self) -> tuple[float, float]:
        """The highest and lowest ink of the outline, in the same layout units,
        from the curves' true extents; ``(-inf, inf)`` for a blank segment. It
        is cached with the outline's content."""
        key = self._content_key()
        if self._band_cache is None or self._band_cache[0] != key:
            verts, codes = self._outline_units()
            if len(verts) == 0:
                band = (-np.inf, np.inf)
            else:
                box = Path(verts, codes).get_extents()
                band = (float(box.y1), float(box.y0))
            self._band_cache = (key, band)
        return self._band_cache[1]

    def _build_outline(self, prop: font_manager.FontProperties, text: str,
                       usetex: bool) -> tuple[np.ndarray, np.ndarray]:
        """Build the outline that :meth:`_outline_units` caches. Implemented by
        subclasses."""
        raise NotImplementedError


class _PlainGlyph(_OutlineSegment):
    """One plain character, drawn as a rigid (undistorted) glyph outline whose
    baseline lies on the curve. Inherits ``_bend = False`` from the base.

    Under usetex the glyph comes from its plain run, ``run_text``, typeset by
    one LaTeX pass (:func:`_tex_run_layout`), which also gives its width and
    TeX's kern toward the next character. ``index`` is the character's place in
    the run. When the run does not set one item per character, the glyph is
    typeset on its own instead, from its text, the character's literal TeX
    source (:func:`_tex_source`). That text is set once at construction, which
    is also when matplotlib fixes the artist's usetex setting."""

    def __init__(self, char: str, run_text: str, index: int, /,
                 **kwargs: Any) -> None:
        super().__init__(char, **kwargs)
        self._char = char
        self._run_text = run_text
        self._index = index
        if self.get_usetex():
            self.set_text(_tex_source(char))

    def _run_layout(self) -> _TexRunLayout | None:
        """This glyph's run typeset in one LaTeX pass, or None without usetex or
        when the run's characters are typeset one at a time."""
        if not self.get_usetex():
            return None
        return _tex_run_layout(self._run_text,
                               self.get_fontproperties().get_size_in_points())

    def _size_px(self, renderer) -> tuple[float, float]:
        run = self._run_layout()
        if run is None:
            return super()._size_px(renderer)
        size = self.get_fontproperties().get_size_in_points()
        px_per_unit = _px_per_unit(renderer, size)
        return (run.widths[self._index] * px_per_unit,
                run.heights[self._index] * px_per_unit)

    def _tex_kern_units(self) -> float:
        """TeX's kern from this glyph toward the next character of its run, in
        1/100-em layout units; zero when the run is typeset one character at a
        time."""
        run = self._run_layout()
        if run is None:
            return 0.0
        return run.spans[self._index] - run.widths[self._index]

    def _outline_units(self) -> tuple[np.ndarray, np.ndarray]:
        # A glyph from a run takes its outline from the run's cache, which
        # follows the TeX rcParams, so its outline and its width always come
        # from the same LaTeX pass.
        run = self._run_layout()
        if run is None:
            return super()._outline_units()
        return run.outlines[self._index]

    def _build_outline(self, prop: font_manager.FontProperties, text: str,
                       usetex: bool) -> tuple[np.ndarray, np.ndarray]:
        # Whitespace advances the cursor but draws nothing. Test the character,
        # not ``text``: under usetex a space's text is TeX source, not whitespace.
        if not self._char.strip():
            return np.empty((0, 2)), np.empty(0, dtype=Path.code_type)
        if usetex:
            converter = _tex_to_path(prop.get_size_in_points())
            verts, codes = converter.get_text_path(prop, text, ismath="TeX")
        else:
            converter = _text_to_path
            verts, codes = converter.get_text_path(prop, text, ismath=False)
        verts = np.asarray(verts, float) * _layout_units(converter)
        return verts, np.asarray(codes, dtype=Path.code_type)


class _MathRun(_OutlineSegment):
    """One ``$...$`` math run, laid out by mathtext or, under usetex, by LaTeX,
    and drawn by bending the expression's glyph outlines and rule boxes through
    the curve. Radicals, fractions, and sized delimiters stay joined because the
    path the label rides, rounded by ``min_radius``, has a radius larger than
    the height of the expression on the inside of every bend. Its baseline is the
    same shared datum as the plain glyphs, so the run's main symbols sit level
    with neighboring characters."""

    _bend = True

    def _build_outline(self, prop: font_manager.FontProperties, text: str,
                       usetex: bool) -> tuple[np.ndarray, np.ndarray]:
        # Lay out with the artist's own usetex setting, the one matplotlib
        # measures the advance with. Under usetex LaTeX runs at the label size
        # (see ``_tex_to_path``), and either way the output is brought to
        # 1/100-em layout units.
        if usetex:
            converter = _tex_to_path(prop.get_size_in_points())
            glyph_info, glyph_map, rects = converter.get_glyphs_tex(prop, text)
        else:
            converter = _text_to_path
            glyph_info, glyph_map, rects = converter.get_glyphs_mathtext(prop, text)
        units = _layout_units(converter)
        pieces = []
        for info in glyph_info:
            placed, codes = _place_glyph(glyph_map, *info)
            if len(placed) == 0:  # whitespace glyphs have no outline
                continue
            pieces.append(_densify(placed * units, codes))
        for rect_verts, rect_codes in rects:
            pieces.append(_densify(np.asarray(rect_verts, float) * units,
                                   np.asarray(rect_codes)))
        if not pieces:
            return np.empty((0, 2)), np.empty(0, dtype=Path.code_type)
        return (np.concatenate([p[0] for p in pieces]),
                np.concatenate([p[1] for p in pieces]))


class CurvedText(mtext.Text):
    """A string drawn along an (x, y) curve, one glyph at a time.

    Each character of ``text`` is drawn as a per-character glyph, and each
    ``$...$`` run as one math run. The label follows the curve through figure
    layout, resizing, and interactive panning and zooming, because its layout is
    computed again on every draw. Use :func:`curved_text` to add a label in one
    call. This class takes the axes after ``x, y, text``, as
    :class:`matplotlib.text.Text` does, where :func:`curved_text` takes it first.

    Parameters
    ----------
    x, y : array-like
        The curve in data coordinates: 1-D, equal length, and ordered along the
        curve. See Notes for gaps and units.
    text : str
        The string to draw, on one line. It may contain mathtext runs
        (``$...$``).
    axes : matplotlib.axes.Axes
        The axes to draw into. It follows ``x, y, text`` here and comes first
        in :func:`curved_text`.
    pos : float, default 0.5
        Where the label is anchored, as a fraction of the drawn arc length of
        the curve: ``0.0`` is the start of the drawn curve and ``1.0`` its end.
        A value outside 0 to 1 places the anchor on the straight extension
        beyond either end of the curve. A value far outside can fall outside
        the figure. Pass ``clip_on=False`` to see an anchor outside the axes.
        On a curve with gaps, the fraction is measured on screen along the drawn
        stretches (connected pieces of the curve between gaps). Zooming can move
        the anchor onto another stretch, and the label follows the stretch that
        holds its anchor. The label reads in the order of the points as they
        appear on screen. If the points run from right to left, the text is
        upside down unless ``upright`` is set. ``pos`` counts from the first
        point.
    anchor : {"start", "center", "end"}, default "center"
        Which part of the label sits at ``pos``.
    offset : float, default 0.0
        Distance from the curve, perpendicular to it, in points (1/72 inch).
        Positive is to the left of the direction of travel, which is above a
        curve that runs from left to right. On a label turned over by
        ``upright``, positive is toward the tops of the letters. The label is
        laid along the parallel (offset) curve at that distance. The clearance
        from the curve and the spacing of the characters stay even where the
        curve bends steeply or asymmetrically. ``pos`` and ``anchor`` are
        measured against the original curve and carried perpendicularly onto
        the offset curve.
    box : bool, str, or dict, default False
        A casing drawn behind the label to clear the lines it crosses: a band
        that follows the curve at the label's height, under the glyphs. ``True``
        draws a white band; a color string sets its color; a dict accepts
        ``color``, ``pad`` (band height relative to the tallest glyph, default
        ``1.1``), and ``alpha``. The band has rounded ends, so it extends about
        half its height past the first and last glyph. For a lighter casing
        around each glyph (a halo), pass a white ``withStroke`` through
        ``path_effects``. A wide stroke merges adjacent glyphs, so ``box`` gives
        solid coverage under plain text.
    crowding : {"none", "curvature"}, default "none"
        How to space glyphs around bends. ``"none"`` spaces them as ordinary
        text does, by width and kerning (the adjustment of the space between
        particular pairs of characters). On the concave side of a tight bend
        the rotated glyphs can overlap. ``"curvature"`` opens an even gap,
        added space between every pair of characters, that grows with the local
        curvature and the glyph height, so the inside edges stop colliding. A
        deadband (a range below which no gap is added) leaves gentle bends and
        straight runs unchanged.
    valign : {"center", "baseline", "ascender", "descender"}, default "center"
        Which line of the text lies on the curve. ``"center"`` straddles the
        text on the curve. ``"baseline"`` places the text baseline on the curve,
        so the body sits above it and descenders below. ``"ascender"`` and
        ``"descender"`` place the ascender or descender line on it. Each choice
        is one font-metric shift applied identically to every glyph and math run,
        so plain text and math stay aligned. Combine it with ``offset`` to lift
        the chosen line off the curve.
    upright : bool, default False
        Keep the text from reading upside down. Each draw, the label is turned
        over when the straight line across the stretch of curve it covers points
        left on screen, or straight down, so it reads left to right or from
        bottom to top. The label keeps its place on the curve: ``pos`` and
        ``anchor`` still refer to the curve as given, so the label covers the
        same stretch of it. An inverted axis or a change of the view is followed
        on the next draw. The decision is for the whole label, so a label that
        winds around, as along a spiral, reads upside down where it turns. A
        label whose chord is near the vertical can turn over when the view
        changes.
    min_radius : {"auto"}, None, or float, default "auto"
        The least radius of curvature, in points, of the path the label rides.
        On the inside of a bend tighter than the label's ink, the ink would
        fold over itself, and an ``offset`` toward the inside of a bend larger
        than the bend's radius would lay the label along a path that doubles
        back. The label rides a rounded copy of the curve instead: a ball of
        the least radius is rolled along each side of the curve, and where the
        curve bends more tightly than the ball, the ball's arc replaces the
        curve. A bend gentler than the ball is left exactly as it is.

        ``"auto"`` takes, for each side of the path, 1.5 times the height of
        the label's ink on that side: the ink above the path is on the inside
        of a left bend, and the ink below it is on the inside of a right bend.
        A number sets the radius, in points, for both sides. ``None`` or ``0``
        turns the rounding off. The rounding is worked out on every draw, and
        it combines with ``crowding`` and ``offset``.

        At a tight bend the label leaves the curve by at most the least radius
        less the curve's own radius. Two kinds of curve are outside the
        guarantee, and the label can fold there, as with ``None`` or, near a
        narrow hairpin, more: a hairpin whose arms are less than about 20
        degrees apart (more for a larger label), where the ball fits only
        beyond the reach of the ball test (about six radii of arc length), and
        a jagged curve that changes direction at the scale of the label's ink,
        such as noisy data plotted point by point. Pass a smoothed curve for
        such data, or ask for ``smooth``.
    smooth : {"auto"}, None, or float, default None
        The width, in points of arc length, over which the path the label rides
        is smoothed; the line itself is not changed. A line of measured data
        wiggles at about the width of a glyph, which tilts neighboring glyphs
        by different amounts and steps them up and down. The path is smoothed
        by a Gaussian of this standard deviation, corrected so that a smooth
        bend keeps its shape, and the label rides the result. The smoothing is
        worked out on every draw, in display space, and it comes before the
        rounding of ``min_radius`` and the offset.

        ``None`` or ``0`` turns the smoothing off. A number smooths by that
        width wherever the label is, so it rounds any bend narrower than the
        width, and it is the choice for raw, unaveraged data. ``"auto"`` takes
        three quarters of an em, the font size, and smooths only where the path
        wiggles under the label: where the chords across half an em, laid end
        to end along the label, turn one way and then the other at least twice.
        A curve that turns the same way all through the label, a tight bend
        included, is drawn as without smoothing; a serpentine that alternates
        twice or more under the label is smoothed. The test is a heuristic,
        tuned on real monthly prices, and it switches on and off as ``pos`` or
        the view changes: give a number for a steady result.

        The label rides the smoothed path, not the line, so a line that wiggles
        by more than the label's ``offset`` can touch the letters. Use an
        offset larger than the wiggles.
    **kwargs
        Extra keyword arguments are :class:`~matplotlib.text.Text` properties.
        The font ones, ``fontsize``, ``fontfamily``, ``fontproperties``,
        ``fontstyle``, ``fontweight``, ``math_fontfamily``, ``parse_math``, and
        ``usetex``, apply to every glyph and every math run when the label is
        made. ``color``, ``alpha``, ``path_effects``, ``snap``,
        ``sketch_params``, ``url``, ``gid``, and the clipping properties belong
        to the label and pass to its glyphs at every draw, so their setters act
        after construction too. The color, alpha, and path effects do not pass
        to the ``box`` casing, which has its own color and alpha. Properties
        that describe one text box have no effect, because the curve places
        every glyph: ``ha``, ``va``, ``rotation_mode``, ``wrap``, ``bbox``,
        ``linespacing``, ``multialignment``, and ``backgroundcolor``.
        ``antialiased`` is accepted and has no effect. ``label=`` adds no
        legend entry, and ``legend()`` warns once that it has no handle for the
        label. ``transform`` is replaced, because glyphs are drawn in display
        pixels. A ``gid`` of
        ``"lab"`` becomes ``"lab-0"``, ``"lab-1"``, and so on, numbered in
        order along the label, one number for each character and one for each
        math run (a space takes a number and draws nothing), so a saved SVG
        has each id once. Select the parts by prefix, for example
        ``[id^=lab-]``. ``rotation`` raises ``ValueError``, because the curve
        sets each glyph's angle. Use ``box`` for a background. An unknown
        property raises ``AttributeError``.

        ``parse_math=False`` treats dollar signs literally (the default comes
        from the ``text.parse_math`` rcParam, a matplotlib runtime setting).
        ``clip_on`` (default ``True``) clips the label at the edge of the axes;
        ``clip_on=False`` lets it extend beyond them.

    Raises
    ------
    ValueError
        If any of these holds:

        - ``x`` and ``y`` are not 1-D arrays of equal length with at least two
          points.
        - ``x`` and ``y`` have no two consecutive finite points.
        - ``pos`` is not finite.
        - ``anchor``, ``valign``, or ``crowding`` is not one of the listed
          values.
        - A ``box`` dict has a key other than ``color``, ``pad``, and ``alpha``.
        - ``rotation`` is passed, because the curve sets each glyph's angle.
        - ``min_radius`` or ``smooth`` is a string other than ``"auto"``, or is
          negative, infinite, or NaN.
    TypeError
        If ``text`` is not a string, ``pos`` is not a number, ``upright`` is
        not a bool (``1`` and ``0`` are not accepted), ``min_radius`` or
        ``smooth`` is not ``None``, ``"auto"``, or a number (a bool is not
        accepted), or ``axes`` is a 3D axes.
    matplotlib.units.ConversionError
        If the axes cannot convert the data of ``x`` or ``y``.
    AttributeError
        If a keyword argument is not a property of ``Text``.

    Notes
    -----
    Each glyph is laid out on one shared text baseline and mapped onto the curve
    from its outline. A plain character is placed rigidly, with one rotation by
    the chord across its own width, so its shape is undistorted. A math run is
    bent along the curve, so radicals (square-root signs) and fractions stay
    connected. Because both kinds share the baseline, plain text and math sit
    level, and no glyph steps up or down against its neighbors. The rotation
    chord follows the local tangent but averages over the glyph's own width, so
    rotation stays smooth across the vertices of a coarsely sampled curve.

    **Gaps and units.** A NaN (not a number), infinite, or masked point (a point
    hidden by a NumPy masked array) leaves a gap, as in ``plot``. The curve
    needs at least two consecutive finite points. A value outside the domain of
    a log or logit axis leaves a gap too. On a log axis these are values of 0 or
    below; on a logit axis, values of 0 or below and of 1 or above. A stretch
    is a connected piece of the curve between gaps. Any type the axes' unit
    converters accept works, as for ``plot``: dates (``datetime64``,
    ``datetime``, pandas dates), category strings, and unit-aware values. An
    axis without units takes them from the curve. Category strings
    not yet on an axis are added to it, as ticks.

    A label that overruns either end of the curve, or of the stretch it follows
    on a curve with gaps, is not clipped. The glyphs beyond the end are placed on
    a straight extension of the end tangent, over a gap if there is one, and the
    label never continues onto another stretch. To run a label along scattered
    points or a curve with gaps, pass a smooth curve that follows their overall
    shape, such as a fit. The label never draws the curve it follows.

    **Mathtext.** Each ``$...$`` run is laid out by matplotlib's mathtext
    engine. Every glyph outline and every bar, such as a fraction bar, is mapped
    onto the curve by arc length. The run sits on the same baseline as the
    surrounding plain glyphs. Fractions, radicals, and large brackets stay
    joined, because the label rides a path whose radius is at least 1.5 times
    the height of its ink on the inside of a bend (``min_radius``). Where the
    path bends toward the expression, its inside edge is squeezed along the
    curve, to a third of its natural length at the tightest bend the path
    allows. A curve that bends more tightly is rounded: the label leaves it to
    ride the rounded path, so the expression does not fold over itself.

    **LaTeX typesetting (usetex).** When ``text.usetex`` is set or
    ``usetex=True`` is passed, LaTeX (a typesetting system) typesets the label,
    so it matches the other usetex text of the figure. ``curved_text`` requires
    ``latex``, as for any matplotlib usetex figure. matplotlib's own usetex
    text, such as tick labels, also needs ``dvipng``. The usetex setting is
    fixed when the label is created. Set the LaTeX preamble, font family, and
    font lists before the figure is first drawn. Math runs are passed to LaTeX
    as written, so they can run TeX commands, including ones that read local
    files. Do not pass untrusted text with usetex on. See
    `LaTeX typesetting (usetex)
    <https://thiebes.github.io/curved-text/usetex.html>`_ for plain text, Greek
    letters, the preamble, caching, and ``valign``.

    Glyphs are rendered from their outlines, not as hinted ``Text`` artists. On
    a rotated label this lets one baseline be pinned exactly, at the cost of
    pixel-grid hinting, which matters little on rotated text. Plain text and
    mathtext are rendered the same way. Under usetex, matplotlib loads the glyphs
    with light hinting, laid out at a resolution where it is negligible.

    **Limits.**

    - Vector output: in PDF, SVG, PostScript, and EPS output, each character is
      drawn as an outline path, not as text. The label cannot be selected,
      searched, or edited as text, and each character is a separate shape. In PNG
      output the label looks as it does on screen.
    - Axes: Cartesian and polar axes work. On polar axes the angle runs
      counterclockwise, so a curve from angle 0 to π runs right to left over
      the top and its label reads upside down unless ``upright`` is set. A 3D axes
      raises ``TypeError``.
    - Animation: ``animated=True`` and ``ax.draw_artist(label)`` work, so a
      label can be blitted. The label draws its casing and its glyphs itself,
      so a blitting loop that draws the label draws all of it.
    - One artist: the label is the only artist the axes holds, so ``ax.texts``
      lists the label, not its characters. Its parts have no zorder of their
      own: the casing and then the glyphs draw at the label's zorder.
    - After creation: ``set_visible``, ``set_zorder``, ``set_animated``,
      ``set_alpha``, ``set_color``, ``set_path_effects``, ``set_gid``,
      ``set_url``, ``set_rasterized``, ``set_snap``, ``set_sketch_params``, and
      the clipping setters act on what is drawn. The text, the font, the curve,
      and the placement arguments are fixed when the label is made: remove the
      label and make a new one to change them.
    - Lifecycle: ``label.remove()`` removes the label. ``ax.clear()`` removes it
      with the other artists. A figure that holds a label can be pickled.
      ``legend(loc="best")`` avoids the label from matplotlib 3.9.
    - ``pos``: ``pos`` is a fraction of the curve you pass in, including any
      part outside the axes limits: pass the visible piece of the curve. A value
      outside 0 to 1 places the anchor on the straight extension beyond an end;
      a value far outside can place it outside the figure. Use ``clip_on=False``
      to see an anchor outside the axes.
    - Axis limits: the label does not change the data limits. Plot the curve
      first, or set the limits yourself.
    - Cost: the time of a draw grows with the number of characters and the
      number of curve points, and is paid on every redraw. If interactive pan and
      zoom feels slow, pass fewer points: decimate or smooth the curve. Dozens
      of labels draw in well under a second.
    - Text: one line. A newline in the string is not a line break.

    **After creation.** :func:`curved_text` and :class:`CurvedText` take the
    same arguments and make the same artist. Keep the returned object to hide it
    (``set_visible``), restack it (``set_zorder``), change its clipping, or
    remove it (``remove()``). To change the text, color, size, or curve, remove
    the label and make a new one. ``get_text()`` does not return the label's
    string.
    """

    def __init__(self, x: ArrayLike | Sequence[Any], y: ArrayLike | Sequence[Any],
                 text: str, axes: Axes, *,
                 pos: float = 0.5, anchor: str = "center", offset: float = 0.0,
                 box: bool | str | dict = False, crowding: str = "none",
                 valign: str = "center", upright: bool = False,
                 min_radius: float | str | None = "auto",
                 smooth: float | str | None = None,
                 **kwargs: Any) -> None:
        # With the other argument checks, before the label is added, so a
        # non-string raises here and leaves the axes unchanged.
        if not isinstance(text, str):
            raise TypeError(f"text must be a str, got {type(text).__name__!r}")
        if not math.isfinite(pos):
            raise ValueError(f"pos must be finite, got {pos!r}")
        if anchor not in _ANCHORS:
            raise ValueError(f"anchor must be one of {_ANCHORS}, got {anchor!r}")
        if crowding not in _CROWDING:
            raise ValueError(
                f"crowding must be one of {_CROWDING}, got {crowding!r}")
        if valign not in _VALIGN:
            raise ValueError(f"valign must be one of {_VALIGN}, got {valign!r}")
        if not isinstance(upright, (bool, np.bool_)):
            raise TypeError(f"upright must be a bool, got {upright!r}")
        min_radius = _checked_length("min_radius", min_radius)
        smooth = _checked_length("smooth", smooth)
        # A 3D axes has no single display-space path before its projection,
        # so a label there would draw nothing.
        if getattr(axes, "name", None) == "3d":
            raise TypeError(
                f"curved_text does not support 3D axes, got {type(axes).__name__}")
        # The curve places every glyph, and each glyph's own rotation widens
        # its box, so the characters spread apart.
        if "rotation" in kwargs:
            raise ValueError(
                "rotation is not supported: the curve sets each glyph's angle")
        # Optional casing behind the label: a fat line following the curve at
        # the label's height. It is built before the label touches the axes, so
        # a ``box`` it cannot draw raises with the axes as they were. The label
        # sets its geometry and draws it before the glyphs, in ``draw``.
        box_config = _box_config(box)
        box_pad = 1.1
        box_line: mlines.Line2D | None = None
        if box_config is not None:
            box_pad = box_config["pad"]
            box_line = mlines.Line2D([], [], color=box_config["color"],
                                     alpha=box_config["alpha"],
                                     solid_capstyle="round",
                                     solid_joinstyle="round")
        # The curve may hold any type the axes' unit converters accept (dates,
        # categories, unit-aware arrays), as ``plot`` does. An axis without a
        # converter takes one from the curve, as ``plot`` sets one up; an axis
        # that has one keeps it, so data it cannot convert raises here instead
        # of replacing the converter the axes' other artists use. Each axis is
        # set up and converted before the next, so data the x axis rejects
        # leaves the y axis alone.
        # The label converts its own copy: floats pass through conversion as
        # they are, so the converted curve would share the caller's array.
        curve = (copy.copy(x), copy.copy(y))
        converted = []
        for axis, values in zip((axes.xaxis, axes.yaxis), curve):
            if not axis.have_units():
                axis.update_units(values)
            converted.append(_axis_floats(axis, values))
        xf, yf = converted
        # Validate the converted curve; the label keeps the values as given.
        if xf.ndim != 1 or xf.shape != yf.shape or xf.size < 2:
            raise ValueError("x and y must be 1-D arrays of equal length >= 2")
        # A NaN, infinite, or masked point leaves a gap, as in ``plot``; the
        # curve needs one stretch a line would draw, two consecutive finite
        # points.
        finite = np.isfinite(xf) & np.isfinite(yf)
        if not (finite[:-1] & finite[1:]).any():
            raise ValueError(
                "x and y must contain at least two consecutive finite points")
        # The container's position is the curve's first finite point as the
        # caller gave it, so ``get_position`` returns the caller's type, as for
        # any Text, and ``get_unitless_position`` the point on the axes.
        first = int(np.argmax(finite))
        super().__init__(_at_position(x, first), _at_position(y, first), " ",
                         **kwargs)
        self._cx, self._cy = curve
        # The converted curve, kept until either axis's units change, as
        # matplotlib's lines keep theirs: converting a long curve of datetime
        # objects on every measurement would slow each draw (``_curve_px``).
        self._curve_floats: tuple[np.ndarray, np.ndarray] | None = (xf, yf)
        # Each axis's callback registry and the id of the label's ``"units"``
        # callback in it (``_follow_axis_units``), to disconnect on removal.
        self._unit_callbacks: list[tuple[CallbackRegistry, int]] = []
        self._pos = float(pos)
        self._anchor = anchor
        self._offset = float(offset)
        self._crowding = crowding
        self._valign = valign
        self._upright = bool(upright)
        self._min_radius = min_radius
        self._smooth = smooth
        axes.add_artist(self)
        # The converted curve is already kept, so the label must hear of a
        # change of units from now on, before its first placement too.
        self._follow_axis_units()
        self._box_pad = box_pad
        self._box: mlines.Line2D | None = box_line
        if self._box is not None:
            self._box.set_transform(axes.transData)
        # The placement of the last measurement or draw, the key it was made
        # for (``_placement_key``), and the extent and glyph boxes measured from
        # it. A measurement reuses the placement while its key is unchanged. The
        # segments draw from the placement the last draw gave them, not from
        # this one, so a measurement never changes what is drawn.
        self._placement: _Placement | None = None
        self._placed_key: tuple | None = None
        self._extent_cache: Bbox | None = None
        self._glyph_box_cache: tuple[Bbox, ...] | None = None
        self._segments: list[_OutlineSegment] = []
        runs = (_split_runs(text) if self.get_parse_math()
                else [_Run(False, text)])
        # Two keywords reach the label only. ``visible``: matplotlib measures
        # a hidden text as an empty box, so a segment made hidden would be
        # sized wrongly the first time the label is shown. ``rasterized``:
        # matplotlib warns for each text that is rasterized but does not draw
        # itself through ``allow_rasterization``, as a segment does not; the
        # label rasterizes its parts as one. The other keywords the label owns
        # (color, alpha, clipping, and so on) are set on the segments at every
        # draw.
        segment_kwargs = {key: value for key, value in kwargs.items()
                          if key not in _LABEL_ONLY_KEYWORDS}
        for run in runs:
            if run.is_math:
                self._segments.append(_MathRun(run.text, **segment_kwargs))
                continue
            for index, ch in enumerate(run.text):
                self._segments.append(
                    _PlainGlyph(ch, run.text, index, **segment_kwargs))
        # The parts belong to the label, not to the axes, so the axes never
        # draws or measures one; each needs the figure to measure its text.
        for part in self._parts():
            part.set_figure(self.figure)

    def set_figure(self, fig) -> None:
        super().set_figure(fig)
        for part in self._parts():
            part.set_figure(fig)

    def _parts(self) -> list[martist.Artist]:
        """The artists the label draws: its segments and its casing. Setters
        may run during base-class construction, before they exist."""
        parts: list[martist.Artist] = list(getattr(self, "_segments", ()))
        box = getattr(self, "_box", None)
        if box is not None:
            parts.append(box)
        return parts

    def remove(self) -> None:
        # The parts belong to the label and the axes holds only the label, so
        # removing the label removes them too.
        # The axes' unit callbacks hold the label only weakly, but a removed
        # label should not be told about units it no longer follows. Each is
        # disconnected from the registry it was connected to: clearing the
        # axes replaces the registries, whose new ids start again at 0 and so
        # can name another label's callback.
        for registry, cid in self._unit_callbacks:
            registry.disconnect(cid)
        self._unit_callbacks = []
        super().remove()

    def __getstate__(self) -> dict:
        # A pickled axes drops the label's unit callbacks, which are not
        # picklable, so the unpickled label converts its curve afresh and
        # connects them again when it is next placed (``_curve_px``).
        state = super().__getstate__()
        assert isinstance(state, dict)
        state["_curve_floats"] = None
        state["_unit_callbacks"] = []
        return state

    def _kerns_px(self, renderer) -> list[float]:
        """The kern from each segment toward the next, in display pixels.

        Between two consecutive plain glyphs it is the kern the text's own
        layout applies to the pair, so pairs such as "AV" and "To" sit as
        tightly as in ordinary text: matplotlib's (:func:`_kern_units`), or
        under usetex TeX's, from the glyph's run (:meth:`_PlainGlyph._tex_kern_units`).
        Next to a math run, and at the end of the label, it is zero.
        """
        kerns = [0.0] * len(self._segments)
        for i, (left, right) in enumerate(zip(self._segments,
                                              self._segments[1:])):
            if isinstance(left, _PlainGlyph) and isinstance(right, _PlainGlyph):
                prop = left.get_fontproperties()
                px_per_unit = _px_per_unit(renderer, prop.get_size_in_points())
                if left.get_usetex():
                    kern = left._tex_kern_units()
                else:
                    kern = _kern_units(prop, left._char, right._char)
                kerns[i] = kern * px_per_unit
        return kerns

    def _advances(self, frame: _CurveFrame, spans: list[float],
                  heights: list[float], flat_start: float) -> list[float]:
        """Arc-length advance for each segment along ``frame``.

        In the default ``"none"`` mode the advance is the segment's flat span
        (its width plus its kern toward the next glyph), with no widening. In
        ``"curvature"`` mode each advance is widened where the curve bends, to
        keep the concave edges of adjacent rigid glyph boxes from overlapping on
        the inside of the bend. A box of height ``h``
        whose center lies on a curve of local curvature ``kappa`` has its concave
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
        the curvature is uniform. Each span sits in the middle of its widened
        slot, so the gap is split evenly around it. The curvature is sampled
        along the un-widened layout starting at ``flat_start``.
        """
        if self._crowding == "none":
            return list(spans)
        advances = []
        cursor = flat_start
        for span, h in zip(spans, heights):
            kappa = float(frame.curvature(cursor, span))
            crowd = min(abs(kappa) * h / 2.0, _MAX_CROWD)
            advances.append(span + max(0.0, crowd - _CROWD_SLACK) * h)
            cursor += span
        return advances

    @martist.allow_rasterization
    def draw(self, renderer, *args, **kwargs) -> None:
        # The label draws its own parts, as matplotlib's composite artists do:
        # it places them afresh for this renderer, so a changed label is
        # measured afresh too, and draws the casing and then the glyphs at the
        # places it just made. Nothing a measurement did reaches here, because
        # the parts keep no placement. Its own properties apply to every part
        # as they stand at this draw, so a setter called after construction
        # reaches what is drawn. A hidden label, and one that cannot be placed,
        # draws nothing.
        if not self.get_visible():
            self.stale = False
            return
        placement = self._place(renderer)
        if placement is None:
            self.stale = False
            return
        gid = self.get_gid()
        for number, segment in enumerate(self._segments):
            self._pass_properties(segment)
            # Each segment draws in its own SVG group, and an id must be unique
            # in the file, so the label's gid takes the segment's number. An
            # empty gid names nothing, so it is passed on as it is.
            segment.set_gid(f"{gid}-{number}" if gid else gid)
        if self._box is not None and placement.box is not None:
            self._draw_box(renderer, placement.box)
        for segment, place in zip(self._segments, placement.segments):
            segment._draw_at(renderer, place)
        self.stale = False

    def _pass_common(self, part: martist.Artist) -> None:
        """Give ``part``, a segment or the casing, the label's URL, snap
        setting, sketch parameters, and clipping for this draw."""
        part.set_url(self.get_url())
        part.set_snap(self.get_snap())
        sketch = self.get_sketch_params()
        part.set_sketch_params(*(sketch if sketch is not None else (None,)))
        part.set_clip_on(self.get_clip_on())
        part.set_clip_box(self.get_clip_box())
        part.set_clip_path(self.get_clip_path())

    def _pass_properties(self, segment: _OutlineSegment) -> None:
        """Give ``segment`` the label's own properties for this draw: the ones
        a part cannot hold apart from the label, because the label is the
        artist the axes and the caller know. The font stays with the segment,
        which builds its outline from it."""
        segment.set_color(self.get_color())
        segment.set_alpha(self.get_alpha())
        segment.set_path_effects(self.get_path_effects())
        self._pass_common(segment)

    def _draw_box(self, renderer, box: _BoxPlace) -> None:
        """Draw the casing for ``box``. It takes the label's URL, snap setting,
        sketch parameters, and clipping, like a glyph; its color, alpha, and
        width are its own (the ``box`` argument), and a path effect, which
        would outline the glyphs, is not applied to it."""
        casing = self._box
        axes = self.axes
        assert casing is not None and axes is not None
        xy = axes.transData.inverted().transform(box.xy_px)
        casing.set_data(xy[:, 0], xy[:, 1])
        casing.set_linewidth(box.linewidth)
        self._pass_common(casing)
        casing.draw(renderer)

    def get_window_extent(self, renderer=None, dpi=None) -> Bbox:
        """The extent of the label as drawn, in display pixels: its glyphs and
        its box casing.

        Figure layout (``bbox_inches="tight"``, constrained layout, and from
        matplotlib 3.9 ``legend(loc="best")``) measures the label through it.
        The label is placed on the curve to be measured, even before its first
        draw. The container's own Text takes no part. Each glyph counts by the
        box of its outline's control points. The box can exceed the ink by a
        fraction of a pixel and never falls short of it. The casing counts by
        its band, half its line width beyond its centerline on every side.

        Without a renderer, the label is measured at the figure's dpi (dots per
        inch). ``dpi`` scales the extent to that resolution. A hidden label has
        an empty extent at the curve's first shown point. So has a label that
        cannot be placed: an empty label, a label off any axes, a curve with no
        stretch left to draw, or a degenerate curve.

        Repeated measurements reuse the last placement while the renderer, the
        curve position, and the glyphs are unchanged.
        """
        if not self.get_visible():
            return self._empty_extent()
        if renderer is None:
            renderer = _measuring_renderer(self.figure)
        extent = self._measured_extent(renderer)
        if dpi is None:
            return extent.frozen()
        return Bbox(extent.get_points() * (dpi / self.figure.dpi))

    def contains(self, mouseevent) -> tuple[bool, dict]:
        """Whether ``mouseevent`` falls on the label: within the box of one of
        its placed glyphs, as matplotlib's own text tests its box. Picking
        (``picker``) and hover use it; the casing's band between glyphs is not
        a hit."""
        if (not self.get_visible() or self.figure is None
                or mouseevent.canvas is not self.figure.canvas):
            return False, {}
        renderer = _measuring_renderer(self.figure)
        self._place_if_stale(renderer)
        hit = any(box.contains(mouseevent.x, mouseevent.y)
                  for box in self._glyph_boxes(renderer))
        return hit, {}

    def _measured_extent(self, renderer) -> Bbox:
        """The label's extent for ``renderer``, placing the label first when
        its last placement no longer holds (:meth:`_place_if_stale`)."""
        self._place_if_stale(renderer)
        return self._label_extent(renderer)

    def _place_if_stale(self, renderer) -> _Placement | None:
        """The placement for ``renderer``: the last one if it was for the same
        renderer, curve position, and glyphs (:meth:`_placement_key`), else a
        new one."""
        curve_px = self._curve_px()
        key = self._placement_key(renderer, curve_px)
        if key != self._placed_key:
            self._place(renderer, curve_px, key)
        return self._placement

    def _place(self, renderer, curve_px: np.ndarray | None = None,
               key: tuple | None = None) -> _Placement | None:
        """Place the label for ``renderer`` (:meth:`_place_on_curve`), keep the
        placement with its key, which voids what was measured from the last,
        and return it. The segments are not touched: a draw gives them their
        places."""
        if curve_px is None:
            curve_px = self._curve_px()
        if key is None:
            key = self._placement_key(renderer, curve_px)
        self._placement = self._place_on_curve(renderer, curve_px)
        self._placed_key = key
        self._extent_cache = None
        self._glyph_box_cache = None
        return self._placement

    def _curve_px(self) -> np.ndarray | None:
        """The curve's points in display pixels, or None off any axes.

        The points are converted by the axes' units here, where drawing,
        measuring, and picking all place the label, so each follows the axes'
        current units. The conversion is kept until either axis's units change
        (:meth:`_forget_curve_floats`). Values outside a log or logit axis's
        domain leave gaps, checked against the axes' current scales each time,
        since a scale can change after the label is made."""
        axes = self.axes
        if axes is None:
            return None
        self._follow_axis_units()
        if self._curve_floats is None:
            self._curve_floats = (_axis_floats(axes.xaxis, self._cx),
                                  _axis_floats(axes.yaxis, self._cy))
        x, y = self._curve_floats
        return axes.transData.transform(np.column_stack(
            [_gaps_outside_domain(axes.get_xscale(), x),
             _gaps_outside_domain(axes.get_yscale(), y)]))

    def _follow_axis_units(self) -> None:
        """Have each axis tell the label when its units change, unless it
        already does or the label is off any axes."""
        if self.axes is None or self._unit_callbacks:
            return
        self._unit_callbacks = [
            (axis.callbacks,
             axis.callbacks.connect("units", self._forget_curve_floats))
            for axis in (self.axes.xaxis, self.axes.yaxis)]

    def _forget_curve_floats(self) -> None:
        """Convert the curve again at the next placement: an axis's units
        changed (its ``"units"`` callback, which also makes the axes'
        lines convert their data again)."""
        self._curve_floats = None

    def _placement_key(self, renderer, curve_px: np.ndarray | None) -> tuple:
        """What a placement depends on: the renderer, its resolution, where
        the curve lands on the canvas (which follows the axes' limits, scales,
        and position), and each segment's text, font, and usetex setting."""
        return (type(renderer), id(renderer), renderer.points_to_pixels(1.0),
                None if curve_px is None else curve_px.tobytes(),
                tuple(seg._content_key() for seg in self._segments))

    def _label_extent(self, renderer) -> Bbox:
        """The box of the placed glyphs' control points and of the casing's
        centerline points, padded by half its width, or an empty box at the
        curve's first shown point when the label could not be placed; kept
        until the label is placed again."""
        if self._extent_cache is None:
            glyph_boxes = self._glyph_boxes(renderer)
            if not glyph_boxes:
                self._extent_cache = self._empty_extent()
            else:
                bands = []
                box = self._placement.box if self._placement else None
                if self._box is not None and box is not None:
                    half_width = (renderer.points_to_pixels(box.linewidth)
                                  / 2)
                    bands.append(Bbox([box.xy_px.min(axis=0),
                                       box.xy_px.max(axis=0)])
                                 .padded(half_width))
                self._extent_cache = Bbox.union([*glyph_boxes, *bands])
        return self._extent_cache

    def _glyph_boxes(self, renderer) -> tuple[Bbox, ...]:
        """The box of each placed glyph's outline control points, in display
        pixels, kept until the label is placed again; none when the label
        could not be placed."""
        if self._glyph_box_cache is None:
            boxes = []
            if self._placement is not None:
                for seg, place in zip(self._segments, self._placement.segments):
                    path = seg._placed_path(renderer, place)
                    if path is not None:
                        vertices = np.asarray(path.vertices)
                        if path.codes is not None:
                            drawn = np.asarray(path.codes) != Path.CLOSEPOLY
                            vertices = vertices[drawn]
                        boxes.append(Bbox([vertices.min(axis=0),
                                           vertices.max(axis=0)]))
            self._glyph_box_cache = tuple(boxes)
        return self._glyph_box_cache

    def _empty_extent(self) -> Bbox:
        """An empty box at the curve's first shown point, which is the
        label's own position unless the axes' scale masks it. Off any axes, or
        when the axes show no point of the curve, the box sits at the label's
        own position; when the axes do not show that position either, it is a
        NaN box, as matplotlib's own text gives at a position without a pixel,
        and figure layout leaves it out."""
        curve_px = self._curve_px()
        if curve_px is not None:
            shown = curve_px[_shown(curve_px)]
            if len(shown):
                return Bbox.from_bounds(shown[0, 0], shown[0, 1], 0.0, 0.0)
        position = np.array(self.get_unitless_position(), dtype=float)
        if self.axes is not None:
            position = np.array([
                _gaps_outside_domain(scale, value[None])[0]
                for scale, value in zip(
                    (self.axes.get_xscale(), self.axes.get_yscale()),
                    position)])
        x, y = self.get_transform().transform(position)
        return Bbox.from_bounds(x, y, 0.0, 0.0)

    def _smooth_px(self, renderer) -> float:
        """The standard deviation, in display pixels, of the smoothing of the
        path the label rides; 0 without smoothing."""
        if self._smooth is None:
            return 0.0
        if self._smooth == "auto":
            size = (self._segments[0].get_fontproperties()
                    .get_size_in_points())
            return _SMOOTH_AUTO_EM * renderer.points_to_pixels(size)
        return self._smooth * renderer.points_to_pixels(1.0)

    def _ride_radii(self, renderer, datum: float) -> tuple[float, float]:
        """The least radius, in display pixels, of the path the label rides
        where it bends left and where it bends right; ``(0, 0)`` without
        rounding. Ink above the path (toward the left of the direction of
        travel) is on the inside of a left bend, so a left bend needs the
        radius of the ink's height above the path, and a right bend that of its
        depth below it."""
        if self._min_radius is None:
            return 0.0, 0.0
        if self._min_radius != "auto":
            radius = self._min_radius * renderer.points_to_pixels(1.0)
            return radius, radius
        px_per_unit = _px_per_unit(
            renderer, self._segments[0].get_fontproperties()
            .get_size_in_points())
        top = bottom = 0.0
        for segment in self._segments:
            highest, lowest = segment._ink_band()
            top = max(top, (highest - datum) * px_per_unit)
            bottom = max(bottom, (datum - lowest) * px_per_unit)
        return _MIN_RADIUS_CLEARANCE * top, _MIN_RADIUS_CLEARANCE * bottom

    @staticmethod
    def _round_curve(base: _CurveFrame, s_anchor: float, lead: float,
                     length: float, ride: tuple[float, float],
                     offset_px: float, origin: float = 0.0
                     ) -> tuple[_CurveFrame, _CurveFrame, float] | None:
        """The part of ``base`` the label can reach, rounded so that the path
        it rides, ``base`` shifted by ``offset_px``, has at least the radii in
        ``ride`` on its left and right bends. Returns the part as sampled, the
        part as rounded (the same vertices), and the anchor's arc length on
        the sampled part, or None where the curve needs no rounding.

        The ridden path at distance ``d`` to the left of a curve of radius
        ``r`` has radius ``r - d`` on a left bend and ``r + d`` on a right
        bend, so the radii asked of ``base`` are adjusted by the offset. The
        part reaches ``_ROUND_REACH`` radii beyond the label on each side, and
        runs past the ends of the curve along their tangents, as the frame does.
        A curvature test at the scale of the ball skips the sampling where no
        bend is tight enough to matter. The samples sit on whole steps of
        ``origin`` plus arc length, so a smoothed part that starts elsewhere as
        the label moves keeps the vertices where they were.

        Where a bend comes within reach of an end of the part, the margin
        doubles and the part is sampled again, up to ``_ROUND_MAX_DOUBLINGS``
        times, and stops earlier once the rounded path across the label has not
        changed for two passes in a row. A bend that is still there after the
        last doubling is rounded as far as the part shows it."""
        # A radius below the round-off slack is not rounded, and one beyond any
        # figure is as good as straight; zero means this side is skipped.
        left, right = (min(radius, _ROUND_MAX_RADIUS_PX)
                       if radius >= _ROUND_TOL_PX else 0.0
                       for radius in (ride[0] + offset_px, ride[1] - offset_px))
        widest = max(left, right)
        if widest <= 0.0:
            return None
        label_lo = s_anchor - lead * length
        label_hi = s_anchor + (1.0 - lead) * length
        reach = _ROUND_REACH * widest
        kappa = base.curvature(
            np.arange(label_lo - reach, label_hi + reach,
                      _ROUND_PROBE * widest), widest)
        # A side is rounded only where the curve bends toward it that tightly:
        # a left bend has positive curvature, a right bend negative.
        if np.max(kappa * left) < _ROUND_GATE:
            left = 0.0
        if np.max(-kappa * right) < _ROUND_GATE:
            right = 0.0
        if left <= 0.0 and right <= 0.0:
            return None
        step = max(min(r for r in (left, right) if r > 0.0) * _ROUND_STEP,
                   _ROUND_MIN_STEP_PX)
        # The samples sit on whole steps of arc length, so the vertices do not
        # move with the label. The whole steps that lie across the label are
        # the same for every margin, which lets one pass be compared with the
        # last.
        shifted_lo, shifted_hi = label_lo + origin, label_hi + origin
        across = slice(math.ceil(shifted_lo / step),
                       math.floor(shifted_hi / step) + 1)
        across_before, agreed = None, 0
        for doubling in range(_ROUND_MAX_DOUBLINGS + 1):
            margin = reach * 2 ** doubling
            first = math.floor((shifted_lo - margin) / step)
            last = math.ceil((shifted_hi + margin) / step)
            s = step * np.arange(first, last + 1)
            x, y, _ = base.points_and_angles(s - origin)
            work = _CurveFrame(x, y)
            left_rounded, left_near_end = work.rounded(left, 1, step)
            rounded, right_near_end = left_rounded.rounded(right, -1, step)
            if not (left_near_end or right_near_end):
                break
            across_now = np.column_stack([rounded._xf, rounded._yf])[
                across.start - first:across.stop - first]
            if across_before is not None and np.allclose(
                    across_now, across_before, rtol=0.0, atol=1e-6):
                agreed += 1
                if agreed == 2:
                    break
            else:
                agreed = 0
            across_before = across_now
        if rounded is work:
            return None
        anchor = float(np.interp((s_anchor + origin) / step - first,
                                 np.arange(len(s)), work._arc))
        return work, rounded, anchor

    def _place_on_curve(self, renderer, curve_px: np.ndarray | None
                        ) -> _Placement | None:
        """Place every segment and the casing along the curve, given in display
        pixels as ``curve_px``, for this renderer: the label's whole layout,
        recomputed on every draw. Returns the placement, which it leaves for
        the caller to hand to the segments, or None where the label is not
        placed: an empty label, a label off any axes, a curve with no stretch
        left to draw, or a degenerate curve."""
        if not self._segments or self.axes is None or curve_px is None:
            return None
        # The curve has gaps where a point has no pixel, as ``plot`` draws it.
        # ``pos`` is a fraction of the drawn length, and the label follows the
        # stretch that holds its anchor, as though that stretch were the whole
        # curve: past its ends the label follows its end tangents, not the
        # next stretch.
        stretch = _stretch_at(curve_px, self._pos, self._anchor)
        if stretch is None:
            return None
        points, s_anchor = stretch
        sizes = [t._size_px(renderer) for t in self._segments]
        widths = [width for width, _ in sizes]
        heights = [height for _, height in sizes]
        # A segment's span is its width plus the kern toward the next glyph:
        # the space it takes along the curve before the next one starts. The
        # glyph itself keeps its own width as the chord it is rotated by.
        spans = [w + k for w, k in zip(widths, self._kerns_px(renderer))]
        lead = {"start": 0.0, "center": 0.5, "end": 1.0}[self._anchor]
        # The path is smoothed before anything is laid on it, so rounding, the
        # offset, the casing, and the reading direction all follow what the
        # label rides. ``covered`` is the interval of arc length it covers.
        label_span = sum(spans)
        covered = (s_anchor - lead * label_span,
                   s_anchor + (1.0 - lead) * label_span)
        points, s_anchor, origin = _smoothed_stretch(
            points, s_anchor, self._smooth_px(renderer), covered,
            self._smooth == "auto")
        base = _CurveFrame(points[:, 0], points[:, 1])
        # An upright label reads left to right on screen. The chord across the
        # span the label covers decides, in display space on every draw, so an
        # inverted axis or a changed view is followed. The label keeps its
        # interval of the curve and only turns over: the curve is read from the
        # other end, and ``lead`` counts from there, so ``pos`` and ``anchor``
        # still refer to the curve as it was given.
        if self._upright and _reads_leftward(base, s_anchor, lead, label_span):
            points = points[::-1]
            s_anchor = base.length - s_anchor
            lead = 1.0 - lead
            if origin is not None:
                origin = -(origin + base.length)
            base = _CurveFrame(points[:, 0], points[:, 1])
        # The vertical-alignment datum is a font-metric constant, identical for
        # every segment, so derive it once here and hand it to each segment
        # rather than re-deriving it per glyph. Every alignment but the baseline
        # is a font line, and so is the box casing's center, which follows the
        # "center" line while the frame follows the chosen one. Measuring the
        # lines runs LaTeX under usetex, so a baseline label without a casing
        # never measures them. The font and the usetex setting are read from a
        # segment, the artist that is drawn, so a setter called on this
        # container after construction cannot measure one font and draw another.
        first_segment = self._segments[0]
        prop = first_segment.get_fontproperties()
        datum = band = 0.0
        if self._valign != "baseline" or self._box is not None:
            lines = _font_lines(prop, usetex=first_segment.get_usetex())
            datum = _valign_datum(self._valign, lines)
            band = _valign_datum("center", lines) - datum

        # Work in display pixels: take the arc-length frame of the stretch,
        # round it where a bend is tighter than the label's ink (see
        # ``_round_curve``), then shift it perpendicularly to the parallel
        # (offset) curve the label actually follows. Laying glyphs along the
        # offset curve, rather than projecting them off the base curve, keeps
        # the clearance from the curve and the on-screen letter spacing
        # uniform at once, because the cursor advances along the curve the
        # glyphs sit on. ``pos`` and ``anchor`` stay defined against the base
        # curve and are carried onto the offset curve below, so the label
        # lands where the user asked.
        offset_px = self._offset * renderer.points_to_pixels(1.0)
        flat_total = float(label_span)
        # The longest the label can be along the frame, with crowding's widest
        # possible gaps, which sets how much of the curve rounding must cover.
        reach = flat_total
        if self._crowding != "none":
            reach += len(spans) * (_MAX_CROWD - _CROWD_SLACK) * max(heights)
        rounding = self._round_curve(
            base, s_anchor, lead, reach, self._ride_radii(renderer, datum),
            offset_px, origin or 0.0)
        # ``work`` and ``rounded`` share their vertices one to one, and so do
        # ``rounded`` and ``frame``: without rounding all three are the curve.
        work, rounded, s_work = rounding or (base, base, s_anchor)
        frame = rounded.offset(offset_px)
        if not np.isfinite(frame.length) or frame.length <= 0.0:
            return None

        # Anchor at ``pos`` of the base curve, carried onto the rounded, offset
        # curve, so the user's placement reads against the curve they passed
        # in. ``lead`` is the fraction of the label that sits before the anchor
        # point.
        s0 = float(work.remap_arc(frame, s_work))

        # Per-glyph advances along the offset curve. In ``"curvature"`` mode
        # these are widened on bends (see ``_advances``); the curve is sampled
        # along the un-widened layout, anchored the same way, which is accurate
        # enough since the widening shifts positions only slightly. The label
        # then spans ``total`` pixels from the re-anchored cursor.
        advances = self._advances(frame, spans, heights, s0 - lead * flat_total)
        total = float(sum(advances))
        cursor = s0 - lead * total

        # The casing follows the curve across the label's whole span at the
        # tallest glyph's height, so it clears the lines behind plain and math
        # segments alike (a single fill, immune to the per-character
        # cannibalization a wide ``path_effects`` stroke would cause). The label
        # lies on the frame at its ``valign`` datum, so the glyph band is centered a
        # little off the frame; shift the casing centerline by that band offset so
        # it sits over the ink rather than over the bare datum line.
        box = None
        if self._box is not None:
            px_per_unit = _px_per_unit(renderer, prop.get_size_in_points())
            band_px = band * px_per_unit
            s_box = np.linspace(cursor, cursor + total, _BOX_SAMPLES)
            bx, by, bang = frame.points_and_angles(s_box)
            bx = bx - band_px * np.sin(bang)
            by = by + band_px * np.cos(bang)
            box = _BoxPlace(np.column_stack([bx, by]),
                            self._box_pad * max(heights)
                            / renderer.points_to_pixels(1.0))

        # ``cursor`` walks the label's left edge along the arc. Each segment maps
        # its baseline-relative outline onto the curve when it draws: a plain
        # glyph rigidly (one rotation by the chord across its own width, so it
        # stays undistorted), a math run by bending its outlines. Centering each
        # segment's span in its (possibly widened) slot lets crowding space
        # plain glyphs and math runs alike, and the shared baseline datum keeps
        # them level. The kern stays between the pair it belongs to, because the
        # glyph starts where its span starts.
        places = []
        for w, span, adv in zip(widths, spans, advances):
            places.append(_SegmentPlace(
                frame, cursor + (adv - span) / 2.0, w, datum))
            cursor += adv
        return _Placement(tuple(places), box)


def curved_text(ax: Axes, x: ArrayLike | Sequence[Any],
                y: ArrayLike | Sequence[Any], text: str, *,
                pos: float = 0.5, anchor: str = "center", offset: float = 0.0,
                box: bool | str | dict = False, crowding: str = "none",
                valign: str = "center", upright: bool = False,
                min_radius: float | str | None = "auto",
                smooth: float | str | None = None,
                **kwargs: Any) -> CurvedText:
    """Draw ``text`` along the curve ``(x, y)`` on ``ax`` and return the artist.

    A short form of :class:`CurvedText`, with the same arguments and the same
    result. The axes is the first argument here, as in matplotlib's other
    axes-first helper functions. :class:`CurvedText` takes it after
    ``x, y, text``, as :class:`matplotlib.text.Text` does. Passing the axes last
    to this function raises ``AttributeError``.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        The axes to draw into.
    x, y : array-like
        The curve in data coordinates: 1-D, equal length, ordered along the
        curve.
    text : str
        The string to draw. It may contain mathtext runs (``$...$``).
    pos : float, default 0.5
        Anchor position as a fraction of the drawn arc length of the curve.
    anchor : {"start", "center", "end"}, default "center"
        Which part of the label sits at ``pos``.
    offset : float, default 0.0
        Distance from the curve, perpendicular to it, in points (1/72 inch).
    box : bool, str, or dict, default False
        A band behind the label that clears the lines it crosses: ``True`` for
        white, a color string, or a dict with ``color``, ``pad``, and ``alpha``.
    crowding : {"none", "curvature"}, default "none"
        ``"curvature"`` adds spacing between characters on tight bends.
    valign : {"center", "baseline", "ascender", "descender"}, default "center"
        Which line of the text lies on the curve.
    upright : bool, default False
        Turn the label over where it would read upside down.
        :class:`CurvedText` describes the rule.
    min_radius : {"auto"}, None, or float, default "auto"
        The least radius, in points, of the path the label rides.
        ``"auto"`` rounds a bend tighter than the label's ink; ``None`` turns
        the rounding off. :class:`CurvedText` describes the rule.
    smooth : {"auto"}, None, or float, default None
        The width, in points, over which the path the label rides is smoothed.
        ``"auto"`` smooths where the path wiggles under the label; ``None``
        leaves the path as it is. :class:`CurvedText` describes the rule.
    **kwargs
        :class:`~matplotlib.text.Text` properties applied to every glyph and
        math run, such as ``color``, ``fontsize``, ``alpha``, and
        ``path_effects``. :class:`CurvedText` lists the properties that have no
        effect.

    Returns
    -------
    CurvedText
        The label artist, already added to ``ax``.

    Raises
    ------
    ValueError, TypeError, matplotlib.units.ConversionError, AttributeError
        As for :class:`CurvedText`, which lists the conditions.

    Notes
    -----
    The layout is computed again on every draw, so the label follows the curve
    through resizing, panning, and zooming. See the Notes and Limits of
    :class:`CurvedText` for vector output, 3D axes, what can change after
    creation, removing a label, and usetex.

    Examples
    --------
    >>> import numpy as np
    >>> import matplotlib.pyplot as plt
    >>> from curved_text import curved_text
    >>> x = np.linspace(0, 2 * np.pi, 200)
    >>> y = np.sin(x)
    >>> fig, ax = plt.subplots()
    >>> line, = ax.plot(x, y)
    >>> label = curved_text(ax, x, y, "a sine wave", pos=0.5, offset=8)
    """
    return CurvedText(x, y, text, ax, pos=pos, anchor=anchor, offset=offset,
                      box=box, crowding=crowding, valign=valign,
                      upright=upright, min_radius=min_radius, smooth=smooth,
                      **kwargs)
