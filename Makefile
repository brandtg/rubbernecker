# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

.PHONY: install env test test-all test-coverage test-coverage-al lint typecheck format build clean

install:
	poetry env use python3.12
	poetry install --with dev

env:
	poetry env use python3.12

build:
	poetry build

test:
	poetry run pytest -n 1

test-all:
	poetry run pytest -n 1 -m 'integration or not integration'

test-coverage:
	poetry run pytest -n 1 --cov=. --cov-report=term

test-coverage-all:
	poetry run pytest -n 1 --cov=. --cov-report=term -m 'integration or not integration'

lint:
	poetry run flake8 .

typecheck:
	poetry run mypy .

format:
	poetry run black .

license:
	poetry run reuse annotate \
		--license Apache-2.0 \
		--copyright "Greg Brandt <brandt.greg@gmail.com>" \
		--skip-unrecognized \
		--recursive .

clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	poetry env remove --all 2>/dev/null || true
