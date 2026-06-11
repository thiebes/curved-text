"""Render every figure in the gallery into ``examples/images/``.

Run from anywhere::

    python examples/generate_all.py
"""
from __future__ import annotations

import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IMAGES = os.path.join(HERE, "images")

MODULES = [
    "example_01_direct_labeling",
    "example_02_sine_hello",
    "example_03_pos_sweep",
    "example_04_anchor_triptych",
    "example_05_offset_ladder",
    "example_06_overrun_tangent",
    "example_07_glued_resize",
    "example_08_styling_passthrough",
    "example_09_seaborn_pandas",
]


def main():
    sys.path.insert(0, HERE)
    os.makedirs(IMAGES, exist_ok=True)
    for name in MODULES:
        mod = importlib.import_module(name)
        path = mod.make(IMAGES)
        if path:
            print(os.path.relpath(path, HERE))


if __name__ == "__main__":
    main()
