# PRD: Rubbernecker Admin Server

**Date:** 2026-03-29
**Status:** Draft

## 1. Summary/Overview

Rubbernecker currently operates exclusively via a CLI — users must manually invoke commands and inspect raw Avro files to understand what is happening across their crawl pipeline. As dataset volumes grow, navigating file paths and running one-off CLI commands becomes tedious and error-prone.

The Admin Server is a lightweight, local Flask web application that provides a read-only monitoring and introspection dashboard over a user-specified root directory containing rubbernecker crawl artifacts. It surfaces crawl status, dataset metadata, and light data previews without requiring the user to leave their browser.

**Primary goals:**

- Give operators a single-pane-of-glass view of all datasets in a working directory
- Surface the output of `rubbernecker status` in a human-friendly UI
- Allow light introspection of Avro data (schema, record count, sample records) without needing the CLI
- Remain stateless by default — all state lives in the filesystem

**Target audience:** Individual developers and small teams running rubbernecker pipelines locally or on a server.

## 2. Status Quo

- There is no visual dashboard; all monitoring requires manual CLI invocations (`rubbernecker status`, `avrokit count`, `avrokit getschema`, etc.)
- There is no concept of a "dataset" in the codebase — a dataset is implicitly a pair of input URL file + output Avro file(s) chosen by the user via path conventions
- Users must know the exact file paths for both input and output to run `rubbernecker status`
- Inspecting Avro file contents requires piping through `avrokit tojson` or `avrokit cat`
- There is no aggregated view across multiple crawls or pipeline stages

## 3. Proposed Change

A Flask application (`rubbernecker/server/`) is started with a single argument: a root directory to monitor. The server walks the directory tree, discovers Avro files and their companion input URL files, and renders a dashboard.

The server is **read-only** (no crawl launching) and **stateless** by default — it derives all information from the filesystem at request time. An optional `db.sqlite` file may be introduced in the root directory if features require caching or derived data (e.g., historical rate snapshots), but only if driven by a concrete feature need.

**Intended UX:**

1. User runs `rubbernecker server --root /path/to/datasets`
2. Browser opens to `http://localhost:5000`
3. Dashboard lists all discovered datasets with status summary cards
4. Clicking a dataset shows a detail view: progress, timing, ETA, schema, sample records
5. All data refreshes on page load (no persistent background polling required initially)

## 4. Features

### Dataset Discovery

**Description:** On each request, the server walks the `--root` directory tree and discovers Avro files. A "dataset" is any `.avro` file (or directory of `.avro` files) found under root. Companion input URL files (`.txt`, `.jsonl`, or `.avro` URL lists) are auto-detected by naming convention or explicit pairing.

**Acceptance Criteria:**

- [ ] Server discovers all `.avro` files under `--root` recursively
- [ ] Datasets are listed on the index page with filename, record count, and last-modified timestamp
- [ ] If a companion input URL file is found alongside a crawl output, the dataset is shown as a "crawl dataset" (enabling status view)
- [ ] Discovery is performed at request time (no background polling)

### Crawl Status View

**Description:** For any crawl dataset (output Avro + input URL file pair), renders the equivalent of `rubbernecker status --input <input> --output <output>` as a formatted dashboard card or detail page.

**Acceptance Criteria:**

- [ ] Displays total input URLs, processed count, successes, errors, and remaining
- [ ] Displays overall pages/sec rate and recent (rolling window) pages/sec rate
- [ ] Displays crawl start time, last record time, and ETA
- [ ] Handles in-progress crawls gracefully (partial Avro file is readable)
- [ ] Falls back gracefully if no companion input file is found (shows record count only)

### Avro File Introspection

**Description:** For any `.avro` file, surfaces the Avro schema, total record count, and a paginated sample of decoded records (via `avrokit` reader).

**Acceptance Criteria:**

- [ ] Schema view shows the Avro schema as formatted JSON
- [ ] Record count is displayed (using `avrokit CountTool` for efficiency on large files)
- [ ] Sample view shows the first N records (default: 25) decoded as a JSON table or formatted list
- [ ] Pagination controls allow browsing through records
- [ ] Page handles large files without loading all records into memory

### Pipeline Stage View

**Description:** When multiple Avro files exist in the same directory (e.g., `raw.avro`, `parsed.avro`), group them as a pipeline and show the progression of record counts through stages.

