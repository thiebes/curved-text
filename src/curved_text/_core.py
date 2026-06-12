"""Draw text along an arbitrary curve in a matplotlib Axes."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import matplotlib.text as mtext
import numpy as np

if TYPE_CHECKING:
    from matplotlib.axes import Axes
    from numpy.typing import ArrayLike

__all__ = ["CurvedText", "curved_text"]

_ANCHORS = ("start", "center", "end")


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

    Parameters
    ----------
    x, y : array-like
        The curve in data coordinates: 1-D, equal length, at least two points,
        finite, and ordered along the curve.
    text : str
        The string to draw.
    axes : matplotlib.axes.Axes
        The axes to draw into.
    pos : float, default 0.5
        Arc-length fraction in ``[0, 1]`` for the anchor point.
    anchor : {"start", "center", "end"}, default "center"
        Which part of the label sits at ``pos``.
    offset : float, default 0.0
        Perpendicular offset off the curve, in points.
    **kwargs
        Passed to each per-character :class:`~matplotlib.text.Text` (for example
        ``color``, ``fontsize``, ``alpha``, ``fontfamily``).
    """

    def __init__(self, x: ArrayLike, y: ArrayLike, text: str, axes: Axes, *,
                 pos: float = 0.5, anchor: str = "center", offset: float = 0.0,
                 **kwargs: Any) -> None:
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
        self._chars: list[mtext.Text] = []
        for ch in text:
            t = mtext.Text(0.0, 0.0, " " if ch == " " else ch, **kwargs)
            t.set_ha("center")
            t.set_va("center")
            axes.add_artist(t)
            self._chars.append(t)

    def set_zorder(self, zorder) -> None:
        # Keep the glyphs one level above the container so they sit on top of it.
        # ``super().__init__`` may set the zorder before ``_chars`` exists, so
        # guard against running during base-class construction.
        super().set_zorder(zorder)
        for t in getattr(self, "_chars", ()):
            t.set_zorder(self.get_zorder() + 1)

    def remove(self) -> None:
        # The glyphs are independent artists on the axes; remove them with the
        # container so removal does not leave them behind as orphans.
        for t in self._chars:
            t.remove()
        self._chars = []
        super().remove()

    def draw(self, renderer, *args, **kwargs) -> None:
        if not self._chars:
            return
        axes = self.axes
        # Work in display pixels: project the curve, accumulate cumulative arc
        # length along it, and the tangent angle of each segment.
        pts = axes.transData.transform(np.column_stack([self._cx, self._cy]))
        xf, yf = pts[:, 0], pts[:, 1]
        arc = np.insert(np.cumsum(np.hypot(np.diff(xf), np.diff(yf))), 0, 0.0)
        if not np.isfinite(arc[-1]) or arc[-1] <= 0.0:
            return
        rads = np.arctan2(np.diff(yf), np.diff(xf))
        inv = axes.transData.inverted()

        # Reset any rotation left by the previous draw before measuring, so each
        # width is the unrotated advance, not the wider rotated bounding box.
        for t in self._chars:
            t.set_rotation(0)
        widths = [t.get_window_extent(renderer=renderer).width for t in self._chars]
        total = float(sum(widths))

        def _point(s):
            # Position at arc length ``s``. ``i`` is the segment it falls in, which
            # the caller uses for the segment-tangent fallback ``rads[i]``. Clipping
            # the index extrapolates past either end along the terminal segment.
            i = int(np.clip(np.searchsorted(arc, s) - 1, 0, len(arc) - 2))
            d = arc[i + 1] - arc[i]
            f = (s - arc[i]) / d if d else 0.0
            return i, xf[i] + f * (xf[i + 1] - xf[i]), yf[i] + f * (yf[i + 1] - yf[i])

        s0 = self._pos * arc[-1]
        if self._anchor == "center":
            cursor = s0 - total / 2.0
        elif self._anchor == "end":
            cursor = s0 - total
        else:
            cursor = s0

        # Offset the whole label along the normal of its chord (first to last
        # glyph); ``_point`` extrapolates past the curve ends along their tangents.
        _, x0, y0 = _point(cursor)
        _, x1, y1 = _point(cursor + total)
        dx, dy = x1 - x0, y1 - y0
        norm = float(np.hypot(dx, dy))
        nx, ny = (-dy / norm, dx / norm) if norm else (0.0, 1.0)
        scale = self._offset * renderer.points_to_pixels(1.0)
        ox, oy = nx * scale, ny * scale

        # ``cursor`` walks the label's left edge along the arc; each glyph is
        # centered on its own midpoint and rotated to the chord across its own
        # advance, which smooths the segment-wise tangent of a coarse polyline
        # at exactly the glyph's own length scale.
        for t, w in zip(self._chars, widths):
            i, px, py = _point(cursor + w / 2.0)
            _, lx, ly = _point(cursor)
            _, rx, ry = _point(cursor + w)
            if rx == lx and ry == ly:
                rot = rads[i]  # zero-width glyph; the chord is degenerate
            else:
                rot = np.arctan2(ry - ly, rx - lx)
            t.set_position(inv.transform((px + ox, py + oy)))
            t.set_rotation(np.degrees(rot))
            t.set_visible(True)
            cursor += w


def curved_text(ax: Axes, x: ArrayLike, y: ArrayLike, text: str, *,
                pos: float = 0.5, anchor: str = "center", offset: float = 0.0,
                **kwargs: Any) -> CurvedText:
    """Draw ``text`` along the curve ``(x, y)`` on ``ax`` and return the artist.

    Thin convenience wrapper around :class:`CurvedText`; see it for the meaning of
    ``pos``, ``anchor``, and ``offset``. The axes is the first argument here,
    matching matplotlib's axes-first helper functions, whereas :class:`CurvedText`
    takes it after ``x, y, text`` to match :class:`matplotlib.text.Text`.
    """
    return CurvedText(x, y, text, ax, pos=pos, anchor=anchor, offset=offset,
                      **kwargs)
