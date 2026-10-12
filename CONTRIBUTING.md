# Contributing

Bug reports, feature requests, and pull requests are welcome. By participating
you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Reporting issues

Open an issue on the [issue tracker](https://github.com/thiebes/curved-text/issues).
For a bug, please include a short script that reproduces the problem, the
matplotlib and numpy versions, and what you expected to see.

## Development install

Clone the repository, create a virtual environment so the install does not
touch your system packages, and install the package in editable mode with the
test and example dependencies:

```bash
git clone https://github.com/thiebes/curved-text
cd curved-text
python -m venv .venv
source .venv/bin/activate   # on Windows: .venv\Scripts\activate
pip install -e ".[test,examples]"
```

## Design notes

Read the [design notes](docs/design-mathtext.md) before you change placement,
layout, the conversion of the curve, or the typesetting of math. They state
the decisions the code depends on, and the reasons for them. Update them when
a change alters the design.

## Running the tests

```bash
pytest -q
```

To run one test, or the tests whose names match a word, use:

```bash
pytest tests/test_core.py::test_name
pytest -k kerning
```

The tests live in [tests/test_core.py](tests/test_core.py). They cover the
public API and the behavior behind it: placement (`pos`, `anchor`, `offset`,
`valign`), mathtext, dates and other unit types, curves with gaps, kerning,
usetex, the box casing, crowding, layout, picking, redraw stability, and error
handling for bad input. Add to this file when you change behavior.

[tests/test_examples.py](tests/test_examples.py) runs every figure script the
gallery lists, so a change that breaks one fails there. A figure whose
requirement is missing is skipped: seaborn and pandas, LaTeX with `dvipng`, or
the `Stocks.csv` sample data, which matplotlib 3.5 does not include. Set the
environment variable `CURVED_TEXT_GALLERY_COMPLETE` to `1` to make such a skip
fail instead, as the continuous integration (CI) job that installs every
requirement does. The module skips itself in a source distribution, which
includes `tests/` but not `examples/`.

The usetex tests need a LaTeX installation and are skipped without one, so a
run with no LaTeX can pass while testing less. Run `pytest -rs` to list every
skipped test with its reason, and check that the usetex tests are not among
them. To run them, install LaTeX with the packages named in `TEX_PACKAGES` in
[.github/workflows/ci.yml](.github/workflows/ci.yml); the tests for fonts
loaded through the preamble are also skipped when their font packages are
missing.

### Continuous integration

Pull requests run these jobs:

| Job | What it checks | Fails the build |
| ------- | ------------- | ------------- |
| `lint` | `ruff check .` and `mypy src`, on Python 3.13 | Yes |
| `docs` | The documentation builds with warnings as errors | Yes |
| `test` | The suite on Python 3.9, 3.11, and 3.13. The 3.13 entry also installs LaTeX and the `examples` extra, and sets `CURVED_TEXT_GALLERY_COMPLETE` | Yes |
| `floor` | The suite on Python 3.9 with the lowest supported matplotlib, with LaTeX | Yes |
| `prerelease` | The suite against the newest matplotlib pre-release | No: it reports a failure without failing the build |

If your change touches anything that depends on the matplotlib version, run
the suite against the lowest supported version yourself, even if it passes on
a recent one. Use a Python 3.9 environment, and pin numpy below 2, because
matplotlib 3.5 does not support numpy 2:

```bash
pip install -e ".[test]" "matplotlib==3.5.*" "numpy<2"
pytest -q
```

## Linting and type checking

The project uses [ruff](https://docs.astral.sh/ruff/) for linting and
[mypy](https://mypy-lang.org/) for type checking. Install them and run both
before opening a pull request:

```bash
pip install ruff mypy
ruff check .
mypy src
```

Both also run in CI.

## Regenerating the example gallery

The figures under [examples/images/](examples/images/) are produced by the
scripts in [examples/](examples/). If a change affects the rendered output,
regenerate them so the gallery stays in sync:

```bash
python examples/generate_all.py
```

The committed figures were rendered with matplotlib 3.10.9. Another matplotlib
version changes the pixels of every figure, so regenerate with that version
and commit only the figures that your change affects.

Regenerating needs the `examples` extra (seaborn and pandas) for the one
integration figure, a LaTeX installation with `dvipng` for the usetex figure,
and a matplotlib that includes the `Stocks.csv` sample data (3.5 does not) for
the seaborn and stock price figures. Each of those scripts skips its figure
when its requirement is missing, so the other figures still regenerate.

To add a figure:

1. Write `examples/example_NN_name.py` with a `make(images_dir)` function that
   saves the figure and returns its path, or returns `None` when an optional
   requirement is missing.
2. Add the module name to `MODULES` in `examples/generate_all.py`.
   `tests/test_examples.py` then runs it.
3. Add an entry with the image and a link to the script to
   [examples/README.md](examples/README.md).

## Building the documentation

The documentation is built with [Sphinx](https://www.sphinx-doc.org/). Install
the docs dependencies and build the HTML locally, with the same flags as CI, so
that a warning fails the build here and not only there:

```bash
pip install -e ".[docs]"
sphinx-build -W --keep-going -b html docs docs/_build/html
```

Open `docs/_build/html/index.html` to preview. The same build is published to
GitHub Pages on every push to `main`.

## Dependencies and workflows

The `docs` job installs the pinned, hash-checked requirements in
`.github/requirements/docs.txt`, and then installs the project with
`--no-index`. If you change the `docs` extra, a runtime dependency, or the
`[build-system]` requirement in `pyproject.toml`, regenerate that file as the
comment at its top describes, or the job fails.

The actions in `.github/workflows/` are pinned to commit SHAs, each with a
comment that names the version. Keep that form when you edit a workflow.
Dependabot proposes updates to both. The `uv` version is the exception: it is
set by hand in `UV_VERSION` in `ci.yml`.

## Pull requests

- Branch off `main` and keep each pull request focused on a single change.
- Add or update tests for any behavior change, and update the docstrings and
  the relevant docs or example when the public API or rendered output changes.
- Add a short entry to [CHANGELOG.md](CHANGELOG.md) under the `## Unreleased`
  heading, describing the change from a user's point of view.
- Make sure `pytest`, `ruff check .`, and `mypy src` all pass.

## Releasing

The maintainer makes releases. A release commit does three things: it changes
`version` in `pyproject.toml`, it changes `version` and `date-released` in
`CITATION.cff`, and it renames the `## Unreleased` heading in
[CHANGELOG.md](CHANGELOG.md) to `## X.Y.Z`. After it is merged, a version tag
(`vX.Y.Z`) pushed to GitHub triggers the publish workflow. The workflow builds
the distribution, publishes it to the Python Package Index (PyPI) through
trusted publishing from the `pypi` environment, and creates the matching
GitHub release from the CHANGELOG section for that version.

The workflow stops if the tag does not match the version in `pyproject.toml`,
so run from a branch by hand it fails at that check: it needs a version tag.
