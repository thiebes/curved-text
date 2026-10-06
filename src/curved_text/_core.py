"""Draw text along an arbitrary curve in a matplotlib Axes."""
# Developed with AI assistance under maintainer review; see the
# "Development and AI use" section of the README.
from __future__ import annotations

import copy
import functools
import inspect
import itertools
import math
import re
import unicodedata
from typing import TYPE_CHECKING, Any, NamedTuple

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
    """Height above the baseline, in 1/100-em layout units, that rides the curve
    for the given vertical alignment.

    ``"baseline"`` returns 0, so the text baseline follows the curve unshifted.
    The others shift every segment by the same font-metric constant -- the curve
    passes through the vertical centre, the ascender line, or the descender line
    -- so plain glyphs and mathtext stay aligned and no per-glyph step is
    introduced (the shift is identical for every glyph).
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

        This is the rotation a glyph of width ``span`` takes: it follows the
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


def _finite_runs(curve_px: np.ndarray) -> list[np.ndarray]:
    """The stretches of the curve, in display pixels, that a line draws: runs
    of at least two consecutive points with a pixel. ``plot`` breaks a line at
    a NaN, infinite, or masked point, and at a point the axes' scale gives no
    pixel, and draws nothing at an isolated point."""
    finite = np.isfinite(curve_px).all(axis=1)
    edges = np.flatnonzero(np.diff(finite.astype(np.int8))) + 1
    return [run for run, drawn in zip(np.split(curve_px, edges),
                                      np.split(finite, edges))
            if drawn[0] and len(run) >= 2]


def _run_at(runs: list[_CurveFrame], pos: float) -> tuple[_CurveFrame, float]:
    """The run holding the point ``pos`` of the way along the runs' total
    length, and that point's fraction of the run's own length. A point where
    one run ends and the next starts is the next run's start; ``pos`` below 0
    or above 1 lies before the first run or past the last. Runs of no length
    hold no point."""
    runs = [run for run in runs if run.length > 0.0]
    ends = np.cumsum([run.length for run in runs])
    target = pos * float(ends[-1])
    index = min(int(np.searchsorted(ends, target, side="right")), len(runs) - 1)
    start = float(ends[index]) - runs[index].length
    return runs[index], (target - start) / runs[index].length


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
    between neighbours. Each printing character sets one glyph, or one rule
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
    for the shared converter, so the factor is 1 there, and within 1.4% of 1
    for a :func:`_tex_to_path` converter at any size up to 72 pt.
    """
    em_px = converter.FONT_SCALE * converter.DPI / _text_to_path.DPI
    return _text_to_path.FONT_SCALE / em_px


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
    parent's cursor walk measures every segment the same way -- by window-extent
    width -- and, crucially, both keep the text baseline as the shared datum
    (``v = 0``), so plain glyphs and math runs sit on one baseline by construction.

    Placement maps an outline point ``(u, v)`` -- arc length from the segment's
    left edge and height above the baseline, both in 1/100-em layout units -- into
    display pixels. ``v`` is shifted by the vertical-alignment datum
    (:func:`_valign_datum`), so the chosen line (baseline, centre, ascender, or
    descender) is what rides the curve. Because each glyph is placed by an
    isometry, the perpendicular distance from the curve equals ``v`` exactly --
    there is no per-glyph step, and plain and math are identical by construction.

    Subclasses differ only in where the outline comes from
    (:meth:`_build_outline`) and whether it is placed rigidly or bent along the
    curve (:attr:`_bend`). Any perpendicular offset is already baked into the
    frame (it is the parallel curve), so a segment rides it with no offset
    handling of its own.
    """

    #: Whether the outline bends along the curve (math runs) or is placed rigidly
    #: as a single undistorted glyph (plain characters).
    _bend = False

    def __init__(self, text: str, **kwargs: Any) -> None:
        super().__init__(0.0, 0.0, text, **kwargs)
        # The container positions every segment when it draws, so the Text
        # position is not where the segment appears, and figure layout
        # (``bbox_inches="tight"``, constrained layout) must not measure it.
        self.set_in_layout(False)
        # The container still measures the segment's size there (``_size_px``),
        # so the position is the display origin, which has a pixel on every
        # axis scale; the data origin has none on a logit axis, a log axis that
        # masks non-positive values, or polar axes whose radial limits start
        # above zero. The axes keep a transform already set.
        # A ``transform`` keyword forwarded from the label is replaced on
        # purpose: the segment draws in display pixels and never uses it.
        self.set_transform(IdentityTransform())
        self._frame: _CurveFrame | None = None
        self._s_left = 0.0
        self._width_px = 0.0
        self._datum = 0.0
        self._outline_cache: tuple | None = None

    def get_window_extent(self, renderer=None, dpi=None) -> Bbox:
        """An empty extent. A segment is measured as part of its label
        (:meth:`CurvedText.get_window_extent`), so a legend placed at
        ``loc="best"``, which measures every text in the axes, counts each
        label once, and never at the segment's unused Text position."""
        return Bbox.null()

    def pickable(self) -> bool:
        """Never. A segment is picked as part of its label
        (:meth:`CurvedText.contains`), though the label's ``picker`` keyword
        reaches it too: matplotlib asks a picker function without calling
        ``contains``, and the segment's own Text position is the display
        origin."""
        return False

    def contains(self, mouseevent) -> tuple[bool, dict]:
        """Never, for hover as for picking (:meth:`pickable`). matplotlib's
        ``Text.contains`` would test the segment's own Text box, at the display
        origin, not its empty extent."""
        return False, {}

    def _size_px(self, renderer) -> tuple[float, float]:
        """This segment's unrotated width and height in display pixels, as
        matplotlib measures its text at its Text position, the display origin.
        Segments never set a Text rotation, so the window extent is the
        unrotated box."""
        extent = mtext.Text.get_window_extent(self, renderer=renderer)
        return extent.width, extent.height

    def _set_placement(self, frame: _CurveFrame, s_left: float,
                       width_px: float, datum: float) -> None:
        """Receive this draw's frame, the arc length of the segment's left edge on
        it (already the parallel curve when offset), the segment's own width in
        pixels (the chord a rigid glyph is rotated by; its kern toward the next
        glyph moves only the cursor, not the glyph), and the
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
        # Callers place the label first, which assigns every segment a frame.
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
            # width, about its centre on the curve. A single isometry preserves
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

    def _build_outline(self, prop: font_manager.FontProperties, text: str,
                       usetex: bool) -> tuple[np.ndarray, np.ndarray]:
        """Build the outline that :meth:`_outline_units` caches. Implemented by
        subclasses."""
        raise NotImplementedError


class _PlainGlyph(_OutlineSegment):
    """One plain character, drawn as a rigid (undistorted) glyph outline whose
    baseline rides the curve. Inherits ``_bend = False`` from the base.

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
        px_per_unit = (renderer.points_to_pixels(self.get_fontsize())
                       / _text_to_path.FONT_SCALE)
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
    the curve so radicals, fractions, and sized delimiters stay connected at any
    curvature. Its baseline is the same shared datum as the plain glyphs, so the
    run's main symbols sit level with neighbouring characters."""

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
    """A string drawn along an (x, y) curve, one segment at a time (each plain
    character and each ``$...$`` run).

    Every glyph -- plain character or mathtext run -- is laid out on one shared
    text baseline and mapped onto the curve from its glyph outline: a plain
    character rigidly (one rotation by the chord across its own width, so its
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
    matplotlib's mathtext engine and bent continuously along the curve -- every
    glyph outline and rule box is mapped through the curve's arc-length frame, so
    radicals, fractions, and sized delimiters stay connected at any curvature.
    The run rides the same baseline as the surrounding plain glyphs, so its main
    symbols sit level with them. Pass ``parse_math=False`` to treat dollar signs
    literally. Tall expressions compress vertically on the inside of tight bends,
    so choose label size relative to curvature accordingly.

    LaTeX is used instead when ``text.usetex`` is set or ``usetex=True`` is
    passed, so the label matches the figure's other usetex text. Math runs are
    then typeset by LaTeX, and so is plain text, literally: characters that are
    TeX markup (such as ``%``, ``#``, and the backslash) are escaped, so TeX
    commands work only inside ``$...$``. Each plain run is typeset in one LaTeX
    pass and kerned as TeX sets it; a run with a character TeX builds from
    several pieces, such as an accented letter in the default encoding, or one
    that can print nothing, such as a soft hyphen, is typeset one character at
    a time, without kerning. Plain text is limited to
    characters the LaTeX preamble can typeset; the README shows how to declare
    upright Greek letters there. The ``valign`` ascender and descender lines are
    the height and depth TeX gives ``()gy`` in the font it sets the text in. The
    first draw runs LaTeX once for each distinct plain run and math run, and
    up to twice more to measure line heights, and later draws reuse the
    caches. The usetex setting is fixed when the label is constructed, as
    matplotlib fixes it for each glyph; pass ``usetex`` or set the rcParam
    before creating the label. Set the LaTeX preamble, font family, and font
    lists before the figure is drawn, too: matplotlib caches text measurements
    per figure without them, so after a change a redraw of the same figure
    keeps the old measurements of math runs and of text typeset one character
    at a time, while plain runs follow the change. matplotlib's own usetex
    text also keeps the old measurements. Under usetex the font family comes
    from the ``font.family`` rcParam, as for matplotlib's own usetex text, and
    the ``fontfamily`` keyword has no effect. Math runs are passed to LaTeX as
    written, so they can run TeX commands, including ones that read local
    files; do not pass untrusted text with usetex on.

    Both plain glyphs and mathtext runs are rendered from their glyph outlines
    rather than as hinted ``Text`` artists. On a rotated label this is what lets a
    single baseline be pinned exactly; the only cost is the loss of pixel-grid
    hinting, which is marginal on rotated text and matches how mathtext has always
    rendered. Under usetex matplotlib loads the glyphs with light hinting, laid
    out at a resolution where it is negligible.

    Parameters
    ----------
    x, y : array-like
        The curve in data coordinates: 1-D, equal length, and ordered along
        the curve. A NaN, infinite, or masked point leaves a gap, as in
        ``plot``, and the curve needs at least two consecutive finite points.
        Any type the axes' unit converters
        accept works, as for ``plot``: dates (``datetime64``, ``datetime``,
        pandas dates), category strings, and unit-aware values. An axis without
        units takes them from the curve; category strings not yet on an axis
        are added to it, as ticks. Data an axis cannot convert raises
        matplotlib's ``ConversionError``.
    text : str
        The string to draw. May contain mathtext runs (``$...$``).
    axes : matplotlib.axes.Axes
        The axes to draw into.
    pos : float, default 0.5
        Arc-length fraction in ``[0, 1]`` for the anchor point. On a curve with
        gaps it is a fraction of the drawn length, and the label rides the
        stretch that holds its anchor.
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
        How to space glyphs around bends. ``"none"`` spaces them as ordinary
        text does, by width and kerning, so on the concave side of a tight bend
        the rotated glyph boxes can overlap. ``"curvature"`` opens an even
        letterspacing gap that grows with the local curvature and the glyph
        height, so the inside edges stop colliding; the gap is the same between
        every pair of letters, and a deadband leaves gentle bends and straight
        runs unchanged.
    valign : {"center", "baseline", "ascender", "descender"}, default "center"
        Which line of the text rides the curve. ``"center"`` straddles the text on
        the curve (the default); ``"baseline"`` follows the text baseline so the
        body sits above the curve; the others ride the ascender or descender line.
        Each is a constant font-metric shift applied to the whole label.
    **kwargs
        Passed to each per-character glyph and each math run (for example
        ``color``, ``fontsize``, ``alpha``, ``fontfamily``, ``usetex``).
    """

    def __init__(self, x: ArrayLike | Sequence[Any], y: ArrayLike | Sequence[Any],
                 text: str, axes: Axes, *,
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
        # Optional casing behind the label: a fat line following the curve at
        # the label's height. It is built before the label touches the axes, so
        # a ``box`` it cannot draw raises with the axes as they were; its
        # geometry is set in ``draw`` (on the container), so it must draw after
        # the container and before the glyphs, and ``set_zorder`` below places
        # it between them.
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
        axes.add_artist(self)
        # The converted curve is already kept, so the label must hear of a
        # change of units from now on, before its first placement too.
        self._follow_axis_units()
        self._box_pad = box_pad
        self._box: mlines.Line2D | None = box_line
        if self._box is not None:
            axes.add_line(self._box)
            # The label measures its casing (``get_window_extent``), so figure
            # layout must not measure it again, as for the segments.
            self._box.set_in_layout(False)
        # The key of the last placement (``_placement_key``), whether that
        # placement succeeded, and the extent and glyph boxes measured from it.
        # A measurement reuses the placement while its key is unchanged.
        self._placed_key: tuple | None = None
        self._placed = False
        self._extent_cache: Bbox | None = None
        self._glyph_box_cache: tuple[Bbox, ...] | None = None
        self._segments: list[_OutlineSegment] = []
        runs = (_split_runs(text) if self.get_parse_math()
                else [_Run(False, text)])
        for run in runs:
            if run.is_math:
                segment = _MathRun(run.text, **kwargs)
                axes.add_artist(segment)
                self._segments.append(segment)
                continue
            for index, ch in enumerate(run.text):
                glyph = _PlainGlyph(ch, run.text, index, **kwargs)
                axes.add_artist(glyph)
                self._segments.append(glyph)
        # Apply the layered zorders now that the casing and glyphs exist: the
        # container draws first (it positions them), then the casing, then the
        # glyphs on top. Visibility and clipping reach the casing the same way;
        # for the glyphs, which have them already from the keyword arguments and
        # the axes, applying them again changes nothing.
        self.set_zorder(self.get_zorder())
        self.set_visible(self.get_visible())
        self.set_clip_on(self.get_clip_on())
        self.set_clip_path(self.get_clip_path())
        self.set_clip_box(self.get_clip_box())

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

    def set_visible(self, b) -> None:
        # The container draws nothing itself, so its visibility and clipping
        # (the setters below) apply to the parts it draws: every segment and
        # the casing.
        super().set_visible(b)
        for part in self._parts():
            part.set_visible(b)

    def set_clip_on(self, b) -> None:
        super().set_clip_on(b)
        for part in self._parts():
            part.set_clip_on(b)

    def set_clip_box(self, clipbox) -> None:
        super().set_clip_box(clipbox)
        for part in self._parts():
            part.set_clip_box(clipbox)

    def set_clip_path(self, path, transform=None) -> None:
        super().set_clip_path(path, transform)
        for part in self._parts():
            part.set_clip_path(path, transform)

    def _parts(self) -> list[martist.Artist]:
        """The artists the label draws: its segments and its casing. Setters
        may run during base-class construction, before they exist."""
        parts: list[martist.Artist] = list(getattr(self, "_segments", ()))
        box = getattr(self, "_box", None)
        if box is not None:
            parts.append(box)
        return parts

    def _unplace(self) -> None:
        # The glyphs and the casing are axes-owned artists drawn independently,
        # so when ``_place_on_curve`` bails out before positioning them they
        # must be cleared explicitly, or the previous placement stays painted:
        # a glyph without a frame draws nothing, and the casing is hidden.
        for segment in self._segments:
            segment._frame = None
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
                px_per_unit = (renderer.points_to_pixels(prop.get_size_in_points())
                               / _text_to_path.FONT_SCALE)
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

    def draw(self, renderer, *args, **kwargs) -> None:
        # The container draws nothing itself: its segments and casing are
        # artists the axes draws after it, so drawing it places them. Every
        # draw places them afresh, so a changed label is measured afresh too. A
        # hidden label has hidden its parts (``set_visible``) and is not placed.
        if self.get_visible():
            self._place(renderer)
        self.stale = False

    def get_window_extent(self, renderer=None, dpi=None) -> Bbox:
        """The extent of the label as drawn, in display pixels: its glyphs and
        its box casing.

        Figure layout (``bbox_inches="tight"``, constrained layout, and from
        matplotlib 3.10 ``legend(loc="best")``) measures the label through it.
        Constrained layout measures before the first draw has placed anything,
        so the label is placed on the curve to be measured. The container's own
        Text, a single space at the curve's first finite point, takes no part.
        Each glyph counts by the box of its outline's control points, which holds
        the curves between them: it can exceed the ink by a fraction of a pixel,
        never fall short of it, and costs far less than exact curve extrema. The
        casing counts by its band, half its line width beyond its centreline on
        every side, which also covers its round caps.
        Without a renderer, the label is measured with one at the figure's dpi
        (:func:`_measuring_renderer`). ``dpi`` scales the extent to that
        resolution, which matches placing the label at that dpi to within what
        whole-pixel glyph widths add up to. A hidden label, and one that cannot
        be placed (an empty label, a label off any axes, or a degenerate curve),
        has an empty extent at the curve's first finite point.

        Figure layout can measure the label several times a draw, and a legend
        measures it right after the label's own draw has placed it, so a
        measurement reuses the last placement, and its extent, while what the
        placement depends on is unchanged (:meth:`_placement_key`).
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

    def _place_if_stale(self, renderer) -> None:
        """Place the label for ``renderer`` unless the last placement was for
        the same renderer, curve position, and glyphs (:meth:`_placement_key`)."""
        curve_px = self._curve_px()
        key = self._placement_key(renderer, curve_px)
        if key != self._placed_key:
            self._place(renderer, curve_px, key)

    def _place(self, renderer, curve_px: np.ndarray | None = None,
               key: tuple | None = None) -> None:
        """Place the label for ``renderer`` (:meth:`_place_on_curve`) and record
        the placement's key, which voids what was measured from the last."""
        if curve_px is None:
            curve_px = self._curve_px()
        if key is None:
            key = self._placement_key(renderer, curve_px)
        self._placed = self._place_on_curve(renderer, curve_px)
        self._placed_key = key
        self._extent_cache = None
        self._glyph_box_cache = None

    def _curve_px(self) -> np.ndarray | None:
        """The curve's points in display pixels, or None off any axes.

        The points are converted by the axes' units here, where drawing,
        measuring, and picking all place the label, so each follows the axes'
        current units. The conversion is kept until either axis's units change
        (:meth:`_forget_curve_floats`)."""
        if self.axes is None:
            return None
        self._follow_axis_units()
        if self._curve_floats is None:
            self._curve_floats = (_axis_floats(self.axes.xaxis, self._cx),
                                  _axis_floats(self.axes.yaxis, self._cy))
        return self.axes.transData.transform(np.column_stack(self._curve_floats))

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
        """The box of the placed glyphs' control points and the casing's band,
        or an empty box at the curve's first finite point when the label could
        not be placed; kept until the label is placed again."""
        if self._extent_cache is None:
            glyph_boxes = self._glyph_boxes(renderer)
            if not glyph_boxes:
                self._extent_cache = self._empty_extent()
            else:
                bands = []
                if self._box is not None and self._box.get_visible():
                    half_width = (renderer.points_to_pixels(
                        self._box.get_linewidth()) / 2)
                    bands.append(
                        self._box.get_window_extent(renderer).padded(half_width))
                self._extent_cache = Bbox.union([*glyph_boxes, *bands])
        return self._extent_cache

    def _glyph_boxes(self, renderer) -> tuple[Bbox, ...]:
        """The box of each placed glyph's outline control points, in display
        pixels, kept until the label is placed again; none when the label
        could not be placed."""
        if self._glyph_box_cache is None:
            boxes = []
            if self._placed:
                for seg in self._segments:
                    path = seg._placed_path(renderer)
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
        """An empty box at the curve's first finite point, or, when the axes
        give that point no pixel (a log axis that masks it), at the curve's
        first point that has one."""
        point = self.get_transform().transform(self.get_unitless_position())
        if not np.isfinite(point).all():
            curve_px = self._curve_px()
            if curve_px is not None:
                drawn = curve_px[np.isfinite(curve_px).all(axis=1)]
                if len(drawn):
                    point = drawn[0]
        return Bbox.from_bounds(point[0], point[1], 0.0, 0.0)

    def _place_on_curve(self, renderer, curve_px: np.ndarray | None) -> bool:
        """Place every segment and the casing along the curve, given in display
        pixels as ``curve_px``, for this renderer: the label's whole layout,
        recomputed on every draw. Returns whether the label was placed: an
        empty label, a label off any axes, or a degenerate curve is not."""
        if not self._segments or self.axes is None or curve_px is None:
            self._unplace()
            return False
        axes = self.axes
        # The curve has gaps where a point has no pixel, as ``plot`` draws it.
        # ``pos`` is a fraction of the drawn length, and the label rides the
        # stretch that holds its anchor, as though that stretch were the whole
        # curve: past its ends the label follows its end tangents, not the
        # next stretch.
        runs = [_CurveFrame(run[:, 0], run[:, 1])
                for run in _finite_runs(curve_px)]
        if not any(run.length > 0.0 for run in runs):
            # No stretch with a span to position the label on; hide it rather
            # than leave the previous draw's glyphs and band stranded on screen.
            self._unplace()
            return False
        base, pos = _run_at(runs, self._pos)
        # Work in display pixels: build the arc-length frame of the stretch,
        # then shift it perpendicularly to the parallel (offset) curve the
        # label actually rides. Laying glyphs along the offset curve -- rather
        # than projecting them off the base curve -- keeps the clearance from
        # the curve and the on-screen letter spacing uniform at once, because
        # the cursor advances along the curve the glyphs sit on. ``pos`` and
        # ``anchor`` stay defined against the base curve and are carried onto
        # the offset curve below, so the label lands where the user asked.
        offset_px = self._offset * renderer.points_to_pixels(1.0)
        frame = base.offset(offset_px)
        if not np.isfinite(frame.length) or frame.length <= 0.0:
            self._unplace()
            return False
        inv = axes.transData.inverted()

        # The vertical-alignment datum is a font-metric constant, identical for
        # every segment, so derive it once here and hand it to each segment
        # rather than re-deriving it per glyph. Every alignment but the baseline
        # is a font line, and so is the box casing's centre, which follows the
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

        sizes = [t._size_px(renderer) for t in self._segments]
        widths = [width for width, _ in sizes]
        heights = [height for _, height in sizes]
        # A segment's span is its width plus the kern toward the next glyph:
        # the space it takes along the curve before the next one starts. The
        # glyph itself keeps its own width as the chord it is rotated by.
        spans = [w + k for w, k in zip(widths, self._kerns_px(renderer))]

        # Anchor at ``pos`` of the base curve, carried onto the offset curve, so
        # the user's placement reads against the curve they passed in. ``lead``
        # is the fraction of the label that sits before the anchor point.
        s0 = float(base.remap_arc(frame, pos * base.length))
        lead = {"start": 0.0, "center": 0.5, "end": 1.0}[self._anchor]

        # Per-glyph advances along the offset curve. In ``"curvature"`` mode
        # these are widened on bends (see ``_advances``); the curve is sampled
        # along the un-widened layout, anchored the same way, which is accurate
        # enough since the widening shifts positions only slightly. The label
        # then spans ``total`` pixels from the re-anchored cursor.
        flat_total = float(sum(spans))
        advances = self._advances(frame, spans, heights, s0 - lead * flat_total)
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
            band_px = band * ppu
            s_box = np.linspace(cursor, cursor + total, _BOX_SAMPLES)
            bx, by, bang = frame.points_and_angles(s_box)
            bx = bx - band_px * np.sin(bang)
            by = by + band_px * np.cos(bang)
            box_xy = inv.transform(np.column_stack([bx, by]))
            height = max(heights)
            self._box.set_data(box_xy[:, 0], box_xy[:, 1])
            self._box.set_linewidth(
                self._box_pad * height / renderer.points_to_pixels(1.0))
            self._box.set_visible(self.get_visible())

        # ``cursor`` walks the label's left edge along the arc. Each segment maps
        # its baseline-relative outline onto the curve when it draws: a plain
        # glyph rigidly (one rotation by the chord across its own width, so it
        # stays undistorted), a math run by bending its outlines. Centering each
        # segment's span in its (possibly widened) slot lets crowding space
        # plain glyphs and math runs alike, and the shared baseline datum keeps
        # them level. The kern stays between the pair it belongs to, because the
        # glyph starts where its span starts.
        for t, w, span, adv in zip(self._segments, widths, spans, advances):
            t._set_placement(frame, cursor + (adv - span) / 2.0, w, datum)
            cursor += adv
        return True


def curved_text(ax: Axes, x: ArrayLike | Sequence[Any],
                y: ArrayLike | Sequence[Any], text: str, *,
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
