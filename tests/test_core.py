"""Smoke and behaviour tests for curved_text.

The Agg backend is selected in conftest.py before pyplot is imported.
"""
# Developed with AI assistance under maintainer review; see the
# "Development and AI use" section of the README.
import datetime
import functools
import inspect
import pickle
import shutil
import subprocess

import matplotlib as mpl
import matplotlib.cbook as cbook
import matplotlib.dates as mdates
import matplotlib.font_manager as font_manager
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.units as munits
import numpy as np
import pandas as pd
import pytest
from matplotlib.backend_bases import MouseEvent
from matplotlib.backends.backend_pdf import FigureCanvasPdf
from matplotlib.testing import jpl_units
from matplotlib.texmanager import TexManager
from matplotlib.transforms import Bbox

from curved_text import CurvedText, _core, curved_text
from curved_text._core import (
    _font_lines, _layout_units, _MathRun, _PlainGlyph, _split_runs, _tex_source,
    _tex_to_path, _text_to_path, _valign_datum)

# usetex outline extraction runs latex and reads the DVI, which needs kpsewhich
# to locate the fonts.
needs_latex = pytest.mark.skipif(
    shutil.which("latex") is None or shutil.which("kpsewhich") is None,
    reason="usetex needs a LaTeX installation")

# TeX's ten special characters, plus the three that the default OT1 encoding
# typesets as other glyphs ("<" as an inverted "!"). Listed here, not read from
# the escape table, so a special character missing from the table makes the
# literal test fail. Unescaped, the three OT1 characters still draw, but as the
# wrong glyphs, so the literal test cannot catch a missing entry for them; the
# relation-sign and bar tests do.
_TEX_MARKUP = r"#$%&~_^\{}<>|"


def _draw(fig):
    """Force a draw so CurvedText positions its glyphs."""
    fig.canvas.draw()


def _math_runs(ct):
    return [t for t in ct._segments if isinstance(t, _MathRun)]


def _anchor_px(seg):
    """The point on the (offset) curve a segment is centered on -- its baseline
    datum at mid-advance -- in display pixels. This is the placement analog of the
    superseded per-character ``Text.get_position`` and is valid after a draw."""
    x, y, _ = seg._frame.points_and_angles(seg._s_left + seg._width_px / 2.0)
    return np.array([float(x), float(y)])


def _anchor_xy(ct):
    """Per-segment curve anchors in data coordinates."""
    inv = ct.axes.transData.inverted()
    return np.array([inv.transform(_anchor_px(s)) for s in ct._segments])


def _rotation_deg(seg):
    """The rigid rotation a plain glyph takes: the chord across its advance."""
    return float(np.degrees(seg._frame.chord_angles(seg._s_left, seg._width_px)))


def test_places_one_artist_per_character():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 50)
    ct = curved_text(ax, x, np.sin(x), "abc", pos=0.5, anchor="center")
    assert len(ct._segments) == 3
    _draw(fig)
    assert all(t.get_visible() for t in ct._segments)
    plt.close(fig)


@pytest.mark.parametrize("ws", [" ", "\t", "\n"])
def test_whitespace_glyph_draws_nothing(ws):
    # A whitespace glyph advances the cursor but contributes no outline; without
    # the guard a tab or newline would render a visible ".notdef" box.
    verts, _ = _PlainGlyph(ws, ws, 0)._outline_units()
    assert len(verts) == 0
    assert len(_PlainGlyph("x", "x", 0)._outline_units()[0]) > 0


def test_plain_glyphs_share_one_baseline_on_a_slope():
    # The headline invariant: on a straight slanted guide every plain glyph rides
    # one baseline, so the cap tops are collinear -- there is no per-glyph
    # perpendicular "step". Alternating the two worst-case shapes (F and T differ
    # most in where their ink sits) the spread of the cap-top perpendicular
    # position across the whole label is sub-pixel. The superseded per-character
    # ``Text`` placement scattered these tops by ~4 px.
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.set_xlim(0.1, 0.9)
    ax.set_ylim(0.1, 0.9)
    ax.set_aspect("equal")
    ax.axis("off")
    curved_text(ax, [0.1, 0.9], [0.1, 0.9], "FTFTFT", fontsize=44, color="black")
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].mean(axis=2)
    H, _ = buf.shape
    ys, xs = np.where(buf < 100)
    px = xs.astype(float)
    py = (H - ys).astype(float)
    th = np.radians(45.0)
    d = np.array([np.cos(th), np.sin(th)])
    n = np.array([-np.sin(th), np.cos(th)])
    along = px * d[0] + py * d[1]
    perp = px * n[0] + py * n[1]
    # The cap-top perpendicular position per bin along the label; constant if the
    # baselines are collinear. Drop the partial leading/trailing bins.
    bins = np.linspace(along.min(), along.max(), 14)
    tops = []
    for i in range(13):
        m = (along >= bins[i]) & (along < bins[i + 1])
        if m.sum() > 40:
            tops.append(float(np.percentile(perp[m], 98)))
    tops = tops[1:-1]
    assert max(tops) - min(tops) < 1.5
    plt.close(fig)


def test_anchor_shifts_label_along_curve():
    # A straight horizontal curve so arc length maps to x directly.
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 1)
    x = np.linspace(0, 10, 100)
    y = np.full_like(x, 0.5)
    start = curved_text(ax, x, y, "word", pos=0.5, anchor="start")
    end = curved_text(ax, x, y, "word", pos=0.5, anchor="end")
    _draw(fig)
    # "start" puts the text to the right of "end" at the same pos.
    sx = _anchor_xy(start)[:, 0].mean()
    ex = _anchor_xy(end)[:, 0].mean()
    assert sx > ex
    plt.close(fig)


def test_offset_moves_perpendicular():
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 100)
    y = np.full_like(x, 5.0)
    flat = curved_text(ax, x, y, "word", pos=0.5, anchor="center", offset=0.0)
    lifted = curved_text(ax, x, y, "word", pos=0.5, anchor="center", offset=10.0)
    _draw(fig)
    fy = _anchor_xy(flat)[:, 1].mean()
    ly = _anchor_xy(lifted)[:, 1].mean()
    # Positive offset is above a left-to-right curve.
    assert ly > fy
    plt.close(fig)


def test_offset_is_dpi_invariant_in_points():
    # The offset is specified in typographic points, so the same point value must
    # produce the same data-space displacement regardless of figure DPI.
    def displacement(dpi):
        fig, ax = plt.subplots(dpi=dpi)
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        x = np.linspace(0, 10, 100)
        y = np.full_like(x, 5.0)
        flat = curved_text(ax, x, y, "word", pos=0.5, anchor="center", offset=0.0)
        lifted = curved_text(ax, x, y, "word", pos=0.5, anchor="center",
                             offset=10.0)
        _draw(fig)
        fy = _anchor_xy(flat)[:, 1].mean()
        ly = _anchor_xy(lifted)[:, 1].mean()
        plt.close(fig)
        return ly - fy

    assert displacement(72) == pytest.approx(displacement(144), rel=0.02)


def _fit_circle(xy):
    """Least-squares circle through points; returns (center, radius, rms)."""
    x, y = xy[:, 0], xy[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    cx2, cy2, c = np.linalg.lstsq(A, x**2 + y**2, rcond=None)[0]
    cx, cy = cx2 / 2.0, cy2 / 2.0
    r = np.sqrt(c + cx**2 + cy**2)
    rms = np.sqrt(np.mean((np.hypot(x - cx, y - cy) - r) ** 2))
    return (cx, cy), r, rms


def _clearance_px(ax, ct, gx, gy):
    """Perpendicular distance, in display pixels, from each glyph center to the
    guide polyline."""
    pts = ax.transData.transform(np.column_stack([gx, gy]))
    seg = pts[1:] - pts[:-1]
    seg2 = np.einsum("ij,ij->i", seg, seg)
    out = []
    for s in ct._segments:
        p = _anchor_px(s)
        t = np.clip(np.einsum("ij,ij->i", p - pts[:-1], seg) / seg2, 0.0, 1.0)
        proj = pts[:-1] + t[:, None] * seg
        out.append(np.hypot(*(p - proj).T).min())
    return np.asarray(out)


def test_offset_is_parallel_curve_on_circle():
    # A perpendicular offset of a circular guide must be a concentric arc:
    # the fitted radius shifts by the offset while the center stays put. The
    # superseded single-chord offset translated the label instead, leaving the
    # radius at 1.0 and moving the center.
    t = np.linspace(np.pi, 0, 400)
    gx, gy = np.cos(t), np.sin(t)
    fig, ax = plt.subplots(dpi=150)
    ax.set_aspect("equal")
    ax.set_xlim(-1.7, 1.7)
    ax.set_ylim(-0.4, 1.9)
    ax.plot(gx, gy)
    _draw(fig)

    radii = {}
    gaps = {}
    for off in (0.0, 40.0, -40.0):
        ct = curved_text(ax, gx, gy, "ABCDEFGHIJKLMNOP", offset=off, fontsize=14)
        _draw(fig)
        centers = _anchor_xy(ct)
        center, radii[off], rms = _fit_circle(centers)
        # Glyph centers lie on a circle (concentric, not translated)...
        assert rms < 0.01
        # ...sharing the guide's center.
        assert center == pytest.approx((0.0, 0.0), abs=0.02)
        gaps[off] = np.hypot(*np.diff(centers, axis=0).T).mean()
    # Outward and inward offsets are symmetric about the unit radius.
    d = radii[40.0] - 1.0
    assert d > 0.05
    assert radii[-40.0] == pytest.approx(1.0 - d, abs=0.01)
    # Laying the label along the offset curve keeps the letter spacing even:
    # the mean center-to-center gap is unchanged by the offset (the label
    # occupies a smaller angular span on the larger arc, not a stretched one).
    assert gaps[40.0] == pytest.approx(gaps[0.0], rel=0.02)
    assert gaps[-40.0] == pytest.approx(gaps[0.0], rel=0.02)
    plt.close(fig)


def test_offset_clearance_is_uniform_on_asymmetric_curve():
    # On a steep, asymmetrically curved guide (a Gaussian flank) the offset must
    # hold a constant perpendicular clearance end to end. The single-chord
    # offset crowded the gentler end and floated the steeper one.
    gx = np.linspace(86, 126, 140)
    gy = 10.0 * np.exp(-0.5 * ((gx - 127) / 20) ** 2)
    fig, ax = plt.subplots(dpi=150)
    ax.set_xlim(0, 255)
    ax.set_ylim(-3.3, 11)
    ax.plot(gx, gy)
    _draw(fig)
    ct = curved_text(ax, gx, gy, "recovered signal", offset=10.0, fontsize=12)
    _draw(fig)
    clear = _clearance_px(ax, ct, gx, gy)
    expected = 10.0 * fig.dpi / 72.0
    assert clear.mean() == pytest.approx(expected, rel=0.02)
    # Uniform to a small fraction of the clearance, not the ~30% the single
    # global offset vector produced here.
    assert (clear.max() - clear.min()) / clear.mean() < 0.03
    plt.close(fig)


def test_offset_anchor_is_measured_on_base_curve():
    # pos/anchor are given against the original curve, so an offset label must
    # sit perpendicularly off the spot pos marks on the bare curve -- not off
    # the spot at the same arc fraction of the longer/shorter offset curve. A
    # parabola sampled asymmetrically makes the two fractions differ.
    x = np.linspace(-1.2, 0.8, 200)
    y = x**2
    fig, ax = plt.subplots(dpi=150)
    ax.set_aspect("equal")
    ax.set_xlim(-1.6, 1.2)
    ax.set_ylim(-0.4, 1.8)
    ax.plot(x, y)
    _draw(fig)
    pos = 0.35
    ct = curved_text(ax, x, y, "o", pos=pos, anchor="center", offset=14.0,
                     fontsize=14)
    _draw(fig)
    center = _anchor_px(ct._segments[0])
    # Foot of the perpendicular from the glyph center onto the base curve, as an
    # arc-length fraction; it must land at pos.
    base = ax.transData.transform(np.column_stack([x, y]))
    seg = base[1:] - base[:-1]
    seg2 = np.einsum("ij,ij->i", seg, seg)
    t = np.clip(np.einsum("ij,ij->i", center - base[:-1], seg) / seg2, 0.0, 1.0)
    feet = base[:-1] + t[:, None] * seg
    j = int(np.argmin(np.hypot(*(center - feet).T)))
    arc = np.insert(np.cumsum(np.hypot(*seg.T)), 0, 0.0)
    foot_arc = arc[j] + t[j] * (arc[j + 1] - arc[j])
    assert foot_arc / arc[-1] == pytest.approx(pos, abs=0.01)
    plt.close(fig)


def test_offset_on_straight_guide_is_rigid_translation():
    # Where the guide is straight the local normal is the chord normal
    # everywhere, so the parallel-curve offset must still shift every glyph by
    # one identical vector -- numerically unchanged from the prior behaviour.
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 100)
    y = np.full_like(x, 5.0)
    flat = curved_text(ax, x, y, "word", pos=0.5, anchor="center", offset=0.0)
    lifted = curved_text(ax, x, y, "word", pos=0.5, anchor="center", offset=8.0)
    _draw(fig)
    shifts = _anchor_xy(lifted) - _anchor_xy(flat)
    # Every glyph moves by the same displacement, purely vertical (the curve
    # runs horizontally, so the normal is +y).
    assert shifts[:, 0] == pytest.approx(0.0, abs=1e-9)
    assert shifts[:, 1] == pytest.approx(shifts[0, 1], abs=1e-9)
    assert shifts[0, 1] > 0.0
    plt.close(fig)


