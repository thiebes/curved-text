# Contributing

Thanks for your interest in curved-text. Bug reports, feature requests, and
pull requests are all welcome. By participating you agree to abide by the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting issues

Open an issue on the [issue tracker](https://github.com/thiebes/curved-text/issues).
For a bug, a
short script that reproduces the problem, the matplotlib and numpy versions, and
what you expected to see are the most useful things to include.

## Development install

Clone the repository and install it in editable mode with the test and example
dependencies:

```bash
git clone https://github.com/thiebes/curved-text
cd curved-text
pip install -e ".[test,examples]"
```

A virtual environment is recommended so the install does not touch your system
packages.

## Running the tests

```bash
pytest -q
```

The tests live in [tests/test_core.py](tests/test_core.py). They cover the
public API: placement (`pos`, `anchor`, `offset`), mathtext, the box casing,
redraw stability, and error handling for bad input. Add to this file when you
change behaviour.

The same suite runs in continuous integration across the supported Python
versions and against the lowest supported matplotlib version. If your change
touches anything version-sensitive, test it against that lowest version too,
even if it passes on a recent matplotlib.

## Linting and type checking

The project uses [ruff](https://docs.astral.sh/ruff/) for linting and
[mypy](https://mypy-lang.org/) for type checking. Install them and run both
before opening a pull request:

```bash
pip install ruff mypy
ruff check .
mypy src
```

Both also run in continuous integration.

## Regenerating the example gallery

The figures under [examples/images/](examples/images/) are produced by the
scripts in [examples/](examples/). If a change affects the rendered output,
regenerate them so the gallery stays in sync:

```bash
python examples/generate_all.py
```

This needs the `examples` extra (seaborn and pandas) for the one integration
figure.

## Building the documentation

The documentation is built with [Sphinx](https://www.sphinx-doc.org/). Install
the docs dependencies and build the HTML locally:

```bash
pip install -e ".[docs]"
sphinx-build -b html docs docs/_build/html
```

Open `docs/_build/html/index.html` to preview. The same build is published to
GitHub Pages on every push to `main`.

## Pull requests

- Branch off `main` and keep each pull request focused on a single change.
- Add or update tests for any behaviour change, and update the docstrings and
  the relevant docs or example when the public API or rendered output changes.
- Add a short entry to [CHANGELOG.md](CHANGELOG.md) under an unreleased heading
  describing the change from a user's point of view.
- Make sure `pytest`, `ruff check .`, and `mypy src` all pass.

## Releasing

Releases are cut by the maintainer. A version tag (`vX.Y.Z`) pushed to GitHub
triggers the publish workflow, which builds the distribution, publishes it to
PyPI through trusted publishing, and creates the matching GitHub release from
the CHANGELOG section for that version.
