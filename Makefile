# AgriNav developer task runner.
#
# These targets are thin wrappers around the documented commands so that local
# development and CI invoke the exact same tools. On Windows without `make`,
# run the underlying commands directly (see README "Development").
#
# Editable-install targets (`install`, `install-dev`) require the packaging
# metadata added in the src/agrinav migration change.

PYTHON ?= python
PIP    ?= $(PYTHON) -m pip

.PHONY: help install install-dev format lint typecheck test test-unit \
        test-integration precommit clean

help:
	@echo "install          editable install (runtime deps)"
	@echo "install-dev      editable install with dev + train + inference extras"
	@echo "format           auto-format with ruff-format + black"
	@echo "lint             ruff lint"
	@echo "typecheck        mypy"
	@echo "test             full pytest suite"
	@echo "test-unit        pytest -m unit"
	@echo "test-integration pytest -m integration"
	@echo "precommit        run all pre-commit hooks"
	@echo "clean            remove caches and build artifacts"

install:
	$(PIP) install -e .

install-dev:
	$(PIP) install -e ".[dev,train,inference]"
	$(PYTHON) -m pre_commit install

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m black .

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m black --check .

typecheck:
	$(PYTHON) -m mypy src

test:
	$(PYTHON) -m pytest

test-unit:
	$(PYTHON) -m pytest -m unit

test-integration:
	$(PYTHON) -m pytest -m integration

precommit:
	$(PYTHON) -m pre_commit run --all-files

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
	find . -type d -name __pycache__ -not -path './_archive/*' -exec rm -rf {} +