def test_math_run_offset_rides_offset_curve():
    # The math run rides the same offset curve as the plain glyphs. Centered at
    # the top of a circular guide, the run's outline centroid sits directly
    # above the guide center; offsetting moves it radially out (or in) by the
    # offset distance, holding its horizontal position. A rigid translation (the
    # superseded behaviour) would shift it by a fixed vector regardless of where
    # on the curve the run sat.
    t = np.linspace(np.pi, 0, 400)
    gx, gy = np.cos(t), np.sin(t)
    fig, ax = plt.subplots(dpi=150)
    ax.set_aspect("equal")
    ax.set_xlim(-1.7, 1.7)
    ax.set_ylim(-0.4, 1.9)
    ax.plot(gx, gy)
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    center_px = ax.transData.transform((0.0, 0.0))

    def centroid(off):
        ct = curved_text(ax, gx, gy, "$x^2+y^2$", offset=off, fontsize=18)
        _draw(fig)
        return _math_runs(ct)[0]._placed_path(renderer).vertices.mean(axis=0)

    c0, cup, cdn = centroid(0.0), centroid(40.0), centroid(-40.0)
    expected = 40.0 * fig.dpi / 72.0
    # Radial distance from the guide center grows by the offset outward and
    # shrinks by it inward (concentric, not a fixed translation).
    r0 = np.hypot(*(c0 - center_px))
    assert np.hypot(*(cup - center_px)) - r0 == pytest.approx(expected, rel=0.05)
    assert np.hypot(*(cdn - center_px)) - r0 == pytest.approx(-expected, rel=0.05)
    # At the top of the circle the move is vertical: horizontal drift stays small.
    assert abs(cup[0] - c0[0]) < 0.05 * expected
    plt.close(fig)


def test_overrun_is_not_clipped():
    # Anchor the start of a long label past the right end of a short curve; the
    # overrunning glyphs should ride the tangent extension, all still visible.
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 20)
    ct = curved_text(ax, x, np.zeros_like(x), "a long label", pos=1.0,
                     anchor="start")
    _draw(fig)
    assert all(t.get_visible() for t in ct._segments)
    plt.close(fig)


def test_left_overrun_is_not_clipped():
    # The symmetric case: anchor the end of a long label before the left end of a
    # short curve so the label rides the left tangent extension.
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 20)
    ct = curved_text(ax, x, np.zeros_like(x), "a long label", pos=0.0,
                     anchor="end")
    _draw(fig)
    assert all(t.get_visible() for t in ct._segments)
    plt.close(fig)


def test_glyph_rotation_smooths_across_vertices():
    # A coarse polyline with one sharp vertex: flat, then rising. A glyph whose
    # advance straddles the vertex must take the angle of the chord across its
    # own advance -- strictly between the two segment tangents -- rather than
    # snapping to whichever segment its midpoint falls in.
    fig, ax = plt.subplots(figsize=(8, 6), dpi=100)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.array([0.0, 5.0, 10.0])
    y = np.array([0.0, 0.0, 5.0])
    # Wide glyphs centered near the vertex so one of them straddles it.
    ct = curved_text(ax, x, y, "mmmm", pos=0.5, anchor="center", fontsize=24)
    _draw(fig)
    pts = ax.transData.transform(np.column_stack([x, y]))
    rising = np.degrees(np.arctan2(pts[2, 1] - pts[1, 1], pts[2, 0] - pts[1, 0]))
    rots = [_rotation_deg(t) for t in ct._segments]
    # The flat segment's tangent is 0; every rotation stays within the two
    # segment tangents, and the straddling glyph lands strictly between them.
    assert all(-0.1 <= r <= rising + 0.1 for r in rots)
    assert any(1.0 < r < rising - 1.0 for r in rots)
    plt.close(fig)


def test_degenerate_curve_does_not_raise():
    # A curve whose points are all identical has zero arc length; drawing must
    # short-circuit cleanly rather than raising.
    fig, ax = plt.subplots()
    x = np.full(10, 3.0)
    y = np.full(10, 3.0)
    ct = curved_text(ax, x, y, "abc", pos=0.5, anchor="center")
    _draw(fig)
    assert len(ct._segments) == 3
    plt.close(fig)


def test_wrapper_matches_class():
    # curved_text is a thin wrapper; for the same inputs the two forms must place
    # glyphs identically despite the different argument order.
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 1)
    x = np.linspace(0, 10, 100)
    y = np.full_like(x, 0.5)
    via_fn = curved_text(ax, x, y, "word", pos=0.5, anchor="center")
    via_cls = CurvedText(x, y, "word", ax, pos=0.5, anchor="center")
    _draw(fig)
    for a, b in zip(_anchor_xy(via_fn), _anchor_xy(via_cls)):
        assert a == pytest.approx(b)
    plt.close(fig)


def test_set_zorder_lifts_glyphs_above_container():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    ct = curved_text(ax, x, np.zeros_like(x), "ab", pos=0.5, anchor="center")
    ct.set_zorder(5)
    assert ct.get_zorder() == 5
    assert all(t.get_zorder() == 6 for t in ct._segments)
    plt.close(fig)


def test_remove_drops_child_glyphs():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    ct = curved_text(ax, x, np.zeros_like(x), "ab", pos=0.5, anchor="center")
    chars = list(ct._segments)
    ct.remove()
    children = ax.get_children()
    assert ct not in children
    assert all(t not in children for t in chars)
    plt.close(fig)


def test_redraw_is_idempotent():
    # Layout is recomputed every draw; two draws of an unchanged figure must yield
    # the same glyph positions.
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 100)
    ct = curved_text(ax, x, np.sin(x) + 5.0, "stable", pos=0.5, anchor="center",
                     offset=8.0)
    _draw(fig)
    first = _anchor_xy(ct)
    _draw(fig)
    second = _anchor_xy(ct)
    for a, b in zip(first, second):
        assert a == pytest.approx(b)
    plt.close(fig)


def test_validates_inputs():
    fig, ax = plt.subplots()
    with pytest.raises(ValueError):
        CurvedText([0.0], [0.0], "x", ax)            # too few points
    with pytest.raises(ValueError):
        CurvedText([0, 1], [0, 1], "x", ax, anchor="middle")  # bad anchor
    with pytest.raises(ValueError):
        CurvedText([0, 1, 2], [0, 1], "x", ax)       # unequal lengths
    with pytest.raises(ValueError):
        CurvedText(np.zeros((2, 3)), np.zeros((2, 3)), "x", ax)  # 2-D
    plt.close(fig)


def test_rejects_non_finite_input():
    fig, ax = plt.subplots()
    with pytest.raises(ValueError):
        CurvedText([0.0, np.nan, 1.0], [0.0, 0.0, 0.0], "x", ax)
    with pytest.raises(ValueError):
        CurvedText([0.0, 1.0], [0.0, np.inf], "x", ax)
    plt.close(fig)


def test_split_runs_mixed_string():
    assert _split_runs(r"flux $\propto D$ end") == [
        (False, "flux "), (True, r"$\propto D$"), (False, " end")]


def test_split_runs_odd_dollar_count_is_literal():
    # matplotlib renders strings with an odd number of unescaped dollar signs
    # as literal text; the tokenizer must not split them.
    assert _split_runs("cost $5") == [(False, "cost $5")]


def test_split_runs_unescapes_dollar_in_plain_text():
    # matplotlib renders \$ in non-math text as a dollar sign.
    assert _split_runs(r"cost \$5") == [(False, "cost $5")]
    assert _split_runs(r"$a$ \$ $b$") == [
        (True, "$a$"), (False, " $ "), (True, "$b$")]


def test_split_runs_adjacent_and_math_only():
    # No empty plain run between adjacent math runs, and a math-only string
    # yields exactly one run.
    assert _split_runs("$a$$b$") == [(True, "$a$"), (True, "$b$")]
    assert _split_runs("$a$") == [(True, "$a$")]


def test_math_run_becomes_single_segment():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 50)
    ct = curved_text(ax, x, np.sin(x), r"ab $x^2$ c")
    # "ab " and " c" stay per-character; the run is one segment.
    assert len(ct._segments) == 6
    runs = _math_runs(ct)
    assert len(runs) == 1
    assert runs[0].get_text() == r"$x^2$"
    _draw(fig)
    assert all(t.get_visible() for t in ct._segments)
    plt.close(fig)


def test_parse_math_false_disables_math_runs():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 50)
    ct = curved_text(ax, x, np.sin(x), "$x$", parse_math=False)
    assert len(ct._segments) == 3
    assert not _math_runs(ct)
    plt.close(fig)


def test_math_run_straight_line_reduces_to_affine():
    # On a straight horizontal curve every tangent angle is zero, so the bend
    # map must collapse to a plain affine: the layout scaled by the per-unit
    # pixel size, its left edge at the cursor, and its centre datum on the
    # curve. Reconstructing that affine from the run's own layout and matching
    # it vertex for vertex pins the unit scale, the datum, and the left anchor.
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 100)
    y = np.full_like(x, 5.0)
    s = r"$\propto\sqrt{D_{\mathrm{eff}}}$"
    ct = curved_text(ax, x, y, s, pos=0.5, anchor="center", fontsize=14)
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    run, = ct._segments
    verts, _ = run._outline_units()
    lines = _font_lines(run.get_fontproperties(), usetex=False)
    datum = _valign_datum(ct._valign, lines)
    per_unit = renderer.points_to_pixels(14.0) / 100.0
    # A horizontal curve maps data x to pixels linearly, so arc length s lands
    # at first_px + s; the run's left edge is at arc length run._s_left.
    first_px = ax.transData.transform((0.0, 5.0))[0]
    cy = ax.transData.transform((5.0, 5.0))[1]
    expected = np.column_stack([
        first_px + run._s_left + verts[:, 0] * per_unit,
        cy + (verts[:, 1] - datum) * per_unit])
    assert np.allclose(run._placed_path(renderer).vertices, expected, atol=1e-6)
    plt.close(fig)


@pytest.mark.parametrize("usetex", [False, pytest.param(True, marks=needs_latex)])
def test_math_run_aligns_to_plain_baseline(usetex):
    # Plain glyphs and math runs share one baseline by construction (the v=0
    # datum), so a math "x" and a plain "x" placed identically land on the same
    # baseline. On a straight line their ink bottoms (the baseline, neither glyph
    # has a descender) coincide tightly -- the alignment is structural, not the
    # tuned 2px tolerance the superseded x-height datum needed. It holds for
    # LaTeX layout under usetex as it does for mathtext.
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 100)
    y = np.full_like(x, 5.0)
    math_x = curved_text(ax, x, y, "$x$", pos=0.5, anchor="center", fontsize=16,
                         usetex=usetex)
    plain_x = curved_text(ax, x, y, "x", pos=0.5, anchor="center", fontsize=16,
                          usetex=usetex)
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    mb = math_x._segments[0]._placed_path(renderer).get_extents()
    pb = plain_x._segments[0]._placed_path(renderer).get_extents()
    # Baselines (ink bottoms) coincide.
    assert mb.y0 == pytest.approx(pb.y0, abs=1.0)
    plt.close(fig)


