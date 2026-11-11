"""A topographic map of real terrain, with its contour labels upright.

Elevation from matplotlib's ``jacksboro_fault_dem.npz`` sample data, a digital
elevation model near the Jacksboro fault in Tennessee, smoothed by a Gaussian
about six cells wide so the contours are smooth enough to label, and shaded by
a light from the northwest. Contours run every 50 m. ``ax.contour`` sets the
direction of each contour path, and many run from right to left on screen, so
every label is passed ``upright=True``. Each label sits where its contour has
the most room, a contour with no stretch straight and open enough for a label
has none, and a label too close to one already placed is left out. Each label
has a thin white halo, not a casing, so its contour runs into it from both
sides.
"""
from __future__ import annotations

import os

import matplotlib.patheffects as patheffects
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LightSource

from curved_text import curved_text
from _style import data_axes, figure, sample_data, save

# The standard deviation, in cells, of the Gaussian that smooths the terrain.
SMOOTHING_CELLS = 6
CONTOUR_INTERVAL_M = 50
# The shortest contour, in points, that is labeled: shorter ones are closed
# loops around a summit or a pit, or fragments at the edge.
MIN_POINTS = 250
# Where along a contour a label may sit, as fractions of its length.
CANDIDATE_POS = np.linspace(0.15, 0.85, 29)
# The least distance, in degrees, from a label to the nearest other contour: a
# little more than half the height of its casing, so the casing covers no
# neighboring contour.
MIN_ROOM = 0.0025
# The least distance, in degrees, between two labels.
MIN_LABEL_SEPARATION = 0.045
# A label is about this long, in degrees, and a contour that turns by more than
# MAX_TURN_DEGREES in total across that length, measured at TURN_SAMPLES points,
# is too curved for its label.
LABEL_LENGTH = 0.025
MAX_TURN_DEGREES = 30.0
TURN_SAMPLES = 8
# How far the hillshading is lightened toward white, so the contours stand out.
SHADE_LIGHTENING = 0.4
INK = "#3b2f2f"   # near-black brown, 12.9:1 against white
# A thin white outline on each glyph, so the contour runs into the label from
# both sides and the reader sees which line it names.
HALO = [patheffects.withStroke(linewidth=3.5, foreground="white")]


def _gaussian_blur(grid, sigma):
    """``grid`` smoothed by a separable Gaussian of ``sigma`` cells, each edge
    padded with its own values. scipy is not a dependency, so this uses numpy
    alone."""
    reach = int(2 * sigma)
    weights = np.exp(-0.5 * (np.arange(-reach, reach + 1) / sigma) ** 2)
    weights /= weights.sum()

    def along(line):
        return np.convolve(np.pad(line, reach, mode="edge"), weights, "valid")

    grid = np.apply_along_axis(along, 1, grid)
    return np.apply_along_axis(along, 0, grid)


def _point_at(path, pos):
    """The point at arc-length fraction ``pos`` of ``path``, an (n, 2) array."""
    steps = np.hypot(*np.diff(path, axis=0).T)
    arc = np.insert(np.cumsum(steps), 0, 0.0)
    return np.array([np.interp(pos * arc[-1], arc, path[:, i])
                     for i in range(2)])


def _turn_degrees(path, pos):
    """The total turning of ``path``, in degrees, along a label's length
    centered at ``pos``, summed over short steps so a hairpin inside the
    length counts even where its two sides cancel."""
    length = np.hypot(*np.diff(path, axis=0).T).sum()
    fractions = pos + np.linspace(-0.5, 0.5, TURN_SAMPLES) * LABEL_LENGTH / length
    points = np.array([_point_at(path, f) for f in fractions])
    steps = np.diff(points, axis=0)
    turns = np.arctan2(steps[:-1, 0] * steps[1:, 1] - steps[:-1, 1] * steps[1:, 0],
                       (steps[:-1] * steps[1:]).sum(axis=1))
    return float(np.abs(np.degrees(turns)).sum())


def _roomiest_pos(path, others):
    """The candidate ``pos`` at which ``path`` is farthest from every other
    contour, among those where it is straight enough for a label and clear of
    its neighbors, and that distance. Where contours crowd, as on a steep slope,
    a label would cover them. ``None`` where no candidate qualifies."""
    best = (None, -1.0)
    for pos in CANDIDATE_POS:
        if _turn_degrees(path, pos) > MAX_TURN_DEGREES:
            continue
        point = _point_at(path, pos)
        room = float(np.min(np.hypot(*(others - point).T)))
        if room > best[1] and room >= MIN_ROOM:
            best = (float(pos), room)
    return best


def make(images_dir):
    path = sample_data("jacksboro_fault_dem.npz")
    if path is None:
        print("  (skipped 20_topographic_map: no jacksboro_fault_dem.npz)")
        return None
    dem = np.load(path)
    # The model's rows run from north to south. The grid has one elevation
    # per cell, and the corners are in degrees of longitude and latitude.
    elevation = dem["elevation"].astype(float)
    south, north = dem["ymin"], dem["ymax"]
    west, east = dem["xmin"], dem["xmax"]
    if north < south:
        elevation = elevation[::-1]
        south, north = north, south
    smoothed = _gaussian_blur(elevation, SMOOTHING_CELLS)
    longitude = np.linspace(west, east, elevation.shape[1])
    latitude = np.linspace(south, north, elevation.shape[0])

    # Hillshading: a light from the northwest, with the relief exaggerated
    # by the ratio of a degree of latitude to a degree of longitude, so the
    # slopes are those of the ground.
    cell_m = 111200 * np.array([dem["dx"] * np.cos(np.radians(south)),
                                dem["dy"]])
    shade = LightSource(azdeg=315, altdeg=40).shade(
        smoothed, cmap=plt.cm.gist_earth, blend_mode="soft", vert_exag=2.0,
        dx=cell_m[0], dy=cell_m[1], fraction=0.9)
    shade[..., :3] = (1 - SHADE_LIGHTENING) * shade[..., :3] + SHADE_LIGHTENING

    fig = figure(17, 14, font_size=9)
    ax = data_axes(fig.subplots())
    ax.imshow(shade, origin="lower", extent=(west, east, south, north),
              aspect=1 / np.cos(np.radians(south)), interpolation="bilinear")
    levels = np.arange(CONTOUR_INTERVAL_M * np.ceil(smoothed.min() / 50),
                       smoothed.max(), CONTOUR_INTERVAL_M)
    contours = ax.contour(longitude, latitude, smoothed, levels=levels,
                          colors=INK, linewidths=0.7)

    paths = [(level, seg) for level, segs in zip(contours.levels,
                                                 contours.allsegs)
             for seg in segs if len(seg) >= MIN_POINTS]
    candidates = []
    for index, (level, seg) in enumerate(paths):
        others = np.vstack([s for i, (_, s) in enumerate(paths) if i != index])
        pos, room = _roomiest_pos(seg, others)
        if pos is not None:
            candidates.append((room, level, seg, pos))
    placed = []
    for _room, level, seg, pos in sorted(candidates, key=lambda c: -c[0]):
        point = _point_at(seg, pos)
        if any(np.hypot(*(point - other)) < MIN_LABEL_SEPARATION
               for other in placed):
            continue
        placed.append(point)
        curved_text(ax, seg[:, 0], seg[:, 1], f"{level:.0f} m", pos=pos,
                    upright=True, fontsize=9, color=INK, path_effects=HALO)
    ax.set_xlabel("longitude (degrees)")
    ax.set_ylabel("latitude (degrees)")

    path = os.path.join(images_dir, "20_topographic_map.png")
    return save(fig, path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
