#!/bin/sh
# Execute in a clean pinned Python 3.12 Linux container with the workspace mounted.
# All installations occur inside that disposable container, never a host venv.
set -eu
python -m pip install --disable-pip-version-check -r requirements.in
python -m pip check
python -m pip freeze --all > requirements.lock
python -m pip install --disable-pip-version-check -r requirements-dev.in
python -m pip check
python -m pip freeze --all > requirements-dev.lock