def test_superscript_does_not_drop_math_body():
    # A raised exponent must not drag the body down (the bug that put the math
    # run below neighbouring plain text). The body shares its baseline with the
    # exponent-free run; only the top extends to carry the exponent.
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 100)
    y = np.full_like(x, 5.0)
    plain = curved_text(ax, x, y, "$x$", pos=0.5, fontsize=20)
    raised = curved_text(ax, x, y, "$x^2$", pos=0.5, fontsize=20)
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    body = plain._segments[0]._placed_path(renderer).get_extents()
    with_exp = raised._segments[0]._placed_path(renderer).get_extents()
    assert with_exp.y0 == pytest.approx(body.y0, abs=1.5)
    assert with_exp.y1 > body.y1 + 2.0
    plt.close(fig)


def test_math_run_follows_tight_arc():
    # A wide expression on a tight half circle: every bent vertex must stay
    # within half the label height of the circle. The in-test sagitta check
    # proves the bound is discriminating: a rigid chord placement would sag
    # past it, so this can only pass if the outlines actually bend.
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-1.5, 1.5)
    ax.set_aspect("equal")
    theta = np.linspace(np.pi, 0, 300)
    ct = curved_text(ax, np.cos(theta), np.sin(theta),
                     r"$\sqrt{abcde}\,/\,\sqrt{vwxyz}$",
                     pos=0.5, anchor="center", fontsize=20)
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    run, = ct._segments
    bent = run._placed_path(renderer)
    center = ax.transData.transform((0.0, 0.0))
    radius = ax.transData.transform((1.0, 0.0))[0] - center[0]
    width, _ = run._size_px(renderer)
    # Derive the bound from the run's actual outline reach above and below the
    # baseline datum it rides on, mapped to pixels exactly as the bend map does.
    # Tying the bound to the same geometry the placement uses keeps it robust to
    # matplotlib mathtext metric changes; half the window-extent height is a
    # different reference frame (the box midpoint, not the baseline) and only
    # happened to sit just above the true reach.
    verts, _ = run._outline_units()
    lines = _font_lines(run.get_fontproperties(), usetex=False)
    datum = _valign_datum(ct._valign, lines)
    px_per_unit = (renderer.points_to_pixels(run.get_fontsize())
                   / _text_to_path.FONT_SCALE)
    reach = np.abs(verts[:, 1] - datum).max() * px_per_unit
    bound = reach + 2.0
    half_span = width / 2.0 / radius  # half the label arc, radians
    sagitta = radius * (1.0 - np.cos(half_span))
    assert sagitta > bound + 4.0, "test geometry too gentle to discriminate"
    radii = np.hypot(*(bent.vertices - center).T)
    assert np.all(np.abs(radii - radius) <= bound)
    plt.close(fig)


def test_math_run_offset_moves_perpendicular_in_points():
    # The offset is in typographic points along the chord normal, identical to
    # the plain-character behaviour.
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 100)
    y = np.full_like(x, 5.0)
    flat = curved_text(ax, x, y, "$x^2$", pos=0.5, anchor="center", offset=0.0)
    lifted = curved_text(ax, x, y, "$x^2$", pos=0.5, anchor="center",
                         offset=10.0)
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    fy = flat._segments[0]._placed_path(renderer).get_extents()
    ly = lifted._segments[0]._placed_path(renderer).get_extents()
    expected = 10.0 * fig.dpi / 72.0
    assert ly.y0 - fy.y0 == pytest.approx(expected, abs=0.05)
    assert ly.x0 == pytest.approx(fy.x0, abs=0.05)
    plt.close(fig)


def test_math_run_geometry_is_dpi_invariant():
    # Layout happens in display space, so the data-space footprint of the bent
    # expression must not depend on figure DPI.
    def data_bbox(dpi):
        fig, ax = plt.subplots(dpi=dpi)
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        x = np.linspace(0, 10, 100)
        ct = curved_text(ax, x, np.sin(x) + 5.0, r"$\sqrt{x^2}$", pos=0.5,
                         anchor="center")
        _draw(fig)
        bent = ct._segments[0]._placed_path(fig.canvas.get_renderer())
        data = ax.transData.inverted().transform(bent.vertices)
        box = (data[:, 0].min(), data[:, 0].max(),
               data[:, 1].min(), data[:, 1].max())
        plt.close(fig)
        return box

    for a, b in zip(data_bbox(72), data_bbox(144)):
        assert a == pytest.approx(b, rel=0.02)


def test_math_run_orders_with_plain_characters():
    # On a straight left-to-right curve the run occupies exactly the gap
    # between its plain neighbours.
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 100)
    y = np.full_like(x, 5.0)
    ct = curved_text(ax, x, y, r"ab$x^2$cd", pos=0.5, anchor="center")
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    bent = ct._segments[2]._placed_path(renderer).get_extents()
    b_x = _anchor_px(ct._segments[1])[0]
    c_x = _anchor_px(ct._segments[3])[0]
    assert b_x < (bent.x0 + bent.x1) / 2.0 < c_x
    plt.close(fig)


def test_math_run_fontsize_scales_path():
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 100)
    y = np.full_like(x, 5.0)
    small = curved_text(ax, x, y, "$x^2$", pos=0.5, fontsize=12)
    large = curved_text(ax, x, y, "$x^2$", pos=0.5, fontsize=24)
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    hs = small._segments[0]._placed_path(renderer).get_extents().height
    hl = large._segments[0]._placed_path(renderer).get_extents().height
    assert hl / hs == pytest.approx(2.0, rel=0.1)
    plt.close(fig)


def test_math_run_overrun_rides_tangent_extension():
    # A math label anchored past the right end of a short straight curve rides
    # the tangent extension at the curve's height, like plain characters do. Under
    # the default centre alignment the run straddles the extension, so its vertical
    # centre sits at the curve's height.
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 1, 20)
    y = np.full_like(x, 5.0)
    ct = curved_text(ax, x, y, r"$\propto D^2$", pos=1.0, anchor="start")
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    run, = ct._segments
    assert run.get_visible()
    bent = run._placed_path(renderer).get_extents()
    end_x, end_y = ax.transData.transform((1.0, 5.0))
    assert bent.x0 >= end_x - 1.0
    assert (bent.y0 + bent.y1) / 2.0 == pytest.approx(end_y, abs=3.0)
    plt.close(fig)


def test_math_run_redraw_is_idempotent():
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 100)
    ct = curved_text(ax, x, np.sin(x) + 5.0, r"a $\frac{x}{y}$ b", pos=0.5,
                     offset=6.0)
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    first = _math_runs(ct)[0]._placed_path(renderer).vertices.copy()
    _draw(fig)
    second = _math_runs(ct)[0]._placed_path(renderer).vertices
    assert np.allclose(first, second)
    plt.close(fig)


def test_degenerate_curve_with_math_does_not_raise():
    # Zero arc length short-circuits before any frame is handed out; the run
    # must quietly draw nothing rather than raising.
    fig, ax = plt.subplots()
    x = np.full(10, 3.0)
    ct = curved_text(ax, x, x, "$x^2$", pos=0.5, anchor="center")
    _draw(fig)
    assert len(ct._segments) == 1
    plt.close(fig)


def test_math_run_path_effects_clears_line_behind_it():
    # A withStroke halo must reach the mathtext run, not only the per-character
    # glyphs (the run draws its own path and would otherwise skip path effects).
    # Draw a thick black line through a math run with and without the white
    # halo; the halo must whiten pixels along the line where the glyphs sit.
    import matplotlib.patheffects as pe

    def dark_pixels_under_label(use_halo):
        fig, ax = plt.subplots()
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        x = np.linspace(0, 10, 100)
        y = np.full_like(x, 5.0)
        ax.plot(x, y, color="black", linewidth=10)
        halo = [pe.withStroke(linewidth=10, foreground="white")]
        kw = {"path_effects": halo} if use_halo else {}
        run = curved_text(ax, x, y, r"$\sqrt{xy}$", pos=0.5, anchor="center",
                          fontsize=22, color="red", **kw)._segments[0]
        fig.canvas.draw()
        bbox = run._placed_path(fig.canvas.get_renderer()).get_extents()
        buf = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
        height = buf.shape[0]
        # Buffer rows run top-down; the path extent is bottom-up, so flip y.
        x0, x1 = int(bbox.x0), int(np.ceil(bbox.x1))
        y0, y1 = height - int(np.ceil(bbox.y1)), height - int(bbox.y0)
        region = buf[max(y0, 0):y1, max(x0, 0):x1]
        dark = int(np.all(region < 80, axis=-1).sum())
        plt.close(fig)
        return dark

    assert dark_pixels_under_label(use_halo=True) < \
        dark_pixels_under_label(use_halo=False)


def test_box_creates_and_removes_casing():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    plain = curved_text(ax, x, np.zeros_like(x), "ab")
    assert plain._box is None
    boxed = curved_text(ax, x, np.zeros_like(x), "ab", box=True)
    assert boxed._box is not None and boxed._box in ax.get_lines()
    casing = boxed._box
    boxed.remove()
    assert casing not in ax.get_lines()
    plt.close(fig)


def test_box_config_color_and_pad():
    import matplotlib.colors as mcolors

    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    red = curved_text(ax, x, np.zeros_like(x), "ab", box="red")
    assert mcolors.to_rgba(red._box.get_color()) == mcolors.to_rgba("red")
    tuned = curved_text(ax, x, np.zeros_like(x), "ab",
                        box=dict(color="yellow", pad=1.5))
    assert mcolors.to_rgba(tuned._box.get_color()) == mcolors.to_rgba("yellow")
    assert tuned._box_pad == 1.5
    plt.close(fig)


def test_box_rejects_unknown_keys():
    # An unknown dict key (a typo) must raise rather than silently vanish.
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    with pytest.raises(ValueError):
        curved_text(ax, x, np.zeros_like(x), "ab", box=dict(colour="red"))
    plt.close(fig)


def test_box_hidden_on_degenerate_redraw():
    # A box that drew once must not stay painted with stale geometry when a
    # later draw hits a degenerate curve (zero arc length in display space).
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 50)
    ct = curved_text(ax, x, np.full_like(x, 5.0), "label", pos=0.5, box=True)
    _draw(fig)
    assert ct._box.get_visible()
    # Collapse the curve to a single point, then redraw. There is no public
    # setter for the curve, so drop its converted copy too.
    ct._cx = np.full_like(ct._cx, 5.0)
    ct._cy = np.full_like(ct._cy, 5.0)
    ct._forget_curve_floats()
    _draw(fig)
    assert not ct._box.get_visible()
    plt.close(fig)


def test_box_sits_below_glyphs_in_zorder():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    ct = curved_text(ax, x, np.zeros_like(x), "ab", box=True)
    ct.set_zorder(5)
    assert all(t.get_zorder() == 6 for t in ct._segments)
    assert ct._box.get_zorder() < min(t.get_zorder() for t in ct._segments)
    plt.close(fig)


def test_box_covers_line_behind_label():
    # The casing must mask the line the label rides, including behind plain
    # per-character text (where a wide path_effects stroke would fail). Draw a
    # thick black line through the label; with the box almost no dark line
    # pixels survive inside the label's footprint.
    def dark_pixels_under_label(use_box):
        fig, ax = plt.subplots()
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        x = np.linspace(0, 10, 100)
        y = np.full_like(x, 5.0)
        ax.plot(x, y, color="black", linewidth=8)
        ct = curved_text(ax, x, y, "coverage", pos=0.5, anchor="center",
                         fontsize=22, color="red", box=use_box)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        # Footprint of the actually-drawn outlines (the segments render their own
        # paths, and their own window extents are empty).
        verts = np.vstack([p.vertices for p in
                           (s._placed_path(renderer) for s in ct._segments)
                           if p is not None])
        x0 = int(verts[:, 0].min())
        x1 = int(np.ceil(verts[:, 0].max()))
        y0 = int(verts[:, 1].min())
        y1 = int(np.ceil(verts[:, 1].max()))
        buf = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
        height = buf.shape[0]
        region = buf[max(height - y1, 0):height - y0, max(x0, 0):x1]
        dark = int(np.all(region < 80, axis=-1).sum())
        plt.close(fig)
        return dark

    assert dark_pixels_under_label(use_box=True) < \
        dark_pixels_under_label(use_box=False) / 4


def test_set_zorder_and_remove_cover_math_runs():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    ct = curved_text(ax, x, np.zeros_like(x), r"a$b$c", pos=0.5)
    ct.set_zorder(5)
    assert all(t.get_zorder() == 6 for t in ct._segments)
    segments = list(ct._segments)
    ct.remove()
    children = ax.get_children()
    assert ct not in children
    assert all(t not in children for t in segments)
    plt.close(fig)


