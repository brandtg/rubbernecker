# PRD: Rubbernecker Admin Server

**Date:** 2026-03-29
**Status:** Review

## 1. Summary/Overview

Rubbernecker currently operates exclusively via a CLI — users must manually invoke commands and inspect raw Avro files to understand what is happening across their crawl pipeline. As dataset volumes grow, navigating file paths and running one-off CLI commands becomes tedious and error-prone.

The Admin Server is a lightweight, local Flask web application that provides a read-only monitoring and introspection dashboard over a user-specified root directory containing rubbernecker crawl artifacts. It surfaces crawl status, dataset metadata, and light data previews without requiring the user to leave their browser.

**Primary goals:**

- Give operators a single-pane-of-glass view of all datasets in a working directory
- Surface the output of `rubbernecker status` in a human-friendly UI
- Allow light introspection of Avro data (schema, record count, sample records) without needing the CLI
- Remain read-only and filesystem-driven; `db.sqlite` is used only as a performance cache, never as a source of truth

**Target audience:** Individual developers and small teams running rubbernecker pipelines locally or on a server.

## 2. Status Quo

- There is no visual dashboard; all monitoring requires manual CLI invocations (`rubbernecker status`, `avrokit count`, `avrokit getschema`, etc.)
- There is no concept of a "dataset" in the codebase — a dataset is implicitly a pair of input URL file + output Avro file(s) chosen by the user via path conventions
- Users must know the exact file paths for both input and output to run `rubbernecker status`
- Inspecting Avro file contents requires piping through `avrokit tojson` or `avrokit cat`
- There is no aggregated view across multiple crawls or pipeline stages

## 3. Proposed Change

A Flask application (`rubbernecker/server/`) is started with a root directory to monitor and optional host/port flags. The server walks the directory tree, discovers Avro files and their companion input URL files by naming convention, and renders a Jinja2-templated dashboard.

The server is **read-only** (no crawl launching). All state derives from the filesystem at request time. A `db.sqlite` file is written to `--root` to cache derived values (e.g., record counts, historical rate snapshots) that would otherwise require expensive per-request Avro reads.

**File naming conventions (fixed):**

- Crawl input: `urls.txt`, `urls.jsonl`, or `urls.avro` in a dataset directory
- Crawl output: `pages.avro` in the same directory
- Auto-detection: if `pages.avro` is found, the server looks for `urls.*` alongside it to classify the directory as a crawl dataset

**Intended UX:**

1. User runs `rubbernecker server --root /path/to/datasets`
2. Browser opens to `http://localhost:7707`
3. Dashboard lists all discovered datasets grouped by directory, with status summary cards
4. Clicking a dataset shows a detail view: progress, timing, ETA, schema, and paginated sample records
5. All data refreshes on page load; no background polling

## 4. Features

### Dataset Discovery

**Description:** On each request, the server walks the `--root` directory tree and discovers Avro files. Directories are grouped into pipelines. A directory containing `pages.avro` alongside a `urls.*` file is classified as a crawl dataset; all other `.avro` files are surfaced as generic Avro datasets.

**Acceptance Criteria:**

- [ ] Server discovers all `.avro` files under `--root` recursively
- [ ] Datasets are listed on the index page with filename, record count, and last-modified timestamp
- [ ] A directory containing `pages.avro` + `urls.txt` / `urls.jsonl` / `urls.avro` is classified as a crawl dataset and enables the status view
- [ ] Directories with multiple `.avro` files are grouped as a pipeline
- [ ] Discovery is performed at request time (no background polling)

### Crawl Status View

**Description:** For any crawl dataset (`pages.avro` + `urls.*` pair), renders the equivalent of `rubbernecker status --input <urls.*> --output pages.avro` as a formatted dashboard card or detail page, reusing `StatusTool` internals as a library call.

**Acceptance Criteria:**

- [ ] Displays total input URLs, processed count, successes, errors, and remaining
- [ ] Displays overall pages/sec rate and recent (rolling window) pages/sec rate
- [ ] Displays crawl start time, last record time, and ETA
- [ ] Handles in-progress crawls gracefully (partial Avro file is readable without crashing)
- [ ] Falls back gracefully if no companion input file is found (shows record count only)

### Avro File Introspection

**Description:** For any `.avro` file, surfaces the Avro schema, total record count, and a paginated read-only sample of decoded records rendered as an HTML table via Jinja2.

