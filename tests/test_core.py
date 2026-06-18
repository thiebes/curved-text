"""Smoke and behaviour tests for curved_text.

The Agg backend is selected in conftest.py before pyplot is imported.
"""
# Developed with AI assistance under maintainer review; see the
# "Development and AI use" section of the README.
import matplotlib.pyplot as plt
import numpy as np
import pytest

from curved_text import CurvedText, curved_text
from curved_text._core import _MathRun, _split_runs, _text_to_path


def _draw(fig):
    """Force a draw so CurvedText positions its glyphs."""
    fig.canvas.draw()


def _math_runs(ct):
    return [t for t in ct._segments if isinstance(t, _MathRun)]


def test_places_one_artist_per_character():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 50)
    ct = curved_text(ax, x, np.sin(x), "abc", pos=0.5, anchor="center")
    assert len(ct._segments) == 3
    _draw(fig)
    assert all(t.get_visible() for t in ct._segments)
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
    sx = np.mean([t.get_position()[0] for t in start._segments])
    ex = np.mean([t.get_position()[0] for t in end._segments])
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
    fy = np.mean([t.get_position()[1] for t in flat._segments])
    ly = np.mean([t.get_position()[1] for t in lifted._segments])
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
        fy = np.mean([t.get_position()[1] for t in flat._segments])
        ly = np.mean([t.get_position()[1] for t in lifted._segments])
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
        p = ax.transData.transform(np.asarray(s.get_position()))
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
        centers = np.array([s.get_position() for s in ct._segments])
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
    center = ax.transData.transform(ct._segments[0].get_position())
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
    shifts = np.array([np.subtract(b.get_position(), a.get_position())
                       for a, b in zip(flat._segments, lifted._segments)])
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
        return _math_runs(ct)[0]._bent_path(renderer).vertices.mean(axis=0)

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
    rots = [t.get_rotation() for t in ct._segments]
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
    for a, b in zip(via_fn._segments, via_cls._segments):
        assert a.get_position() == pytest.approx(b.get_position())
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
    first = [t.get_position() for t in ct._segments]
    _draw(fig)
    second = [t.get_position() for t in ct._segments]
    for a, b in zip(first, second):
        assert a == pytest.approx(b)
    plt.close(fig)


def test_validates_inputs():
    fig, ax = plt.subplots()
    with pytest.raises(ValueError):
        CurvedText([0.0], [0.0], "x", ax)            # too few points
    with pytest.raises(ValueError):
        CurvedText([0, 1], [0, 1], "x", ax, anchor="middle")  # bad anchor
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
    verts, _, datum = run._expression_outline()
    per_unit = renderer.points_to_pixels(14.0) / 100.0
    # A horizontal curve maps data x to pixels linearly, so arc length s lands
    # at first_px + s; the run's left edge is at arc length run._s_left.
    first_px = ax.transData.transform((0.0, 5.0))[0]
    cy = ax.transData.transform((5.0, 5.0))[1]
    expected = np.column_stack([
        first_px + run._s_left + verts[:, 0] * per_unit,
        cy + (verts[:, 1] - datum) * per_unit])
    assert np.allclose(run._bent_path(renderer).vertices, expected, atol=1e-6)
    plt.close(fig)


def test_math_run_aligns_to_plain_x_height():
    # A math run rides the curve on the surrounding text's x-height line, so a
    # lowercase math symbol lands where the plain character would under
    # va="center". On a straight line the bent "x" centre must match a plain
    # centred "x".
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 100)
    y = np.full_like(x, 5.0)
    math_x = curved_text(ax, x, y, "$x$", pos=0.5, anchor="center", fontsize=16)
    plain_x = ax.text(5.0, 5.0, "x", ha="center", va="center", fontsize=16)
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    bent = math_x._segments[0]._bent_path(renderer).get_extents()
    ref = plain_x.get_window_extent(renderer)
    assert (bent.y0 + bent.y1) / 2.0 == pytest.approx(
        (ref.y0 + ref.y1) / 2.0, abs=2.0)
    # The run also sits horizontally where the centred plain glyph does.
    assert (bent.x0 + bent.x1) / 2.0 == pytest.approx(
        (ref.x0 + ref.x1) / 2.0, abs=3.0)
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
    body = plain._segments[0]._bent_path(renderer).get_extents()
    with_exp = raised._segments[0]._bent_path(renderer).get_extents()
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
    bent = run._bent_path(renderer)
    center = ax.transData.transform((0.0, 0.0))
    radius = ax.transData.transform((1.0, 0.0))[0] - center[0]
    extent = run.get_window_extent(renderer)
    # Derive the bound from the run's actual outline reach above and below the
    # x-height datum it rides on, mapped to pixels exactly as _bent_path does.
    # Tying the bound to the same geometry the bend map uses keeps it robust to
    # matplotlib mathtext metric changes; half the window-extent height is a
    # different reference frame (the box midpoint, not the x-height line) and
    # only happened to sit just above the true reach.
    verts, _, datum = run._expression_outline()
    px_per_unit = (renderer.points_to_pixels(run.get_fontsize())
                   / _text_to_path.FONT_SCALE)
    reach = np.abs(verts[:, 1] - datum).max() * px_per_unit
    bound = reach + 2.0
    half_span = extent.width / 2.0 / radius  # half the label arc, radians
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
    fy = flat._segments[0]._bent_path(renderer).get_extents()
    ly = lifted._segments[0]._bent_path(renderer).get_extents()
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
        bent = ct._segments[0]._bent_path(fig.canvas.get_renderer())
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
    bent = ct._segments[2]._bent_path(renderer).get_extents()
    to_px = ax.transData.transform
    b_x = to_px(ct._segments[1].get_position())[0]
    c_x = to_px(ct._segments[3].get_position())[0]
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
    hs = small._segments[0]._bent_path(renderer).get_extents().height
    hl = large._segments[0]._bent_path(renderer).get_extents().height
    assert hl / hs == pytest.approx(2.0, rel=0.1)
    plt.close(fig)


def test_math_run_overrun_rides_tangent_extension():
    # A math label anchored past the right end of a short straight curve rides
    # the tangent extension at the curve's height, like plain characters do.
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
    bent = run._bent_path(renderer).get_extents()
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
    first = _math_runs(ct)[0]._bent_path(renderer).vertices.copy()
    _draw(fig)
    second = _math_runs(ct)[0]._bent_path(renderer).vertices
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
        bbox = run._bent_path(fig.canvas.get_renderer()).get_extents()
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
    # Collapse the curve to a single point, then redraw.
    ct._cx = np.full_like(ct._cx, 5.0)
    ct._cy = np.full_like(ct._cy, 5.0)
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
        extents = [s.get_window_extent(renderer) for s in ct._segments]
        x0 = int(min(e.x0 for e in extents))
        x1 = int(np.ceil(max(e.x1 for e in extents)))
        y0 = int(min(e.y0 for e in extents))
        y1 = int(np.ceil(max(e.y1 for e in extents)))
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
    for a, b in zip(default._segments, explicit._segments):
        assert a.get_position() == pytest.approx(b.get_position())
        assert a.get_rotation() == pytest.approx(b.get_rotation())
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
    for a, b in zip(flat._segments, bent._segments):
        assert a.get_position()[0] == pytest.approx(b.get_position()[0])
    plt.close(fig)


def _end_to_end(ct):
    x0, y0 = ct._segments[0].get_position()
    x1, y1 = ct._segments[-1].get_position()
    return np.hypot(x1 - x0, y1 - y0)


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