def test_valign_rejects_unknown_value():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    with pytest.raises(ValueError, match="valign must be one of"):
        curved_text(ax, x, np.zeros_like(x), "ab", valign="middle")
    plt.close(fig)


# Ascender over units per em, from the font files matplotlib bundles.
@pytest.mark.parametrize("family, ascender_em", [
    ("DejaVu Sans", 1901 / 2048),
    ("STIXGeneral", 1055 / 1000),
])
def test_valign_shifts_label_perpendicular_uniformly(family, ascender_em):
    # valign picks which line rides the curve. On a straight horizontal guide,
    # "ascender" puts the label below "baseline" (its ascender line is pulled down
    # onto the curve), and the shift is the same constant for every glyph -- the
    # datum is a font metric, not a per-glyph box, so it introduces no step. The
    # shift is the ascender of the font the label names, which differs between
    # the default DejaVu Sans and STIXGeneral.
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 100)
    y = np.full_like(x, 5.0)
    kwargs = dict(pos=0.5, fontsize=20, fontfamily=family)
    base = curved_text(ax, x, y, "nnnn", valign="baseline", **kwargs)
    asc = curved_text(ax, x, y, "nnnn", valign="ascender", **kwargs)
    _draw(fig)
    r = fig.canvas.get_renderer()
    shifts = np.array([
        sa._placed_path(r).vertices.mean(axis=0)[1]
        - sb._placed_path(r).vertices.mean(axis=0)[1]
        for sb, sa in zip(base._segments, asc._segments)])
    assert shifts.std() < 0.5          # identical shift per glyph: no step
    em_px = r.points_to_pixels(20)
    assert shifts.mean() == pytest.approx(-ascender_em * em_px, abs=0.005 * em_px)
    plt.close(fig)


@pytest.mark.parametrize("valign, box, measurements", [
    ("baseline", False, 0),
    ("baseline", True, 1),
    ("center", False, 1),
    ("ascender", True, 1),
])
def test_font_lines_are_measured_only_when_needed(monkeypatch, valign, box,
                                                  measurements):
    # Under usetex, measuring the font lines runs LaTeX. A draw therefore
    # measures them only when a line other than the baseline or the box casing
    # needs them, and then once, however many of the two need them.
    calls = []

    def counting(prop, *, usetex):
        calls.append(usetex)
        return _font_lines(prop, usetex=usetex)

    monkeypatch.setattr(_core, "_font_lines", counting)
    fig, _ = _flat_label("label", valign=valign, box=box)
    assert calls == [False] * measurements  # the label is not usetex
    plt.close(fig)


@pytest.mark.parametrize("family, pair, reference", [
    ("DejaVu Sans", "AV", "AB"),
    ("DejaVu Sans", "To", "Tx"),
    # STIXGeneral keeps its kerning only in the GPOS table, which matplotlib
    # reads from 3.11 on (through HarfBuzz) and ignores before.
    ("STIXGeneral", "AV", "AB"),
])
def test_plain_glyphs_are_kerned_as_matplotlib_lays_out_text(family, pair,
                                                              reference):
    # Each plain glyph's span includes the kern toward the next glyph, so the
    # second glyph of a pair starts where matplotlib's own layout puts it.
    # Comparing against a reference pair cancels the first glyph's own width,
    # which some matplotlib versions round to whole pixels.
    fontsize = 30

    def second_glyph_offsets(text):
        fig, ct = _flat_label(text, fontsize=fontsize, fontfamily=family)
        renderer = fig.canvas.get_renderer()
        first, second = ct._segments
        prop = first.get_fontproperties()
        font = font_manager.get_font(font_manager.findfont(prop))
        font.set_size(_text_to_path.FONT_SCALE, _text_to_path.DPI)
        glyphs = _text_to_path.get_glyphs_with_font(font, text)[0]
        px_per_unit = (renderer.points_to_pixels(fontsize)
                       / _text_to_path.FONT_SCALE)
        plt.close(fig)
        return second._s_left - first._s_left, glyphs[1][1] * px_per_unit

    ours, matplotlibs = second_glyph_offsets(pair)
    ours_ref, matplotlibs_ref = second_glyph_offsets(reference)
    if family == "DejaVu Sans":  # kerned by every supported matplotlib
        assert ours - ours_ref < -1.0
    assert ours - ours_ref == pytest.approx(matplotlibs - matplotlibs_ref, abs=0.01)


@pytest.mark.parametrize("text, kwargs", [
    ("A$V$", {}),
    ("$A$V", {}),
    # matplotlib 3.11 shapes text through HarfBuzz: it attaches the accent over
    # the "q", forms an "fi" ligature, hides the soft hyphen, reorders the
    # Hebrew pair, and rounds every advance. None of that is a kern, and cmr10
    # has no kerning at all, so its pair must come out exactly zero.
    ("q\u0301V", {}),
    ("fi", {}),
    ("A\u00adV", {}),
    ("\u05d0\u05d1", {}),
    ("Ba", {"fontfamily": "cmr10"}),
])
def test_kern_is_zero_where_no_plain_pair_is_kerned(text, kwargs):
    # Only two consecutive plain glyphs set by matplotlib are kerned, and only
    # by the font's kerning. A math run and every other effect of shaping take
    # no kern, so the label spaces exactly as without kerning.
    fig, ct = _flat_label(text, **kwargs)
    kerns = ct._kerns_px(fig.canvas.get_renderer())
    plt.close(fig)
    assert kerns == [0.0] * len(ct._segments)


@pytest.mark.parametrize("axis, scale, kwargs", [
    ("y", "logit", {}),
    ("y", "log", {"nonpositive": "mask"}),
    ("x", "log", {"nonpositive": "mask"}),
], ids=["logit", "log_y_mask", "log_x_mask"])
def test_label_draws_on_scales_without_a_data_origin(axis, scale, kwargs):
    # The container measures each glyph at its unused Text position. On a
    # logit axis, and on a log axis that masks non-positive values, the data
    # origin has no pixel, so a position there gave every glyph a NaN width
    # and the label was not drawn. Every point of the curve is valid for the
    # scale, so the label draws inside the axes, its glyphs as wide as on a
    # linear axis.
    def label(set_scale):
        fig, ax = plt.subplots()
        x = np.linspace(1, 100, 50)
        y = np.linspace(0.1, 0.9, 50)
        ax.plot(x, y)
        if set_scale:
            getattr(ax, f"set_{axis}scale")(scale, **kwargs)
        ct = curved_text(ax, x, y, "label text")
        _draw(fig)
        return fig, ct

    fig, ct = label(set_scale=True)
    linear_fig, linear_ct = label(set_scale=False)
    renderer = fig.canvas.get_renderer()
    linear_renderer = linear_fig.canvas.get_renderer()
    for seg, linear_seg in zip(ct._segments, linear_ct._segments):
        np.testing.assert_allclose(seg._size_px(renderer),
                                   linear_seg._size_px(linear_renderer))
    extent = ct.get_window_extent(renderer)
    axes_box = ct.axes.get_window_extent(renderer)
    assert np.isfinite(extent.get_points()).all()
    assert axes_box.contains(extent.x0, extent.y0)
    assert axes_box.contains(extent.x1, extent.y1)
    plt.close(fig)
    plt.close(linear_fig)


def test_label_draws_on_polar_axes_whose_radius_starts_above_zero():
    # On polar axes whose radial limits start above zero, the data origin lies
    # below the radial limit and has no pixel either, through a transform that
    # is not separable into x and y scales like those above.
    fig, ax = plt.subplots(subplot_kw={"projection": "polar"})
    ax.set_rlim(1, 10)
    theta = np.linspace(0.5, 2.5, 50)
    ct = curved_text(ax, theta, np.full_like(theta, 5.0), "label text")
    _draw(fig)
    flat_fig, flat_ct = _flat_label("label text", fontsize=ct.get_fontsize())
    renderer = fig.canvas.get_renderer()
    flat_renderer = flat_fig.canvas.get_renderer()
    for seg, flat_seg in zip(ct._segments, flat_ct._segments):
        np.testing.assert_allclose(seg._size_px(renderer),
                                   flat_seg._size_px(flat_renderer))
    extent = ct.get_window_extent(renderer)
    axes_box = ax.get_window_extent(renderer)
    assert np.isfinite(extent.get_points()).all()
    assert axes_box.contains(extent.x0, extent.y0)
    assert axes_box.contains(extent.x1, extent.y1)
    plt.close(fig)
    plt.close(flat_fig)


# A curve of 50 daily dates, the values a time series plots against them, and
# 50 category strings.
_DAYS = np.datetime64("2017-09-24") + np.arange(50) * np.timedelta64(1, "D")
_WAVE = np.sin(np.linspace(0, 2 * np.pi, 50))
_CATEGORIES = [f"c{i}" for i in range(50)]
# The label every unit test draws, and its float twin draws to match it.
_UNIT_LABEL = {"text": "unit-typed curve", "offset": 6, "box": True}


def _unit_label(x, y, **kwargs):
    """A boxed label on the curve ``x, y``, over the line ``plot`` draws from
    the same data, with the axes' limits fixed where autoscaling put them;
    return the figure, the label, and the line. ``kwargs`` go to the label."""
    fig, ax = plt.subplots(figsize=(6, 4))
    (line,) = ax.plot(x, y)
    ax.set_xlim(ax.get_xlim())
    ax.set_ylim(ax.get_ylim())
    ct = curved_text(ax, x, y, **_UNIT_LABEL, **kwargs)
    return fig, ct, line


def _float_twin(line):
    """The same label on ``line``'s data as its axes converted it, in a float
    figure of the same size, dpi, and limits; return the figure and label."""
    ax = line.axes
    fig, ref_ax = plt.subplots(figsize=ax.figure.get_size_inches(),
                               dpi=ax.figure.dpi)
    ref_ax.set_xlim(ax.get_xlim())
    ref_ax.set_ylim(ax.get_ylim())
    xy = line.get_xydata()
    ct = curved_text(ref_ax, xy[:, 0], xy[:, 1], **_UNIT_LABEL)
    return fig, ct


def _assert_same_placement(fig, ct, ref_fig, ref_ct):
    """Draw both figures and check that both labels place every glyph and
    their casings at the same display pixels."""
    _draw(fig)
    _draw(ref_fig)
    renderer = fig.canvas.get_renderer()
    ref_renderer = ref_fig.canvas.get_renderer()
    assert len(ct._segments) == len(ref_ct._segments)
    for seg, ref_seg in zip(ct._segments, ref_ct._segments):
        path = seg._placed_path(renderer)
        ref_path = ref_seg._placed_path(ref_renderer)
        if ref_path is None:
            assert path is None
            continue
        np.testing.assert_allclose(path.vertices, ref_path.vertices, atol=1e-6)
    np.testing.assert_allclose(
        ct._box.get_transform().transform(ct._box.get_xydata()),
        ref_ct._box.get_transform().transform(ref_ct._box.get_xydata()),
        atol=1e-6)


_UNIT_CURVES = [
    pytest.param(_DAYS.astype("datetime64[s]"), _WAVE, id="datetime64[s]"),
    pytest.param(_DAYS.astype("datetime64[us]"), _WAVE, id="datetime64[us]"),
    pytest.param(_DAYS.astype("datetime64[ns]"), _WAVE, id="datetime64[ns]"),
    pytest.param(list(_DAYS.astype("datetime64[us]").astype(datetime.datetime)),
                 _WAVE, id="datetime list"),
    pytest.param(pd.DatetimeIndex(_DAYS), _WAVE, id="DatetimeIndex"),
    pytest.param(pd.DatetimeIndex(_DAYS).tz_localize("Europe/Madrid"), _WAVE,
                 id="aware DatetimeIndex"),
    pytest.param(pd.Series(_DAYS, index=np.arange(100, 150)), _WAVE,
                 id="date Series"),
    pytest.param(_CATEGORIES, _WAVE, id="categories on x"),
    pytest.param(_WAVE, _DAYS.astype("datetime64[us]"), id="dates on y"),
    pytest.param(_WAVE, _CATEGORIES, id="categories on y"),
]


@pytest.mark.parametrize("x, y", _UNIT_CURVES)
def test_unit_typed_curve_matches_float_curve(x, y):
    # The axes convert the curve as they convert the plotted line, so a label
    # on dates, categories, or pandas data draws exactly as one on the line's
    # own converted data, casing included. Cast straight to float, datetime64
    # gives raw counts since 1970, and datetime objects and strings raise.
    fig, ct, line = _unit_label(x, y)
    ref_fig, ref_ct = _float_twin(line)
    _assert_same_placement(fig, ct, ref_fig, ref_ct)
    plt.close(fig)
    plt.close(ref_fig)