**Acceptance Criteria:**

- [ ] Schema view shows the Avro schema as formatted JSON
- [ ] Record count is displayed (using `avrokit CountTool` for efficiency on large files)
- [ ] Sample view shows the first N records (default: 25) as an HTML table with schema fields as columns
- [ ] Offset-based pagination controls allow browsing forward and backward through records
- [ ] Records are streamed from disk; the full file is never loaded into memory

### Pipeline Stage View

**Description:** When multiple Avro files exist in the same directory (e.g., `pages.avro`, `parsed.avro`), the directory detail page groups them as a pipeline and shows record count progression through stages.

**Acceptance Criteria:**

- [ ] Files in the same directory are grouped under a pipeline view on the directory detail page
- [ ] Each stage shows its filename, Avro schema name, and record count
- [ ] Record count delta between adjacent stages is surfaced (e.g., parse failures, enrichment additions)
- [ ] Stage order is determined by file modification time when no explicit convention applies

## 5. Implementation Phases

### Phase 1: Project Scaffold & Dataset Discovery

- Create `rubbernecker/server/` package with `app.py` (Flask app factory) and `tool.py` (`ServerTool` implementing the `Tool` protocol)
- `ServerTool.configure()` registers `--root` (required), `--port` (default: `7707`), and `--host` (default: `127.0.0.1`) flags
- Register `ServerTool` in `rubbernecker/__main__.py`
- Implement filesystem walker that discovers `.avro` files under `--root` and classifies directories
- Implement record count using `avrokit CountTool`; cache results in `db.sqlite` under `--root`
- Render index page listing datasets with filename, record count, and last-modified time
- `flask` is already declared in `pyproject.toml` under `[project.optional-dependencies] server`; install with `uv sync --extra server`

### Phase 2: Crawl Status Integration

- Implement `urls.*` auto-detection: scan the same directory as `pages.avro` for `urls.txt`, `urls.jsonl`, or `urls.avro`
- Reuse `StatusTool` internals (not the CLI entrypoint) as a library call to compute `StatusToolResult`
- Render crawl status card on the dataset detail page (progress bar, rates, ETA)
- Handle partial/in-progress Avro files without crashing; surface whatever partial data is available

### Phase 3: Avro Introspection UI

- Implement schema view: open file with `avrokit avro_reader`, extract and render schema as formatted JSON
- Implement sample records view with configurable page size and offset-based pagination
- Render records as an HTML table via Jinja2 (columns = Avro schema fields)
- Stream records from disk; never load the full file into memory

### Phase 4: Pipeline Grouping

- Group `.avro` files by parent directory on directory detail pages
- Order stages by file modification time
- Render stage progression with per-stage record counts and deltas
- Extend `db.sqlite` schema as needed to cache per-file metadata across requests

## 6. Considerations

- **Data modeling:** All server-side models use `@dataclass`, consistent with the rest of the rubbernecker codebase. No Pydantic dependency is introduced. SQLite rows are deserialized via `@classmethod from_row(cls, row: tuple)` on each dataclass for full type-checker coverage.

- **Partial Avro reads:** In-progress crawls produce partially written Avro files. All reads must be wrapped in `try/except`; partial data should be surfaced rather than returning an error page. The `avrokit repair` utility may be used as a fallback.

- **Record count performance:** `CountTool` uses Avro block-counting (no full deserialization) and is fast on large files. Counts are cached in `db.sqlite` keyed by `(path, mtime)` so repeated page loads do not re-read the file unless it has changed.

- **Concurrency:** Flask's development server is used with `threaded=True`. For production-style deployments, Gunicorn is recommended but not bundled.

- **Dependencies:**
  - `avrokit >= 0.0.7` — all Avro I/O (`avro_reader`, `CountTool`, schema extraction)
  - `flask >= 3.0` — web framework and Jinja2 templating; installable via `rubbernecker[server]` optional extra
  - `sqlite3` — standard library; caches derived data (record counts, mtimes) in `db.sqlite` under `--root`
  - `rubbernecker.status.tool.StatusTool` — reused as a library for crawl status computation

## 7. Revisions

| Date       | Author      | Changes                                              |
| ---------- | ----------- | ---------------------------------------------------- |
| 2026-03-29 | Greg Brandt | Initial draft                                        |
| 2026-03-29 | Greg Brandt | Resolved open questions; promoted to Review status   |
