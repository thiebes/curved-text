"""Smoke and behaviour tests for curved_text.

The Agg backend is selected in conftest.py before pyplot is imported.
"""
import matplotlib.pyplot as plt
import numpy as np
import pytest

from curved_text import CurvedText, curved_text


def _draw(fig):
    """Force a draw so CurvedText positions its glyphs."""
    fig.canvas.draw()


def test_places_one_artist_per_character():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 50)
    ct = curved_text(ax, x, np.sin(x), "abc", pos=0.5, anchor="center")
    assert len(ct._chars) == 3
    _draw(fig)
    assert all(t.get_visible() for t in ct._chars)
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
    sx = np.mean([t.get_position()[0] for t in start._chars])
    ex = np.mean([t.get_position()[0] for t in end._chars])
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
    fy = np.mean([t.get_position()[1] for t in flat._chars])
    ly = np.mean([t.get_position()[1] for t in lifted._chars])
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
        fy = np.mean([t.get_position()[1] for t in flat._chars])
        ly = np.mean([t.get_position()[1] for t in lifted._chars])
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
    assert all(t.get_visible() for t in ct._chars)
    plt.close(fig)


def test_left_overrun_is_not_clipped():
    # The symmetric case: anchor the end of a long label before the left end of a
    # short curve so the label rides the left tangent extension.
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 20)
    ct = curved_text(ax, x, np.zeros_like(x), "a long label", pos=0.0,
                     anchor="end")
    _draw(fig)
    assert all(t.get_visible() for t in ct._chars)
    plt.close(fig)


def test_degenerate_curve_does_not_raise():
    # A curve whose points are all identical has zero arc length; drawing must
    # short-circuit cleanly rather than raising.
    fig, ax = plt.subplots()
    x = np.full(10, 3.0)
    y = np.full(10, 3.0)
    ct = curved_text(ax, x, y, "abc", pos=0.5, anchor="center")
    _draw(fig)
    assert len(ct._chars) == 3
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
    for a, b in zip(via_fn._chars, via_cls._chars):
        assert a.get_position() == pytest.approx(b.get_position())
    plt.close(fig)


def test_set_zorder_lifts_glyphs_above_container():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    ct = curved_text(ax, x, np.zeros_like(x), "ab", pos=0.5, anchor="center")
    ct.set_zorder(5)
    assert ct.get_zorder() == 5
    assert all(t.get_zorder() == 6 for t in ct._chars)
    plt.close(fig)


def test_remove_drops_child_glyphs():
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    ct = curved_text(ax, x, np.zeros_like(x), "ab", pos=0.5, anchor="center")
    chars = list(ct._chars)
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
    first = [t.get_position() for t in ct._chars]
    _draw(fig)
    second = [t.get_position() for t in ct._chars]
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