@pytest.mark.parametrize("x", [_DAYS.astype("datetime64[us]"), _CATEGORIES],
                         ids=["dates", "categories"])
def test_label_before_any_plot_sets_up_the_axis_units(x):
    # A label made on empty axes sets up the axis units itself, as plot does:
    # the axis formats dates or categories, not plain numbers, and a line
    # plotted afterwards shares its units. Without the setup, categories on
    # empty axes cannot be converted at all.
    fig, ax = plt.subplots(figsize=(6, 4))
    ct = curved_text(ax, x, _WAVE, **_UNIT_LABEL)
    assert not isinstance(ax.xaxis.get_major_formatter(), mticker.ScalarFormatter)
    (line,) = ax.plot(x, _WAVE)
    ax.set_xlim(ax.get_xlim())
    ax.set_ylim(ax.get_ylim())
    ref_fig, ref_ct = _float_twin(line)
    _assert_same_placement(fig, ct, ref_fig, ref_ct)
    plt.close(fig)
    plt.close(ref_fig)


@pytest.mark.parametrize("drawn_first", [True, False],
                         ids=["after a draw", "before the first draw"])
def test_label_follows_a_change_of_axis_units(monkeypatch, drawn_first):
    # A change of axis units drops the converted curve, so after the axis
    # switches from kilometres to metres the label stays on the line. The
    # label keeps the curve converted at construction, so this holds before
    # its first draw too.
    monkeypatch.setitem(munits.registry, jpl_units.UnitDbl,
                        jpl_units.UnitDblConverter())
    x = [jpl_units.UnitDbl(value, "km") for value in np.linspace(1, 9, 50)]
    fig, ct, line = _unit_label(x, _WAVE)
    if drawn_first:
        _draw(fig)
    ct.axes.xaxis.set_units("m")
    ct.axes.set_xlim(600, 9400)
    ref_fig, ref_ct = _float_twin(line)
    _assert_same_placement(fig, ct, ref_fig, ref_ct)
    plt.close(fig)
    plt.close(ref_fig)


def test_label_converts_its_curve_once_until_the_units_change(monkeypatch):
    # Drawing and measuring reuse the converted curve, as matplotlib's lines
    # do, so a long curve of datetime objects is not converted again on every
    # measurement; a change of the axis units converts it again.
    monkeypatch.setitem(munits.registry, jpl_units.UnitDbl,
                        jpl_units.UnitDblConverter())
    x = [jpl_units.UnitDbl(value, "km") for value in np.linspace(1, 9, 50)]
    fig, ct, _ = _unit_label(x, _WAVE)
    axis = ct.axes.xaxis
    convert_units = axis.convert_units
    conversions = []

    def counting_convert_units(values):
        if values is ct._cx:
            conversions.append(values)
        return convert_units(values)

    monkeypatch.setattr(axis, "convert_units", counting_convert_units)
    _draw(fig)
    _draw(fig)
    ct.get_window_extent(fig.canvas.get_renderer())
    assert not conversions
    axis.set_units("m")
    _draw(fig)
    assert len(conversions) == 1
    plt.close(fig)


def test_unpickled_label_follows_a_change_of_axis_units(monkeypatch):
    # A pickled figure drops the label's unit callbacks, so the unpickled
    # label connects them again and still follows the axis from kilometres
    # to metres, as the plotted line does.
    monkeypatch.setitem(munits.registry, jpl_units.UnitDbl,
                        jpl_units.UnitDblConverter())
    x = [jpl_units.UnitDbl(value, "km") for value in np.linspace(1, 9, 50)]
    fig, _, _ = _unit_label(x, _WAVE)
    _draw(fig)
    fig = pickle.loads(pickle.dumps(fig))
    ax = fig.axes[0]
    (ct,) = [text for text in ax.texts if isinstance(text, CurvedText)]
    # Placed once after unpickling, the label converts its curve again and
    # keeps it, so only reconnected callbacks can tell it of the change.
    _draw(fig)
    ax.xaxis.set_units("m")
    ax.set_xlim(600, 9400)
    ref_fig, ref_ct = _float_twin(ax.lines[0])
    _assert_same_placement(fig, ct, ref_fig, ref_ct)
    plt.close(fig)
    plt.close(ref_fig)


def test_removed_label_disconnects_only_its_own_unit_callbacks():
    # Removing a label disconnects its unit callbacks and no others, even
    # after the axes' callback registries were replaced, as clearing the axes
    # replaces them; the new registries' ids start again and can repeat the
    # removed label's.
    def units_callbacks(ax):
        return [len(axis.callbacks.callbacks.get("units", {}))
                for axis in (ax.xaxis, ax.yaxis)]

    fig, ax = plt.subplots()
    x = np.linspace(1, 9, 50)
    before = units_callbacks(ax)
    removed = curved_text(ax, x, _WAVE, "removed")
    assert units_callbacks(ax) == [count + 1 for count in before]
    for axis in (ax.xaxis, ax.yaxis):
        axis.callbacks = cbook.CallbackRegistry()
    kept = [curved_text(ax, x, _WAVE, f"kept {index}") for index in range(2)]
    removed.remove()
    assert units_callbacks(ax) == [2, 2]
    for label in kept:
        label.remove()
    assert units_callbacks(ax) == [0, 0]
    plt.close(fig)


def test_label_with_a_box_it_cannot_draw_leaves_the_axes_alone():
    # The casing is built before the label touches the axes, so a box color
    # matplotlib cannot draw raises without adding a half-made label or
    # setting up the axis units, and the figure still draws.
    fig, ax = plt.subplots()
    with pytest.raises(ValueError):
        curved_text(ax, _DAYS, _WAVE, "label", box="not-a-colour")
    assert not ax.texts
    assert not ax.lines
    assert not ax.xaxis.have_units()
    _draw(fig)
    plt.close(fig)


def test_day_dates_follow_the_date_epoch():
    # Days since 1970 match matplotlib's date numbers only under the default
    # epoch; the axis converter follows any epoch. matplotlib fixes the epoch
    # at its first date conversion, so the test resets it with matplotlib's
    # own test helper, before and after, where rc_context would not reach it.
    mdates._reset_epoch_test_example()
    mdates.set_epoch("2000-01-01T00:00:00")
    try:
        fig, ct, line = _unit_label(_DAYS, _WAVE)
        ref_fig, ref_ct = _float_twin(line)
        _assert_same_placement(fig, ct, ref_fig, ref_ct)
        plt.close(fig)
        plt.close(ref_fig)
    finally:
        mdates._reset_epoch_test_example()


def test_label_position_is_the_callers_first_point():
    # The label's own Text position is the curve's first point as given, and
    # its unitless position is that point on the axis, as for any Text.
    x = _DAYS.astype("datetime64[us]")
    fig, ct, _ = _unit_label(x, _WAVE)
    assert ct.get_position()[0] == x[0]
    assert ct.get_unitless_position()[0] == pytest.approx(mdates.date2num(x[0]))
    plt.close(fig)


def test_float_series_without_a_zero_index_draws():
    # The first point is taken by position; a pandas Series indexes by label.
    index = np.arange(10, 60)
    fig, ct, line = _unit_label(pd.Series(np.linspace(1, 9, 50), index=index),
                                pd.Series(_WAVE, index=index))
    ref_fig, ref_ct = _float_twin(line)
    _assert_same_placement(fig, ct, ref_fig, ref_ct)
    plt.close(fig)
    plt.close(ref_fig)


def test_label_adds_only_new_categories_to_the_axis():
    # As for ax.text and plot, categories already on the axis keep their
    # places and new ones are added after them, as ticks.
    def tick_labels(ax):
        _draw(ax.figure)
        return [tick.get_text() for tick in ax.get_xticklabels()]

    fig, ax = plt.subplots()
    ax.plot(["a", "b", "c", "d"], [0, 1, 2, 3])
    curved_text(ax, ["b", "c"], [1, 2], "on plotted categories")
    assert tick_labels(ax) == ["a", "b", "c", "d"]
    curved_text(ax, ["d", "e"], [3, 4], "on a new category")
    assert tick_labels(ax) == ["a", "b", "c", "d", "e"]
    plt.close(fig)


def test_data_the_axis_cannot_convert_raises_and_keeps_the_axis_converter():
    # Strings on a date axis raise matplotlib's ConversionError when the label
    # is made. The label adds nothing to the axes, the date axis keeps its
    # converter, and the y axis, which comes after the x axis that raised, is
    # not set up for the label's strings.
    fig, ax = plt.subplots()
    (line,) = ax.plot(_DAYS, _WAVE)
    with pytest.raises(munits.ConversionError):
        curved_text(ax, _CATEGORIES, _CATEGORIES, "strings on dates")
    assert not ax.texts
    np.testing.assert_allclose(ax.xaxis.convert_units(_DAYS),
                               mdates.date2num(_DAYS))
    assert not ax.yaxis.have_units()
    _draw(fig)
    assert np.isfinite(line.get_xydata()).all()
    plt.close(fig)


def test_masked_points_are_rejected():
    # A masked point is not finite once converted. Cast straight to float, the
    # value under the mask placed the label instead.
    fig, ax = plt.subplots()
    y = np.ma.masked_array(_WAVE, mask=np.arange(50) == 10)
    with pytest.raises(ValueError, match="finite"):
        curved_text(ax, np.arange(50.0), y, "masked")
    plt.close(fig)


def test_label_keeps_its_curve_when_the_callers_array_changes():
    # The label keeps a copy of the curve, as Line2D does, so changing the
    # caller's array after the label is made does not move it.
    x = np.linspace(1, 9, 50)
    fig, ct, line = _unit_label(x, _WAVE)
    ref_fig, ref_ct = _float_twin(line)
    x += 100.0
    _assert_same_placement(fig, ct, ref_fig, ref_ct)
    plt.close(fig)
    plt.close(ref_fig)


def test_unit_typed_label_is_measured_and_picked_before_a_draw():
    # Figure layout measures the label, and a click picks it, before the first
    # draw has placed it; both place it through the same conversion as a draw.
    fig, ct, line = _unit_label(_DAYS.astype("datetime64[us]"), _WAVE,
                                picker=True)
    ref_fig, ref_ct = _float_twin(line)
    _draw(ref_fig)
    assert ct.contains(_click(fig, *_first_glyph_centre(ref_ct)))[0]
    np.testing.assert_allclose(
        ct.get_window_extent(fig.canvas.get_renderer()).get_points(),
        ref_ct.get_window_extent(ref_fig.canvas.get_renderer()).get_points(),
        atol=1e-6)
    plt.close(fig)
    plt.close(ref_fig)


def test_unclipped_label_keeps_the_tight_bounding_box():
    # The container positions each glyph when it draws, so a glyph's own Text
    # position, the display origin, is not where it appears. An unclipped label
    # must leave figure layout alone; glyphs measured at the origin would
    # stretch a tight bounding box to the figure's lower left corner.
    def tight_bounds(label):
        fig, ax = plt.subplots(figsize=(4, 3))
        x = np.linspace(100, 110, 50)
        ax.plot(x, 100 + np.sin(x))
        if label:
            curved_text(ax, x, 100 + np.sin(x), "far from the origin",
                        clip_on=False)
        _draw(fig)
        bounds = fig.get_tightbbox(fig.canvas.get_renderer()).bounds
        plt.close(fig)
        return bounds

    np.testing.assert_allclose(tight_bounds(True), tight_bounds(False))


def _rising_label(clip_on, layout=None, label=True, **kwargs):
    """A figure whose label's curve rises past the top of the axes, beyond the
    curve's first point; return the figure and the label, or None with
    ``label=False`` for the same figure without it. ``kwargs`` go to the
    label."""
    fig, ax = plt.subplots(figsize=(4, 3), layout=layout)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    if not label:
        return fig, None
    x = np.linspace(1, 9, 50)
    ct = curved_text(ax, x, 10.5 + 0.6 * (x - 1), "a label rising above the axes",
                     fontsize=14, clip_on=clip_on, **kwargs)
    return fig, ct


def _tight_top_px(fig):
    """The top of the figure's tight bounding box, in display pixels."""
    bbox = fig.get_tightbbox(fig.canvas.get_renderer())
    return bbox.transformed(fig.dpi_scale_trans).y1


