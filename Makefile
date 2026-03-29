# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

.PHONY: install test test-all test-coverage test-coverage-all lint fix typecheck format build publish lock check license-check license bump clean help

help: ## Display this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies including dev group
	uv sync --group dev

build: ## Build the package
	uv build

publish: ## Publish the package to PyPI
	uv publish

test: ## Run tests in parallel (excluding integration)
	uv run pytest -n auto

test-all: ## Run all tests including integration
	uv run pytest -n auto -m 'integration or not integration'

test-coverage: ## Run tests with coverage report (excluding integration)
	uv run pytest -n auto --cov=. --cov-report=term

test-coverage-all: ## Run all tests with coverage report
	uv run pytest -n auto --cov=. --cov-report=term -m 'integration or not integration'

lint: ## Run ruff linter
	uv run ruff check .

fix: ## Run ruff linter and apply fixes
	uv run ruff check --fix .

typecheck: ## Run type checker
	uv run ty check

format: ## Format code with ruff
	uv run ruff format .

bump: ## Bump version: make bump part=patch|minor|major
	uv version --bump $(part)

lock: ## Update the lockfile
	uv lock

check: lint typecheck format test license-check ## Run all checks (lint, typecheck, format, test, license-check)

license-check: ## Check that all files have REUSE license headers
	uv run reuse lint

license: ## Annotate files with REUSE license headers
	uv run reuse annotate \
		--license Apache-2.0 \
		--copyright "Greg Brandt <brandt.greg@gmail.com>" \
		--skip-unrecognized \
		--recursive .

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
