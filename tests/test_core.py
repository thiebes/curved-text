"""Smoke and behaviour tests for curved_text.

The Agg backend is selected in conftest.py before pyplot is imported.
"""
import matplotlib.pyplot as plt
import numpy as np
import pytest

from curved_text import CurvedText, curved_text
from curved_text._core import _MathRun, _split_runs


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


def test_math_run_centres_on_curve_like_rigid_text():
    # The datum is chosen so the run rides the curve exactly where a rigid
    # va="center" Text would. On a straight line the bent ink centre must match
    # the centre of an equivalent centred mathtext Text.
    fig, ax = plt.subplots()
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    x = np.linspace(0, 10, 100)
    y = np.full_like(x, 5.0)
    s = r"$\propto\sqrt{D_{\mathrm{eff}}}$"
    ct = curved_text(ax, x, y, s, pos=0.5, anchor="center", fontsize=14)
    reference = ax.text(5.0, 5.0, s, ha="center", va="center", fontsize=14)
    _draw(fig)
    renderer = fig.canvas.get_renderer()
    bent = ct._segments[0]._bent_path(renderer).get_extents()
    ref = reference.get_window_extent(renderer)
    assert (bent.x0 + bent.x1) / 2.0 == pytest.approx(
        (ref.x0 + ref.x1) / 2.0, abs=3.0)
    assert (bent.y0 + bent.y1) / 2.0 == pytest.approx(
        (ref.y0 + ref.y1) / 2.0, abs=2.0)
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
    bound = extent.height / 2.0 + 2.0
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