def test_unclipped_label_outside_the_axes_is_in_the_tight_bounding_box():
    # An unclipped label is drawn wherever its curve goes, so figure layout
    # must reach its ink, as it reaches matplotlib's own unclipped text. The
    # label is measured by its glyphs' control points, which can exceed the ink
    # but never fall short of it.
    fig, ct = _rising_label(clip_on=False)
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    ink = Bbox.union([seg._placed_path(renderer).get_extents()
                      for seg in ct._segments if not seg._char.isspace()])
    top = _tight_top_px(fig)
    assert ink.y1 <= top + 0.01
    assert top - ink.y1 < 2.0
    plt.close(fig)


def test_clipped_label_outside_the_axes_leaves_the_tight_bounding_box():
    # A clipped label is cut at the axes, as clipped text is, so figure layout
    # leaves it out, as matplotlib does for clipped artists.
    fig, _ = _rising_label(clip_on=True)
    plain, _ = _rising_label(clip_on=True, label=False)
    _draw(fig)
    _draw(plain)
    assert _tight_top_px(fig) == pytest.approx(_tight_top_px(plain))
    plt.close(fig)
    plt.close(plain)


def test_constrained_layout_makes_room_for_an_unclipped_label():
    # Constrained layout measures the label before the first draw has placed
    # it, so the label is placed to be measured, and the axes shrink for it on
    # the first draw. The label's top sits well above the figure's, so the axes
    # move down by a tenth of the figure or more.
    fig, ct = _rising_label(clip_on=False, layout="constrained")
    plain, _ = _rising_label(clip_on=False, layout="constrained", label=False)
    _draw(fig)
    _draw(plain)
    assert ct.axes.get_position().y1 < plain.axes[0].get_position().y1 - 0.1
    plt.close(fig)
    plt.close(plain)


def test_label_extent_scales_with_dpi():
    # The placement scales with the figure's dpi, so the extent asked for at
    # twice the dpi matches the label placed at twice the dpi, to within what
    # whole-pixel glyph widths add up to along the label (matplotlib 3.11
    # rounds each one), here 2% of its width.
    fig, ct = _rising_label(clip_on=False)
    _draw(fig)
    dpi = fig.dpi
    scaled = ct.get_window_extent(fig.canvas.get_renderer(), dpi=2 * dpi)
    fig.set_dpi(2 * dpi)
    _draw(fig)
    placed = ct.get_window_extent(fig.canvas.get_renderer())
    np.testing.assert_allclose(scaled.get_points(), placed.get_points(),
                               atol=0.02 * placed.width)
    plt.close(fig)


def test_label_extent_without_a_renderer_matches_the_figure_dpi(tmp_path):
    # A canvas such as PDF makes a renderer only while drawing, at 72 dpi.
    # Measured without a renderer, the label is placed at the figure's own dpi,
    # so it measures as on an Agg canvas, before a draw and after one.
    fig, ct = _rising_label(clip_on=False)
    expected = ct.get_window_extent(fig.canvas.get_renderer()).get_points()
    FigureCanvasPdf(fig)
    np.testing.assert_allclose(ct.get_window_extent().get_points(), expected)
    fig.savefig(tmp_path / "label.pdf")
    np.testing.assert_allclose(ct.get_window_extent().get_points(), expected)
    plt.close(fig)


def test_label_extent_follows_the_axes_between_draws():
    # A measurement reuses the last placement only while the curve lands where
    # it did on the canvas. After the axes' limits change, the label is placed
    # again to be measured, and the extent matches the next draw's.
    fig, ct = _rising_label(clip_on=False)
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    before = ct.get_window_extent(renderer).get_points()
    ct.axes.set_ylim(0, 20)
    measured = ct.get_window_extent(renderer).get_points()
    _draw(fig)
    drawn = ct.get_window_extent(renderer).get_points()
    assert not np.allclose(measured, before)
    np.testing.assert_allclose(measured, drawn)
    plt.close(fig)


_LEGEND_MEASURES_TEXT = pytest.mark.skipif(
    tuple(int(part) for part in mpl.__version__.split(".")[:2]) < (3, 10),
    reason="a legend placed at 'best' measures texts from matplotlib 3.10")


@_LEGEND_MEASURES_TEXT
def test_legend_measures_the_label_without_placing_it_again(monkeypatch):
    # A legend placed at "best" measures every text in the axes after the
    # labels have drawn. The measurement reuses each label's placement from
    # that draw, so each label is measured but placed once per draw.
    placements, measurements = [], []
    place = CurvedText._place_on_curve
    measure = CurvedText.get_window_extent

    def counting_place(self, renderer, curve_px):
        placements.append(self)
        return place(self, renderer, curve_px)

    def counting_measure(self, renderer=None, dpi=None):
        measurements.append(self)
        return measure(self, renderer, dpi)

    monkeypatch.setattr(CurvedText, "_place_on_curve", counting_place)
    monkeypatch.setattr(CurvedText, "get_window_extent", counting_measure)
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 50)
    for k in range(3):
        ax.plot(x, x + k, label=f"line {k}")
        curved_text(ax, x, x + k, f"label {k}")
    ax.legend(loc="best")
    _draw(fig)
    placements.clear()
    measurements.clear()
    _draw(fig)
    assert len(measurements) >= 3
    assert len(placements) == 3
    plt.close(fig)


@_LEGEND_MEASURES_TEXT
def test_legend_avoids_the_label_not_its_glyphs_unused_position():
    # A legend placed at "best" measures every text in the axes, the glyph
    # segments included. A segment counts as part of its label, not at its
    # unused Text position, the display origin, here the axes' lower left
    # corner, so with a line across the top the legend goes to the lower left,
    # the first free corner in matplotlib's order of preference.
    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 50)
    ax.plot(x, np.full_like(x, 9.5), label="line")
    curved_text(ax, np.linspace(4, 6, 20), np.full(20, 5.0), "label in the middle")
    legend = ax.legend(loc="best")
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    box = legend.get_window_extent(renderer)
    axes_box = ax.get_window_extent(renderer)
    assert box.x0 < axes_box.x0 + 0.25 * axes_box.width
    assert box.y0 < axes_box.y0 + 0.25 * axes_box.height
    plt.close(fig)


def test_label_extent_follows_a_change_to_its_glyphs_between_draws():
    # A measurement reuses the last placement only while the glyphs it placed
    # are unchanged. After their font size changes, the label is placed again
    # to be measured, and the extent matches the next draw's.
    fig, ct = _rising_label(clip_on=False)
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    before = ct.get_window_extent(renderer)
    plt.setp(ct._segments, fontsize=20)
    measured = ct.get_window_extent(renderer)
    _draw(fig)
    drawn = ct.get_window_extent(renderer)
    assert measured.width > 1.2 * before.width
    np.testing.assert_allclose(measured.get_points(), drawn.get_points())
    plt.close(fig)


def _red_pixels_above_axes(fig, ax):
    """Draw the figure and count the strongly red pixels above its axes."""
    _draw(fig)
    image = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].astype(int)
    rows_above = image.shape[0] - int(np.ceil(ax.bbox.y1))
    red, green, blue = image[:rows_above].transpose(2, 0, 1)
    return int(((red > 200) & (green < 80) & (blue < 80)).sum())


def test_hidden_label_hides_its_glyphs_and_takes_no_room():
    # The container draws nothing itself, so hiding it hides every part it
    # draws, and its extent is empty, as matplotlib's own hidden text takes no
    # room. Shown again, it draws and measures as before.
    fig, ct = _rising_label(clip_on=False)
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    shown = ct.get_window_extent(renderer)
    ct.set_visible(False)
    assert not any(seg.get_visible() for seg in ct._segments)
    hidden = ct.get_window_extent(renderer)
    assert hidden.width == hidden.height == 0
    ct.set_visible(True)
    _draw(fig)
    np.testing.assert_allclose(ct.get_window_extent(renderer).get_points(),
                               shown.get_points())
    plt.close(fig)


@pytest.mark.parametrize("hide_at_construction", [False, True],
                         ids=["hidden_afterwards", "hidden_at_construction"])
def test_hidden_label_hides_its_casing(hide_at_construction):
    # Visibility reaches the casing whether the label is hidden when it is
    # made, through the keyword, or afterwards.
    kwargs = {"visible": False} if hide_at_construction else {}
    fig, ct = _flat_label("label", box="red", **kwargs)
    if not hide_at_construction:
        ct.set_visible(False)
    _draw(fig)
    assert not ct._box.get_visible()
    assert not any(seg.get_visible() for seg in ct._segments)
    plt.close(fig)


def test_unclipped_label_keeps_its_casing_outside_the_axes():
    # The casing follows the label's clipping, so an unclipped label that
    # leaves the axes keeps its casing behind it there, and a clipped one has
    # it cut at the axes edge along with its glyphs.
    def red_above(clip_on):
        fig, ct = _rising_label(clip_on, box="red")
        count = _red_pixels_above_axes(fig, ct.axes)
        plt.close(fig)
        return count

    assert red_above(clip_on=False) > 1000
    assert red_above(clip_on=True) == 0


def test_clipping_set_after_construction_reaches_every_part():
    fig, ct = _flat_label("label $x$", box=True)
    parts = [*ct._segments, ct._box]
    ct.set_clip_on(False)
    assert not any(part.get_clip_on() for part in parts)
    ct.set_clip_on(True)
    assert all(part.get_clip_on() for part in parts)
    circle = plt.Circle((5, 5), 2, transform=ct.axes.transData)
    ct.set_clip_path(circle)
    assert all(part.get_clip_path() is not None for part in parts)
    clip_box = ct.axes.bbox
    ct.set_clip_box(clip_box)
    assert all(part.get_clip_box() is clip_box for part in parts)
    plt.close(fig)


def test_label_out_of_layout_takes_its_casing_with_it():
    # The label measures its casing, so the casing never enters figure layout
    # on its own: a label taken out of layout leaves a tight bounding box as
    # it is without the label, casing and all.
    fig, ct = _rising_label(clip_on=False, box="red")
    ct.set_in_layout(False)
    plain, _ = _rising_label(clip_on=False, label=False)
    _draw(fig)
    _draw(plain)
    assert _tight_top_px(fig) == pytest.approx(_tight_top_px(plain))
    plt.close(fig)
    plt.close(plain)


def test_casing_is_part_of_the_label_extent():
    # A drawn casing is part of the label, so the extent reaches its band:
    # half its line width beyond its centreline, past the glyphs on every side.
    def extent(box):
        fig, ct = _flat_label("label", fontsize=14, box=box)
        bbox = ct.get_window_extent(fig.canvas.get_renderer())
        plt.close(fig)
        return bbox

    plain, cased = extent(False), extent({"pad": 2.0})
    assert cased.x0 < plain.x0 - 5 and cased.x1 > plain.x1 + 5
    assert cased.y0 < plain.y0 - 5 and cased.y1 > plain.y1 + 5


def _picking_label(picker):
    """A label with ``picker``; return the figure, the label, and the artists
    picked so far."""
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(1, 9, 50)
    ct = curved_text(ax, x, np.full_like(x, 5.0), "label", fontsize=20,
                     picker=picker)
    picked = []
    fig.canvas.mpl_connect("pick_event", lambda event: picked.append(event.artist))
    _draw(fig)
    return fig, ct, picked


def _click(fig, x_px, y_px):
    """A left-button press at display pixel ``(x_px, y_px)``."""
    return MouseEvent("button_press_event", fig.canvas, x_px, y_px, button=1)


def _first_glyph_centre(ct):
    """The display-pixel centre of the label's first placed glyph."""
    renderer = ct.figure.canvas.get_renderer()
    return ct._segments[0]._placed_path(renderer).get_extents().get_points().mean(
        axis=0)


def test_label_is_picked_on_its_glyphs():
    # Picking and hover test a point against the label's placed glyphs, so a
    # click on a glyph hits the label and a click in empty space does not. The
    # glyph segments take the forwarded picker too, but never answer a pick
    # themselves, so a click just inside their unused Text box at the display
    # origin, outside every axes, where matplotlib still asks the axes'
    # children, picks nothing, and no segment contains it for hover.
    fig, ct, picked = _picking_label(picker=True)
    ax = ct.axes
    on_glyph = _click(fig, *_first_glyph_centre(ct))
    empty = _click(fig, *ax.transData.transform((1.0, 1.0)))
    inside_segment_text_box = _click(fig, 3.0, 3.0)
    assert ct.contains(on_glyph)[0]
    assert not ct.contains(empty)[0]
    fig.canvas.callbacks.process("button_press_event", on_glyph)
    assert picked == [ct]
    fig.canvas.callbacks.process("button_press_event", inside_segment_text_box)
    assert picked == [ct]
    assert not any(seg.contains(inside_segment_text_box)[0] for seg in ct._segments)
    ct.set_visible(False)
    assert not ct.contains(on_glyph)[0]
    plt.close(fig)