**Acceptance Criteria:**

- [ ] Files in the same directory are grouped under a "pipeline" view
- [ ] Each stage shows its filename, record count, and schema name
- [ ] Record count drop or gain between stages is surfaced (e.g., parse failures)

## 5. Implementation Phases

### Phase 1: Project Scaffold & Dataset Discovery

- Create `rubbernecker/server/` package with `app.py` (Flask app factory) and `tool.py` (`ServerTool` implementing the `Tool` protocol)
- Register `ServerTool` in `rubbernecker/__main__.py`
- Implement filesystem walker that discovers `.avro` files under `--root`
- Implement record count using `avrokit CountTool`
- Render index page listing datasets with filename, record count, and last-modified time
- Add `flask` to `pyproject.toml` under `[project.optional-dependencies] server` (install with `pip install rubbernecker[server]` or `uv sync --extra server`)

### Phase 2: Crawl Status Integration

- Implement input URL file auto-detection (look for `.txt`/`.jsonl`/`.avro` file with matching stem in same directory)
- Wire `StatusTool` logic into server request handler (reuse existing `StatusTool` internals or call it as a library)
- Render crawl status card on dataset detail page (progress bar, rates, ETA)
- Handle partial/in-progress Avro files without crashing

### Phase 3: Avro Introspection UI

- Implement schema view using `avrokit avro_reader` to extract and display schema as formatted JSON
- Implement sample records view with configurable page size and offset-based pagination
- Render records as an HTML table (columns = schema fields)
- Ensure streaming reads so large files are never fully loaded into memory

### Phase 4: Pipeline Grouping

- Group `.avro` files by parent directory into pipeline views
- Detect stage ordering by filename convention or modification time
- Render pipeline stage progression on directory detail page
- Evaluate whether `db.sqlite` is needed to cache record counts for large datasets (decision gate)

## 6. Questions/Considerations

- **Technical Risks:**
  - In-progress Avro files may be partially written and cause reader errors; mitigation: wrap all reads in try/except and surface partial data where possible (avrokit `repair` may help)
  - Large Avro files could make per-request record counting slow; mitigation: use `CountTool` (block-count, not full deserialization) and consider a `db.sqlite` cache in Phase 4
  - Flask's development server is single-threaded; multiple simultaneous requests while reading large files could block; mitigation: use `threaded=True` or Gunicorn for non-dev use

- **Dependencies:**
  - `avrokit >= 0.0.7` — all Avro I/O (`avro_reader`, `CountTool`, schema extraction)
  - `flask >= 3.0` — web framework and Jinja2 templating; installable via `rubbernecker[server]` optional extra
  - `sqlite3` — standard library; used for caching derived data (record counts, historical rates) in `db.sqlite` under `--root`
  - `rubbernecker.status.tool.StatusTool` — reuse status logic as a library call

- **Open Questions:**
  - [ ] What is the naming convention users follow for input URL files alongside output Avro files? (e.g., same stem, or a fixed name like `urls.txt`?) This drives auto-detection logic.

The file will be named `urls.txt`, `urls.jsonl`, or `urls.avro` and must be in the same directory as the output Avro file. Similarly, the Avro file with the crawl output will be `pages.avro`. This convention allows for straightforward auto-detection: if `pages.avro` is found, look for `urls.*` in the same directory to pair it as a crawl dataset.

- [ ] Should the server support a `--port` flag, or always bind to `localhost:5000`?

Allow a --port flag, and let's default to 7707 to avoid conflicts with other local services. So the server would bind to `localhost:7707` by default, but users can specify a different port if needed.

- [ ] Should the sample records view support filtering or searching, or is read-only pagination sufficient for v1?

Read only pagination is sufficient. I just want to see the schema and a sample of records to verify the data looks correct.

- [ ] Is there a preference for a specific HTML templating approach (Jinja2 built into Flask, or a minimal JS frontend)?

Jinja2 is fine for v1.

- [ ] Should the server be accessible on the local network (0.0.0.0) or loopback only (127.0.0.1) by default?

Loopback only (but allow binding to local network via a `--host` flag if needed).

## 7. Revisions

| Date       | Author      | Changes       |
| ---------- | ----------- | ------------- |
| 2026-03-29 | Greg Brandt | Initial draft |
