<!--
SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>

SPDX-License-Identifier: Apache-2.0
-->

# Development

Common tasks for working on Rubbernecker locally.

## Setup

```bash
make install
# or
uv sync
```

## Running Tests

```bash
# Unit tests only
make test

# All tests including integration tests
make test-all

# Tests with coverage report
make test-coverage
```

## Linting and Type Checking

```bash
make lint
make typecheck
```

## Formatting

```bash
make format
```

## Building

```bash
make build
```

## Cleaning Up

```bash
make clean
```

## Debug Logging

Pass `--debug` before the subcommand to enable verbose logging:

```bash
uv run rubbernecker --debug crawl tmp/urls.txt tmp/output.avro
```