def test_label_picked_by_a_picker_function_is_never_a_glyph():
    # matplotlib asks a picker function without calling ``contains``, and the
    # label's picker reaches every glyph segment. A function that tests each
    # artist's own extent picks the label on its glyphs, and never a segment,
    # whose empty extent would otherwise answer every click.
    def by_extent(artist, mouseevent):
        hit = artist.get_window_extent().contains(mouseevent.x, mouseevent.y)
        return hit, {}

    fig, ct, picked = _picking_label(picker=by_extent)
    origin = _click(fig, 3.0, 3.0)
    fig.canvas.callbacks.process("button_press_event", origin)
    assert picked == []
    fig.canvas.callbacks.process("button_press_event",
                                 _click(fig, *_first_glyph_centre(ct)))
    assert picked == [ct]
    plt.close(fig)


def test_label_is_picked_where_it_moved_without_a_draw():
    # Panning moves the label before the next draw, and picking places it
    # again to test the click, so the glyph's new position hits and its old
    # one misses.
    fig, ct, _ = _picking_label(picker=True)
    ax = ct.axes
    old_centre = _first_glyph_centre(ct)
    data_point = ax.transData.inverted().transform(old_centre)
    ax.set_xlim(2, 12)
    new_centre = ax.transData.transform(data_point)
    assert not ct.contains(_click(fig, *old_centre))[0]
    assert ct.contains(_click(fig, *new_centre))[0]
    plt.close(fig)


def test_degenerate_curve_has_an_empty_extent():
    # A curve with no length cannot be laid out, so the label takes no room.
    fig, ax = plt.subplots()
    ct = curved_text(ax, [5.0, 5.0], [5.0, 5.0], "label", clip_on=False)
    _draw(fig)
    extent = ct.get_window_extent(fig.canvas.get_renderer())
    assert extent.width == extent.height == 0
    plt.close(fig)


def test_outline_is_cached_until_its_font_changes(monkeypatch):
    # Each segment caches its outline on its text, font, and usetex setting.
    # A redraw reuses every outline, and a change to one glyph's font rebuilds
    # that glyph alone. A broken cache key would either rebuild on every draw
    # or keep drawing the old outline. The change is to the weight: outlines
    # are in em units, so without usetex a size change leaves them identical
    # and could not show a stale one.
    builds = []
    build = _PlainGlyph._build_outline

    def counting(self, prop, text, usetex):
        builds.append(text)
        return build(self, prop, text, usetex)

    monkeypatch.setattr(_PlainGlyph, "_build_outline", counting)
    fig, ct = _flat_label("ab")
    assert builds == ["a", "b"]
    _draw(fig)
    assert builds == ["a", "b"]
    regular = ct._segments[0]._outline_units()[0]
    ct._segments[0].set_fontweight("bold")
    _draw(fig)
    assert builds == ["a", "b", "a"]
    bold = ct._segments[0]._outline_units()[0]
    assert bold.shape != regular.shape or not np.array_equal(bold, regular)
    plt.close(fig)


def test_crowding_rejects_unknown_value():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    with pytest.raises(ValueError, match="crowding must be one of"):
        curved_text(ax, x, np.zeros_like(x), "abc", crowding="wedge")
    plt.close(fig)


def test_crowding_none_leaves_glyph_positions_unchanged():
    # The default mode must be byte-for-byte the un-widened layout, so the
    # curvature path is purely opt-in.
    fig, ax = plt.subplots()
    x = np.linspace(0, 2 * np.pi, 200)
    y = np.sin(x)
    default = curved_text(ax, x, y, "following", pos=0.5)
    explicit = curved_text(ax, x, y, "following", pos=0.5, crowding="none")
    _draw(fig)
    for a, b in zip(_anchor_xy(default), _anchor_xy(explicit)):
        assert a == pytest.approx(b)
    for a, b in zip(default._segments, explicit._segments):
        assert _rotation_deg(a) == pytest.approx(_rotation_deg(b))
    plt.close(fig)


def test_crowding_curvature_leaves_straight_line_unchanged():
    # A straight guide has zero curvature everywhere, so widening is a no-op and
    # the two modes must place glyphs identically.
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 1)
    x = np.linspace(0, 10, 100)
    y = np.full_like(x, 0.5)
    flat = curved_text(ax, x, y, "straight", pos=0.5, crowding="none")
    bent = curved_text(ax, x, y, "straight", pos=0.5, crowding="curvature")
    _draw(fig)
    for a, b in zip(_anchor_xy(flat), _anchor_xy(bent)):
        assert a[0] == pytest.approx(b[0])
    plt.close(fig)


def _end_to_end(ct):
    a = _anchor_xy(ct)
    return np.hypot(a[-1, 0] - a[0, 0], a[-1, 1] - a[0, 1])


def test_crowding_curvature_spreads_glyphs_on_a_tight_bend():
    # On a bend tight enough to crowd the letters (a small displayed radius next
    # to a large font), the curvature mode widens advances past the deadband, so
    # the label spans a longer stretch of curve: its first and last glyph sit
    # farther apart than in the un-widened layout.
    fig, ax = plt.subplots()
    ax.set_aspect("equal")
    ax.set_xlim(-10, 10)
    ax.set_ylim(-2, 10)
    th = np.linspace(np.pi, 0.0, 300)
    x, y = np.cos(th), np.sin(th)
    flat = curved_text(ax, x, y, "concave", pos=0.5, fontsize=26,
                       crowding="none")
    bent = curved_text(ax, x, y, "concave", pos=0.5, fontsize=26,
                       crowding="curvature")
    _draw(fig)
    assert _end_to_end(bent) > _end_to_end(flat)
    plt.close(fig)


def test_crowding_curvature_is_negligible_on_a_gentle_bend():
    # The deadband must keep a gentle bend (where the letters are not actually
    # crowded) essentially unchanged, so the correction does not spread text
    # that has no overlap to fix.
    fig, ax = plt.subplots()
    ax.set_aspect("equal")
    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-0.1, 1.3)
    th = np.linspace(np.pi * 0.95, np.pi * 0.05, 400)
    x, y = np.cos(th), np.sin(th)
    flat = curved_text(ax, x, y, "Following Curve", pos=0.5, fontsize=14,
                       crowding="none")
    bent = curved_text(ax, x, y, "Following Curve", pos=0.5, fontsize=14,
                       crowding="curvature")
    _draw(fig)
    assert _end_to_end(bent) == pytest.approx(_end_to_end(flat), rel=0.01)
    plt.close(fig)


def _flat_label(text, fontsize=16, **kwargs):
    """Draw ``text`` centred on a flat line; return the figure and the label."""
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    # Under the text.usetex rcParam the tick labels would be usetex too, and
    # Agg rasterizes those through dvipng, which curved-text itself never needs.
    ax.set_axis_off()
    x = np.linspace(0, 10, 100)
    ct = curved_text(ax, x, np.full_like(x, 5.0), text, pos=0.5,
                     anchor="center", fontsize=fontsize, **kwargs)
    _draw(fig)
    return fig, ct


def _ink(ct, renderer, char):
    """Extents of the drawn outline of the plain glyph for ``char``."""
    seg = next(s for s in ct._segments
               if isinstance(s, _PlainGlyph) and s._char == char)
    return seg._placed_path(renderer).get_extents()


@needs_latex
def test_usetex_outline_matches_measured_design_at_any_size():
    # TeX fonts change design with size, and matplotlib measures a usetex
    # advance at the label's own size. Laying the outline out at a fixed size
    # instead draws a different design than the one measured: thinner letters
    # with loose tracking on small labels. With both at the label size, the
    # ink-to-advance ratio is the same at every size.
    ratios = []
    for fontsize in (8, 30):
        fig, ct = _flat_label("m", fontsize=fontsize, usetex=True)
        seg = ct._segments[0]
        ink = seg._placed_path(fig.canvas.get_renderer()).get_extents()
        ratios.append(ink.width / seg._width_px)
        plt.close(fig)
    assert ratios[0] == pytest.approx(ratios[1], rel=0.02)


@needs_latex
@pytest.mark.parametrize("fontsize", [8, 10, 30, 190])
def test_usetex_glyph_height_does_not_snap_to_the_pixel_grid(fontsize):
    # FreeType hints usetex glyphs on the converter's pixel grid. With a
    # 10-pixel em at 10 pt, the x-height snaps from 0.44 em to 0.50 em. With
    # the em spanning at least 100 pixels, the ink of "x" is as tall as the
    # height TeX gives it, which is the font's x-height at that size. At 190 pt
    # the exact DPI is 37.9, which FreeType would truncate to 37 and shrink the
    # glyph 2.8%, unless the DPI is a whole number.
    fig, ct = _flat_label("x", fontsize=fontsize, usetex=True)
    renderer = fig.canvas.get_renderer()
    ink = _ink(ct, renderer, "x")
    _, height, depth = TexManager().get_text_width_height_descent("x", fontsize)
    assert ink.height / renderer.points_to_pixels(fontsize) == pytest.approx(
        (height - depth) / fontsize, rel=0.015)
    plt.close(fig)


@needs_latex
@pytest.mark.parametrize("ws", [" ", "\t"])
def test_usetex_whitespace_advances_by_interword_space(ws):
    # matplotlib's DVI reader sizes its output from the glyphs and rules TeX
    # sets, so bare glue would advance zero and words would run together. TeX
    # reads a tab as a space, and its interword space is about a third of an em.
    fig, ct = _flat_label(f"a{ws}b", usetex=True)
    em_px = fig.canvas.get_renderer().points_to_pixels(16)
    assert ct._segments[1]._width_px == pytest.approx(em_px / 3, rel=0.1)
    plt.close(fig)


@needs_latex
def test_usetex_keyword_matches_rcparam():
    # A usetex keyword is forwarded to every segment and must select the same
    # layout, for both advance and outline, as the global rcParam. Paths are
    # read inside each label's own rcParam context, as a draw would.
    def placed(fig, ct):
        renderer = fig.canvas.get_renderer()
        paths = [seg._placed_path(renderer) for seg in ct._segments]
        return [p.vertices for p in paths if p is not None]

    fig_kw, by_kwarg = _flat_label("ab $x$", usetex=True)
    kw_paths = placed(fig_kw, by_kwarg)
    with mpl.rc_context({"text.usetex": True}):
        fig_rc, by_rc = _flat_label("ab $x$")
        rc_paths = placed(fig_rc, by_rc)
    # "a", "b", and "$x$" draw; the space does not.
    assert len(kw_paths) == len(rc_paths) == 3
    for kw, rc in zip(kw_paths, rc_paths):
        np.testing.assert_allclose(kw, rc)
    plt.close(fig_kw)
    plt.close(fig_rc)


@needs_latex
def test_container_set_usetex_does_not_move_the_label():
    # The usetex setting is fixed when the segments are built. Calling
    # set_usetex on the container afterwards changes nothing that is drawn, so
    # the valign lines must not switch to TeX's either; if they did, the label
    # would shift while its glyphs stayed in the matplotlib font.
    fig, ct = _flat_label("nnnn", fontsize=30, valign="ascender")
    renderer = fig.canvas.get_renderer()
    before = [seg._placed_path(renderer).vertices for seg in ct._segments]
    ct.set_usetex(True)
    _draw(fig)
    after = [seg._placed_path(renderer).vertices for seg in ct._segments]
    for b, a in zip(before, after):
        np.testing.assert_allclose(a, b)
    plt.close(fig)


@needs_latex
def test_usetex_plain_text_is_literal():
    # A plain glyph is one literal character, so every TeX markup character
    # must advance and draw instead of vanishing as a comment or stopping the
    # LaTeX run. The label holds a single "$", so it stays plain text. A
    # dollar sign drawn from a fixed-size layout came out about a third of its
    # height, so its ink is also checked against a plain "S".
    fig, ct = _flat_label("S" + _TEX_MARKUP, usetex=True)
    for seg in ct._segments:
        assert seg._width_px > 0, seg._char
        assert len(seg._outline_units()[0]) > 0, seg._char
    renderer = fig.canvas.get_renderer()
    dollar, s = _ink(ct, renderer, "$"), _ink(ct, renderer, "S")
    assert dollar.height == pytest.approx(s.height, rel=0.25)
    plt.close(fig)


