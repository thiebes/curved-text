"""A topographic map of real terrain, with its contour labels upright.

Elevation from matplotlib's ``jacksboro_fault_dem.npz`` sample data, a digital
elevation model near the Jacksboro fault in Tennessee, smoothed by a Gaussian
with a standard deviation of six cells so the contours are smooth enough to
label, cropped to the escarpment, and shaded by a light from the northwest and
darkened. Contours run every 50 m. ``ax.contour`` sets the direction of each
contour path, and many run from right to left on screen, so every label is
passed ``upright=True``.

Each label sits on the straightest stretch of its contour that has no other
contour near its center and where the shading, sampled along the contour under
the label, is dark enough for white text. A contour with no such stretch has no
label. Each elevation is labeled once, on the contour with the most room, and a
label too close to one already placed is left out. The map is dark and the
labels are white, with no casing or halo, so each label sits on its own contour
line, which runs through the text. White text has a contrast of at least 4.5:1
against any shading dark enough to pass placement; the pale contour line
through the text is not part of that measure.
"""
from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LightSource

from curved_text import curved_text
from _style import data_axes, figure, sample_data, save

# The standard deviation, in cells, of the Gaussian that smooths the terrain.
SMOOTHING_CELLS = 6
CONTOUR_INTERVAL_M = 50
# The part of the model that is mapped, as (first row, last row, first column,
# last column) counted from the south and west: the escarpment, whose contours
# run long and simple.
WINDOW = (40, 300, 130, 403)
# The shortest contour, in points, that is labeled: shorter ones are closed
# loops around a summit or a pit, or fragments at the edge.
MIN_POINTS = 150
# Where along a contour a label may sit, as fractions of its length.
CANDIDATE_POS = np.linspace(0.15, 0.85, 71)
# The least distance, in degrees, from a label's center to the nearest other
# contour, so a neighboring line is not at the center of the text.
MIN_ROOM = 0.0007
# The least distance, in degrees, between two labels.
MIN_LABEL_SEPARATION = 0.02
# A label is about 0.02 degrees long. The stretch of contour that must be
# straight is longer, so a bend just past the label's end does not crush its
# last letter. A contour that turns by more than MAX_TURN_DEGREES in total
# across that stretch, measured at TURN_SAMPLES points, is too curved for its
# label.
LABEL_LENGTH = 0.028
# The label size LABEL_LENGTH was measured for.
LABEL_FONTSIZE = 8
MAX_TURN_DEGREES = 40
TURN_SAMPLES = 10
# The factor that darkens the hillshading, so white labels can be read on it.
SHADE_DARKENING = 0.45
# The labels and the contour lines are white. White text is at least 4.5:1
# against a background whose relative luminance is at most this value, the
# WCAG 2 minimum for text, so a label is placed only where the shading sampled
# along the contour under it is that dark.
MAX_BACKGROUND_LUMINANCE = 0.18
# Meters in one degree of latitude, to turn the model's cell size into meters.
METERS_PER_DEGREE = 111200


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


def _luminance(rgb):
    """The WCAG 2 relative luminance of each color in ``rgb``, an array whose
    last axis holds the red, green, and blue values."""
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return linear @ np.array([0.2126, 0.7152, 0.0722])


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


def _straightest_pos(path, others, dark_enough):
    """The candidate ``pos`` at which ``path`` is straightest, among those where
    it is straight enough for a label, has no other contour near its center,
    and lies over shading
    dark enough for white text, and the distance from there to the nearest other
    contour. The label then lies on the flattest stretch the contour offers,
    where text follows it with the least bend. ``None`` where no candidate
    qualifies."""
    best = (None, None, np.inf)
    for pos in CANDIDATE_POS:
        turn = _turn_degrees(path, pos)
        if turn > MAX_TURN_DEGREES or turn >= best[2]:
            continue
        if not dark_enough(path, pos):
            continue
        room = float(np.min(np.hypot(*(others - _point_at(path, pos)).T)))
        if room >= MIN_ROOM:
            best = (float(pos), room, turn)
    return best[:2]


