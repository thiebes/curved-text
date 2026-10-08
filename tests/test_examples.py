"""Every figure in the example gallery draws without error.

Runs each script ``examples/generate_all.py`` lists, as that script does, into
a temporary folder, so a change to the library that breaks a gallery figure
fails here. A script returns ``None`` when an optional dependency (seaborn,
pandas, LaTeX with dvipng, or the ``Stocks.csv`` sample data, which
matplotlib 3.5 does not ship) is missing, and its figure is skipped, unless the
environment variable ``CURVED_TEXT_GALLERY_COMPLETE`` is set, as in the CI job
that installs every one of them, where a skip would hide a figure from CI.
"""
# Developed with AI assistance under maintainer review; see the
# "Development and AI use" section of the README.
import importlib.util
import os
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _load_example(name):
    """The module ``examples/<name>.py``, loaded with the examples folder on
    the import path, as ``generate_all.py`` runs it."""
    spec = importlib.util.spec_from_file_location(name, EXAMPLES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wcag_contrast_on_white(color):
    """The WCAG 2 contrast ratio of ``color`` against white."""
    channels = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                for c in mpl.colors.to_rgb(color)]
    luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    return 1.05 / (luminance + 0.05)


@pytest.fixture(autouse=True)
def _examples_on_path(monkeypatch):
    # The scripts import their shared style module from the examples folder.
    monkeypatch.syspath_prepend(str(EXAMPLES))


@pytest.mark.parametrize("name", _load_example("generate_all").MODULES)
def test_gallery_figure_draws(name, tmp_path):
    # The scripts set rcParams such as the font size, which must not leak into
    # the other tests, and each writes its figure where it is told.
    try:
        with mpl.rc_context():
            path = _load_example(name).make(str(tmp_path))
    finally:
        plt.close("all")
    if path is None:
        message = f"{name} needs an optional dependency or data that is missing"
        if os.environ.get("CURVED_TEXT_GALLERY_COMPLETE"):
            pytest.fail(message)
        pytest.skip(message)
    assert Path(path).parent == tmp_path
    assert Path(path).stat().st_size > 0


def test_gallery_text_shades_are_legible():
    # Label text in the gallery is at least 4.5:1 against its white
    # background, the WCAG 2 minimum for text; the gold and green shades pass
    # by a few hundredths, so retuning one must not drop it below.
    style = _load_example("_style")
    for hue, color in style.TEXT.items():
        assert _wcag_contrast_on_white(color) >= 4.5, hue
