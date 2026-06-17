"""Sphinx configuration for the curved-text documentation site."""
from importlib.metadata import PackageNotFoundError, version as _version

project = "curved-text"
author = "Joseph Thiebes"
copyright = "Joseph Thiebes"

try:
    release = _version("curved-text")
except PackageNotFoundError:  # building from a source tree without an install
    release = "0.0.0"
version = ".".join(release.split(".")[:2])

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
]

# The README and the gallery reference each other and external pages by absolute
# URL, so no relative-link rewriting is needed when they are included here.
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}

html_theme = "furo"
html_title = f"curved-text {version}"

# Resolve the matplotlib and numpy cross-references used in the docstrings
# (for example :class:`matplotlib.text.Text`) against their published docs.
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable", None),
    "matplotlib": ("https://matplotlib.org/stable", None),
}

# Keep the build green when an external reference cannot be resolved offline;
# the API reference is the primary product here, not a strict link audit.
nitpicky = False

autodoc_member_order = "bysource"
napoleon_google_docstring = False
napoleon_numpy_docstring = True
