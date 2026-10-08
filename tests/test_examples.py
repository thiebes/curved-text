"""Every figure in the example gallery draws without error.

Runs each script ``examples/generate_all.py`` lists, as that script does, into
a temporary folder, so a change to the library that breaks a gallery figure
fails here. A script returns ``None`` when an optional dependency (seaborn,
pandas, LaTeX) is missing, and its figure is skipped.
"""
# Developed with AI assistance under maintainer review; see the
# "Development and AI use" section of the README.
import importlib
import importlib.util
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _gallery_modules():
    """The script names ``examples/generate_all.py`` lists, in its order."""
    spec = importlib.util.spec_from_file_location(
        "generate_all", EXAMPLES / "generate_all.py")
    generate_all = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generate_all)
    return generate_all.MODULES


@pytest.mark.parametrize("name", _gallery_modules())
def test_gallery_figure_draws(name, tmp_path, monkeypatch):
    # The scripts import their shared style module from the examples folder,
    # and set rcParams such as the font size, which must not leak into the
    # other tests.
    monkeypatch.syspath_prepend(str(EXAMPLES))
    with mpl.rc_context():
        path = importlib.import_module(name).make(str(tmp_path))
    plt.close("all")
    if path is None:
        pytest.skip(f"{name} needs an optional dependency that is missing")
    assert Path(path).stat().st_size > 0