@needs_latex
@pytest.mark.parametrize("char, ot1_twin", [("<", "!"), (">", "?")])
def test_usetex_relation_sign_is_not_ot1_punctuation(char, ot1_twin):
    # In TeX's default OT1 encoding "<" and ">" typeset as an inverted "!" and
    # "?", as narrow as their twins; escaped, they are full-width relation signs.
    fig, ct = _flat_label(char + ot1_twin, usetex=True)
    sign, twin = ct._segments
    assert sign._width_px > 1.3 * twin._width_px
    plt.close(fig)


@needs_latex
def test_usetex_bar_is_not_ot1_dash():
    # In OT1 "|" typesets as an em dash, which is wide and flat; the escaped
    # \textbar is a tall vertical bar.
    fig, ct = _flat_label("|", usetex=True)
    ink = _ink(ct, fig.canvas.get_renderer(), "|")
    assert ink.height > 2 * ink.width
    plt.close(fig)


@needs_latex
def test_usetex_plain_run_is_typeset_in_one_latex_pass(monkeypatch, tmp_path):
    # LaTeX typesets each plain run once, not once per distinct character.
    # Figure layout must not measure the glyphs one at a time either, so saving
    # with a tight bounding box asks LaTeX for nothing more, even for an
    # unclipped label, whose glyphs layout would otherwise measure. What remains
    # does not grow with the label: the run, the "lp" line box, and the "()gy"
    # font lines the default valign reads. The container's own text, a single
    # space, is not measured either. The run cache is emptied first, so the
    # run is asked for here.
    _core._typeset_tex_run.cache_clear()
    sources = set()
    make_dvi = TexManager.make_dvi

    def recording(*args):
        sources.add(args[-2])
        if inspect.ismethod(make_dvi):  # a classmethod from matplotlib 3.6 on
            return make_dvi(*args[-2:])
        return make_dvi(*args)

    monkeypatch.setattr(TexManager, "make_dvi", recording)
    fig, _ = _flat_label("Typography AVA", usetex=True, clip_on=False)
    fig.savefig(tmp_path / "label.png", bbox_inches="tight")
    plt.close(fig)
    assert not {_tex_source(char) for char in "Typography AV"} & sources
    assert len(sources) == 3


@needs_latex
@pytest.mark.parametrize("pair, reference", [("AV", "AB"), ("To", "Tx")])
def test_usetex_plain_glyphs_are_kerned_as_tex_sets_them(pair, reference):
    # TeX kerns "AV" and "To" within a run. The second glyph of each pair
    # starts where TeX's own layout of the pair puts it, closer than after a
    # reference letter.
    fontsize = 30

    def second_glyph_offsets(text):
        fig, ct = _flat_label(text, fontsize=fontsize, usetex=True)
        first, second = ct._segments
        converter = _tex_to_path(fontsize)
        glyphs = converter.get_glyphs_tex(
            font_manager.FontProperties(size=fontsize), text)[0]
        px_per_unit = (fig.canvas.get_renderer().points_to_pixels(fontsize)
                       / _text_to_path.FONT_SCALE * _layout_units(converter))
        plt.close(fig)
        return (second._s_left - first._s_left,
                (glyphs[1][1] - glyphs[0][1]) * px_per_unit)

    ours, tex = second_glyph_offsets(pair)
    ours_ref, _ = second_glyph_offsets(reference)
    assert ours - ours_ref < -1.0
    assert ours == pytest.approx(tex, abs=0.01)


@needs_latex
@pytest.mark.parametrize("text", [
    "office --- affluent",  # ligature pairs, kept one glyph per character
    "S" + _TEX_MARKUP,  # "\_" sets a rule, not a glyph
    " a  b ",  # spaces at either end and in a row
    "a\tb",  # a tab is whitespace, not a character that sets nothing
])
def test_usetex_run_sets_one_item_per_character(text):
    # Each printing character of a run takes its own glyph or rule from the
    # run's one LaTeX pass, and each space one interword space.
    fig, ct = _flat_label(text, usetex=True)
    em_px = fig.canvas.get_renderer().points_to_pixels(16)
    for seg in ct._segments:
        assert seg._run_layout() is not None
        assert seg._width_px > 0, seg._char
        if seg._char.isspace():
            assert seg._width_px == pytest.approx(em_px / 3, rel=0.1)
        else:
            assert len(seg._outline_units()[0]) > 0, seg._char
    plt.close(fig)


@needs_latex
def test_usetex_long_run_stays_on_one_line():
    # LaTeX sets text in a paragraph a few inches wide, so a long run would
    # break onto a second line and its items would interleave along the run.
    # Kept on one line, every character starts after the one before it.
    fig, ct = _flat_label("wavy line " * 30, fontsize=72, usetex=True)
    lefts = [seg._s_left for seg in ct._segments]
    assert ct._segments[0]._run_layout() is not None
    assert all(a < b for a, b in zip(lefts, lefts[1:]))
    plt.close(fig)


@needs_latex
@pytest.mark.parametrize("text", [
    # In the default OT1 encoding "\u00e9" sets an accent and a letter, two
    # items for one character.
    "caf\u00e9",
    # A soft hyphen sets nothing, so with "\u00e9" the counts would agree and
    # every item after them would pair with the wrong character.
    "caf\u00e9\u00adx",
])
def test_usetex_run_that_cannot_be_paired_is_typeset_per_character(text):
    # A run whose items cannot be paired with its characters is typeset one
    # character at a time, and its characters still advance in order.
    fig, ct = _flat_label(text, usetex=True)
    lefts = [seg._s_left for seg in ct._segments]
    assert all(seg._run_layout() is None for seg in ct._segments)
    assert all(seg._width_px > 0 for seg in ct._segments if seg._char.isalpha())
    assert lefts == sorted(lefts)
    assert len(_ink(ct, fig.canvas.get_renderer(), "\u00e9").bounds) == 4
    plt.close(fig)


@needs_latex
def test_usetex_run_glyph_height_matches_matplotlib_measuring_it_alone():
    # A glyph's height sizes its crowding gap and the box casing. Taken from
    # its run, it is within a fraction of a pixel of the height matplotlib gives
    # the character typeset on its own: the "lp" line box, or a taller
    # character's own box, which the run stands in for with the glyph's ink.
    fontsize = 26
    fig, ct = _flat_label("an (q) [j]", fontsize=fontsize, usetex=True)
    renderer = fig.canvas.get_renderer()
    for seg in ct._segments:
        alone = ct.axes.text(0, 0, _tex_source(seg._char), usetex=True,
                             fontsize=fontsize)
        expected = alone.get_window_extent(renderer).height
        assert seg._size_px(renderer)[1] == pytest.approx(expected, abs=0.5), (
            seg._char)
    plt.close(fig)


@needs_latex
@pytest.mark.parametrize("after, tex_files", [
    pytest.param({"font.family": "monospace"}, ("cmtt12.pfb",), id="family"),
    pytest.param({"font.family": "serif", "font.serif": ["Times"]},
                 ("mathptmx.sty", "utmr8a.pfb"), id="serif-list"),
])
def test_usetex_run_follows_the_font_when_rcparams_change(after, tex_files):
    if not _has_tex_files(*tex_files):
        pytest.skip(f"needs {', '.join(tex_files)}")
    # A run is typeset again when any rcParam matplotlib writes the LaTeX
    # preamble from changes: the family, or the font list it picks a family's
    # font from. A new label then
    # matches the character typeset alone under the new rcParams, and so does
    # a label drawn before the change and redrawn after it, whose outline must
    # come from the same pass as its width.
    with mpl.rc_context({"font.family": "serif"}):
        fig_before, drawn_before = _flat_label("ww", fontsize=30, usetex=True)
    with mpl.rc_context(after):
        _draw(fig_before)
        fig, drawn_after = _flat_label("ww", fontsize=30, usetex=True)
        alone = drawn_after.axes.text(0, 0, "w", usetex=True, fontsize=30)
        expected = alone.get_window_extent(fig.canvas.get_renderer()).width
        for label in (drawn_before, drawn_after):
            seg = label._segments[0]
            assert seg._width_px == pytest.approx(expected, abs=0.5)
        np.testing.assert_allclose(drawn_before._segments[0]._outline_units()[0],
                                   drawn_after._segments[0]._outline_units()[0])
    plt.close(fig_before)
    plt.close(fig)


@functools.cache
def _has_tex_files(*names):
    """Whether kpsewhich finds every one of the TeX files ``names``. Called from
    inside tests, so collecting the module never runs kpsewhich."""
    found = subprocess.run(["kpsewhich", *names], capture_output=True,
                           text=True).stdout.splitlines()
    return len([path for path in found if path]) == len(names)


# Usetex font setups, each with the TeX files its package draws from.
_TEX_FONT_CASES = [
    pytest.param({}, (), id="computer-modern"),
    pytest.param({"font.family": "monospace"}, ("cmtt12.pfb",), id="typewriter"),
    pytest.param(
        {"text.latex.preamble": r"\usepackage[T1]{fontenc}\usepackage{lmodern}"},
        ("lmodern.sty", "lmss17.pfb"), id="latin-modern"),
    pytest.param(
        {"text.latex.preamble": r"\usepackage{times}", "font.family": "serif"},
        ("times.sty", "utmr8a.pfb"), id="times"),
    pytest.param(
        {"text.latex.preamble": r"\usepackage[scaled=0.92]{helvet}"},
        ("helvet.sty", "uhvr8a.pfb"), id="helvetica-scaled"),
]


@needs_latex
@pytest.mark.parametrize("rc, tex_files", _TEX_FONT_CASES)
@pytest.mark.parametrize("valign", ["center", "ascender", "descender"])
def test_usetex_valign_follows_the_drawn_font(valign, rc, tex_files):
    if tex_files and not _has_tex_files(*tex_files):
        pytest.skip(f"needs {', '.join(tex_files)}")
    # Under usetex the text is drawn in a TeX font chosen by the preamble, so the
    # valign lines must come from that font as LaTeX draws it. TeX sizes the box
    # of "()gy" from the font's metrics, and its ink reaches within 0.02 em of
    # that box, so on a flat curve the label straddles the curve under "center"
    # and touches it at the top or bottom under "ascender" or "descender". The
    # cases catch the ways a datum can miss the drawn font: the matplotlib font
    # (DejaVu Sans, off by 0.18 em at the ascender), the font file's bounding
    # box (Latin Modern's is 0.4 em taller than its letters), a font the
    # preamble loads scaled (Helvetica at 0.92), and parentheses alone as the
    # probe (typewriter "g" and "y" hang 0.14 em below them).
    with mpl.rc_context(rc):
        fig, ct = _flat_label("()gy", fontsize=30, usetex=True, valign=valign)
        renderer = fig.canvas.get_renderer()
        ink = [seg._placed_path(renderer).get_extents() for seg in ct._segments]
    top = max(e.y1 for e in ink)
    bottom = min(e.y0 for e in ink)
    edge = {"center": (top + bottom) / 2.0, "ascender": top,
            "descender": bottom}[valign]
    curve_y = ct.axes.transData.transform((5.0, 5.0))[1]
    em_px = renderer.points_to_pixels(30)
    assert edge == pytest.approx(curve_y, abs=0.03 * em_px)
    plt.close(fig)


@needs_latex
@pytest.mark.parametrize("valign", ["baseline", "center", "ascender", "descender"])
def test_usetex_box_centres_on_the_ink_under_every_valign(valign):
    # The casing follows the label's "center" line whichever line rides the
    # curve, so it must take that line from the same drawn font as the label.
    # Under usetex the centre line lies midway between the top and bottom of
    # "()gy"; the matplotlib font's centre line sits 0.1 em higher.
    fig, ct = _flat_label("()gy", fontsize=30, usetex=True, valign=valign,
                          box=True)
    renderer = fig.canvas.get_renderer()
    ink = [seg._placed_path(renderer).get_extents() for seg in ct._segments]
    ink_mid = (max(e.y1 for e in ink) + min(e.y0 for e in ink)) / 2.0
    casing = np.column_stack([ct._box.get_xdata(), ct._box.get_ydata()])
    casing_y = ct.axes.transData.transform(casing)[:, 1]
    em_px = renderer.points_to_pixels(30)
    assert casing_y == pytest.approx(ink_mid, abs=0.025 * em_px)
    plt.close(fig)