def make(images_dir):
    dem_path = sample_data("jacksboro_fault_dem.npz")
    if dem_path is None:
        print("  (skipped 20_topographic_map: no jacksboro_fault_dem.npz)")
        return None
    # The model's rows run from north to south. The grid has one elevation
    # per cell, and the corners are in degrees of longitude and latitude.
    with np.load(dem_path) as dem:
        elevation = dem["elevation"].astype(float)
        south, north = dem["ymin"], dem["ymax"]
        west, east = dem["xmin"], dem["xmax"]
        cell_deg = np.array([dem["dx"], dem["dy"]])
    if north < south:
        elevation = elevation[::-1]
        south, north = north, south
    smoothed = _gaussian_blur(elevation, SMOOTHING_CELLS)
    longitude = np.linspace(west, east, elevation.shape[1])
    latitude = np.linspace(south, north, elevation.shape[0])
    row0, row1, col0, col1 = WINDOW
    smoothed = smoothed[row0:row1, col0:col1]
    longitude, latitude = longitude[col0:col1], latitude[row0:row1]
    west, east = longitude[0], longitude[-1]
    south, north = latitude[0], latitude[-1]

    # Hillshading: a light from the northwest. The cell sizes are in meters,
    # so slopes are those of the ground, and the relief is exaggerated only by
    # the factor ``vert_exag``.
    cell_m = METERS_PER_DEGREE * cell_deg * [np.cos(np.radians(south)), 1]
    shade = LightSource(azdeg=315, altdeg=40).shade(
        smoothed, cmap=plt.cm.gist_earth, blend_mode="soft", vert_exag=2.0,
        dx=cell_m[0], dy=cell_m[1], fraction=0.9)
    shade[..., :3] *= SHADE_DARKENING
    luminance = _luminance(shade[..., :3])

    def dark_enough(path, pos):
        """Whether the shading is dark enough for white text at each of the
        ``TURN_SAMPLES`` points along ``path`` under a label centered at
        ``pos``."""
        length = np.hypot(*np.diff(path, axis=0).T).sum()
        half = LABEL_LENGTH / 2 / length
        points = np.array([_point_at(path, f) for f in
                           np.linspace(pos - half, pos + half, TURN_SAMPLES)])
        columns = np.round((points[:, 0] - west) / (east - west)
                           * (luminance.shape[1] - 1)).astype(int)
        rows = np.round((points[:, 1] - south) / (north - south)
                        * (luminance.shape[0] - 1)).astype(int)
        return bool(luminance[rows, columns].max() <= MAX_BACKGROUND_LUMINANCE)

    fig = figure(17, 14, font_size=9)
    ax = data_axes(fig.subplots())
    ax.imshow(shade, origin="lower", extent=(west, east, south, north),
              aspect=1 / np.cos(np.radians(south)), interpolation="bilinear")
    first_level = CONTOUR_INTERVAL_M * np.ceil(smoothed.min() / CONTOUR_INTERVAL_M)
    levels = np.arange(first_level, smoothed.max(), CONTOUR_INTERVAL_M)
    contours = ax.contour(longitude, latitude, smoothed, levels=levels,
                          colors="white", linewidths=0.7, alpha=0.6)

    paths = [(level, seg) for level, segs in zip(contours.levels,
                                                 contours.allsegs)
             for seg in segs if len(seg) >= MIN_POINTS]
    candidates = []
    for index, (level, seg) in enumerate(paths):
        others = np.vstack([s for i, (_, s) in enumerate(paths) if i != index])
        pos, room = _straightest_pos(seg, others, dark_enough)
        if pos is not None:
            candidates.append((room, level, seg, pos))
    # The contour with the most room labels its elevation first, and wins a
    # collision between two labels.
    placed = []
    labeled_levels = set()
    for _room, level, seg, pos in sorted(candidates, key=lambda c: -c[0]):
        point = _point_at(seg, pos)
        if level in labeled_levels or any(
                np.hypot(*(point - other)) < MIN_LABEL_SEPARATION
                for other in placed):
            continue
        placed.append(point)
        labeled_levels.add(level)
        curved_text(ax, seg[:, 0], seg[:, 1], f"{level:.0f} m", pos=pos,
                    upright=True, fontsize=LABEL_FONTSIZE, color="white")
    ax.set_xlabel("longitude (degrees)")
    ax.set_ylabel("latitude (degrees)")

    out_path = os.path.join(images_dir, "20_topographic_map.png")
    return save(fig, out_path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "images")
    os.makedirs(out, exist_ok=True)
    print(make(out))
