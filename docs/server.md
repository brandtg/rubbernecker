<!--
SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>

SPDX-License-Identifier: Apache-2.0
-->

# Admin Server

The admin server is a lightweight, read-only web dashboard for monitoring rubbernecker crawl pipelines. It walks a root directory, discovers Avro files and crawl datasets, and renders status and data previews in the browser.

## Installation

The server requires Flask, which is an optional dependency:

```bash
pip install "rubbernecker[server]"
# or with uv:
uv sync --extra server
```

## Running the Server

```bash
uv run rubbernecker server --root /path/to/datasets
```

The server starts on `http://127.0.0.1:7707` by default.

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--root PATH` | _(required)_ | Root directory to monitor |
| `--host HOST` | `127.0.0.1` | Interface to bind to |
| `--port PORT` | `7707` | Port to listen on |

### Examples

```bash
# Monitor the current directory
uv run rubbernecker server --root .

# Bind on all interfaces (e.g. for remote access)
uv run rubbernecker server --root /data/crawls --host 0.0.0.0 --port 8080
```

## Directory Layout

The server discovers datasets by walking `--root` recursively. It recognises two kinds of directories:

**Crawl dataset** — a directory containing `pages.avro` alongside one of:
- `urls.txt` (plain text, one URL per line)
- `urls.jsonl` (JSON Lines, each record has a `"url"` field)
- `urls.avro` (Avro, e.g. output from `rubbernecker sitemap`)

**Generic Avro dataset** — any directory containing `.avro` files that does not meet the crawl dataset criteria.

Example layout:

```
datasets/
├── hn-crawl/
│   ├── urls.txt          # input — detected automatically
│   └── pages.avro        # crawl output
├── hn-pipeline/
│   ├── pages.avro        # stage 1
│   └── parsed.avro       # stage 2 (parse output)
└── sitemaps/
    └── entries.avro      # generic dataset
```

## Pages

### Index (`/`)

Lists all discovered directories. Each directory shows:

- Relative path (linked to the directory detail page)
- A **Crawl Dataset** badge if `pages.avro` + `urls.*` are present
- A table of `.avro` files with record counts and last-modified timestamps

### Directory Detail (`/dir/<rel_path>`)

For **crawl datasets**, shows a status card equivalent to `rubbernecker status`:

- Total input URLs, processed count, and percentage
- Success and error counts with error rate
- Overall and recent pages/sec rates
- Crawl start time, last record time, and ETA

When a directory contains more than one `.avro` file, a **Pipeline** section lists the files in modification-time order and shows the record count delta between each adjacent stage (useful for spotting parse failures or enrichment drops).

All `.avro` files in the directory are also listed and linked to their file detail pages.

### File Detail (`/file/<rel_path>`)

For any `.avro` file, shows:

- The embedded Avro **schema** as formatted JSON
- A paginated **records table** (25 records per page by default)

Pagination query parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `offset` | `0` | Record offset to start from |
| `limit` | `25` | Number of records per page |

Example: `/file/hn-crawl/pages.avro?offset=50&limit=10`

## SQLite Cache

On first load the server writes a `db.sqlite` file inside `--root`. This caches record counts and schema names keyed by `(path, mtime)` so repeated page loads on large files are fast. The cache is invalidated automatically when a file's modification time changes. It is safe to delete `db.sqlite` at any time — it will be rebuilt on the next request.

## Limitations

- **Read-only** — the server never launches or modifies crawls.
- **No authentication** — do not expose the server publicly without an external auth layer.
- **Development server only** — for production-style deployments use Gunicorn:
  ```bash
  gunicorn "rubbernecker.server.app:create_app(root='/path/to/datasets')" \
      --bind 0.0.0.0:7707 --workers 2
  ```
- **No background polling** — all data is read from disk on each page load.
