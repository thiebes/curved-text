"""curved-text: draw text along an arbitrary curve in matplotlib."""
from importlib.metadata import PackageNotFoundError, version

from ._core import CurvedText, curved_text

__all__ = ["CurvedText", "curved_text"]

try:
    __version__ = version("curved-text")
except PackageNotFoundError:  # running from a source tree without an install
    __version__ = "0.0.0"
