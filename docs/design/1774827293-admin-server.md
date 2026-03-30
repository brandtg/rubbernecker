<!--
SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>

SPDX-License-Identifier: Apache-2.0
-->

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

- [x] Server discovers all `.avro` files under `--root` recursively
- [x] Datasets are listed on the index page with filename, record count, and last-modified timestamp
- [x] A directory containing `pages.avro` + `urls.txt` / `urls.jsonl` / `urls.avro` is classified as a crawl dataset and enables the status view
- [x] Directories with multiple `.avro` files are grouped as a pipeline
- [x] Discovery is performed at request time (no background polling)

### Crawl Status View

**Description:** For any crawl dataset (`pages.avro` + `urls.*` pair), renders the equivalent of `rubbernecker status --input <urls.*> --output pages.avro` as a formatted dashboard card or detail page, reusing `StatusTool` internals as a library call.

**Acceptance Criteria:**

- [x] Displays total input URLs, processed count, successes, errors, and remaining
- [x] Displays overall pages/sec rate and recent (rolling window) pages/sec rate
- [x] Displays crawl start time, last record time, and ETA
- [x] Handles in-progress crawls gracefully (partial Avro file is readable without crashing)
- [ ] Falls back gracefully if no companion input file is found (shows record count only) *(failing — section is hidden entirely when no `urls.*` companion exists; see [Future Work](#future-work))*

### Avro File Introspection

**Description:** For any `.avro` file, surfaces the Avro schema, total record count, and a paginated read-only sample of decoded records rendered as an HTML table via Jinja2.

**Acceptance Criteria:**

- [x] Schema view shows the Avro schema as formatted JSON
- [x] Record count is displayed (using `avrokit CountTool` for efficiency on large files)
- [x] Sample view shows the first N records (default: 25) as an HTML table with schema fields as columns
- [x] Offset-based pagination controls allow browsing forward and backward through records
- [x] Records are streamed from disk; the full file is never loaded into memory

### Pipeline Stage View

**Description:** When multiple Avro files exist in the same directory (e.g., `pages.avro`, `parsed.avro`), the directory detail page groups them as a pipeline and shows record count progression through stages.

**Acceptance Criteria:**

- [x] Files in the same directory are grouped under a pipeline view on the directory detail page
- [x] Each stage shows its filename, Avro schema name, and record count
- [x] Record count delta between adjacent stages is surfaced (e.g., parse failures, enrichment additions)
- [x] Stage order is determined by file modification time when no explicit convention applies

## 5. Implementation Phases

> **Testing conventions for all phases:**
> - All tests live in `tests/` alongside existing test files (e.g., `tests/test_server_discovery.py`).
> - Use `tempfile.TemporaryDirectory()` as a context manager for disk I/O — not pytest `tmp_path` — to stay consistent with the majority of the existing test suite.
> - Write real Avro files on disk using `avrokit.avro_writer` + `avrokit.parse_url` with the production schemas imported directly from `rubbernecker`. Never mock the Avro layer.
> - Use `unittest.mock.patch` (not `pytest.monkeypatch`) when patching is needed.
> - Mark any test that requires a running Flask server or live network as `@pytest.mark.integration`. All other tests must run without a server process.
> - All tests for a phase must pass (`pytest`) before beginning the next phase.

---

### Phase 1a: Package Scaffold & CLI Registration

**Goal:** Create the `rubbernecker/server/` package and wire the `ServerTool` into the CLI. No logic yet — just structure and a smoke-test that `rubbernecker server --help` works.

#### Steps

1. **Create the package directory.**
   Create `rubbernecker/server/__init__.py` (empty, with SPDX header matching existing files).

2. **Create `rubbernecker/server/tool.py`.**
   Define `ServerTool` implementing the `Tool` protocol from `rubbernecker.base`:
   ```python
   class ServerTool:
       def name(self) -> str:
           return "server"

       def configure(self, subparsers) -> None:
           parser = subparsers.add_parser("server", help="Start the admin server")
           parser.add_argument("--root", required=True, help="Root directory to monitor")
           parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
           parser.add_argument("--port", type=int, default=7707, help="Bind port (default: 7707)")

       def run(self, args) -> None:
           from rubbernecker.server.app import create_app
           app = create_app(root=args.root)
           app.run(host=args.host, port=args.port, threaded=True)
   ```

3. **Create `rubbernecker/server/app.py`.**
   Define a minimal Flask app factory that stores `root` in `app.config`:
   ```python
   from flask import Flask

   def create_app(root: str) -> Flask:
       app = Flask(__name__)
       app.config["ROOT"] = root
       return app
   ```

4. **Register `ServerTool` in `rubbernecker/__main__.py`.**
   Import `ServerTool` and add it to the list of tools passed to the argument parser, following the exact pattern used for `CrawlTool`, `ParseTool`, etc.

#### Tests — `tests/test_server_tool.py`

- **`test_server_tool_name`**: Instantiate `ServerTool()` and assert `.name() == "server"`.
- **`test_server_tool_configure_registers_subcommand`**: Create an `argparse.ArgumentParser`, add a subparsers action, call `ServerTool().configure(subparsers)`, then parse `["server", "--root", "/tmp"]` and assert `args.root == "/tmp"`, `args.host == "127.0.0.1"`, `args.port == 7707`.
- **`test_server_tool_configure_custom_host_port`**: Parse `["server", "--root", "/tmp", "--host", "0.0.0.0", "--port", "8080"]` and assert correct values.
- **`test_create_app_stores_root`**: Call `create_app(root="/some/path")` and assert `app.config["ROOT"] == "/some/path"`.

---

### Phase 1b: Data Models & SQLite Cache

**Goal:** Define all server-side dataclasses and the SQLite cache layer. No Flask routes yet.

#### Steps

1. **Create `rubbernecker/server/models.py`.**
   Define the following dataclasses. All fields must be fully type-annotated. Each model that maps to a SQLite row must have a `@classmethod from_row(cls, row: tuple) -> "ClassName"` method.

   ```python
   @dataclass
   class AvroFileInfo:
       """Metadata about a single .avro file discovered on disk."""
       path: str                  # absolute path
       rel_path: str              # path relative to --root
       mtime: float               # os.stat mtime
       record_count: int | None   # None if not yet cached
       schema_name: str | None    # None if not yet read

       @classmethod
       def from_row(cls, row: tuple) -> "AvroFileInfo": ...

   @dataclass
   class DirectoryInfo:
       """A directory under --root containing one or more .avro files."""
       path: str                       # absolute path
       rel_path: str                   # path relative to --root
       files: list[AvroFileInfo]       # all .avro files in this directory
       is_crawl_dataset: bool          # True if pages.avro + urls.* present
       input_url_path: str | None      # absolute path to urls.* if found
   ```

2. **Create `rubbernecker/server/cache.py`.**
   Implement the SQLite cache with these functions:
   - `init_db(db_path: str) -> None` — creates the `file_cache` table if it does not exist:
     ```sql
     CREATE TABLE IF NOT EXISTS file_cache (
         path TEXT PRIMARY KEY,
         mtime REAL NOT NULL,
         record_count INTEGER,
         schema_name TEXT
     )
     ```
   - `get_cached(db_path: str, path: str, mtime: float) -> tuple[int, str] | None` — returns `(record_count, schema_name)` if a row exists for `path` with a matching `mtime`, otherwise `None`.
   - `set_cached(db_path: str, path: str, mtime: float, record_count: int, schema_name: str) -> None` — inserts or replaces a row.

#### Tests — `tests/test_server_cache.py`

- **`test_init_db_creates_table`**: Call `init_db` on a temp path, then open the sqlite3 connection directly and assert the `file_cache` table exists with the correct columns.
- **`test_get_cached_miss_empty_db`**: Call `get_cached` on a fresh DB for any path — assert it returns `None`.
- **`test_set_and_get_cached_hit`**: Call `set_cached(path="/a.avro", mtime=1.0, record_count=42, schema_name="Page")`, then `get_cached(path="/a.avro", mtime=1.0)` — assert it returns `(42, "Page")`.
- **`test_get_cached_miss_stale_mtime`**: Insert a row with `mtime=1.0`, then call `get_cached` with `mtime=2.0` — assert it returns `None`.
- **`test_set_cached_overwrites_existing`**: Insert a row, then insert again with the same path but different `mtime`/`record_count` — assert `get_cached` returns the new values.

---

### Phase 1c: Filesystem Walker & Index Route

**Goal:** Implement the directory walker and the `/` index route that lists all discovered datasets.

#### Steps

1. **Create `rubbernecker/server/discovery.py`.**
   Implement two functions:

   - `find_avro_files(root: str) -> list[AvroFileInfo]`
     Walk `root` recursively using `os.walk`. For each `.avro` file found, construct an `AvroFileInfo` with `path`, `rel_path` (relative to root), and `mtime` from `os.stat`. Set `record_count=None` and `schema_name=None` — these are populated by the cache layer separately.

   - `discover_directories(root: str, db_path: str) -> list[DirectoryInfo]`
     Call `find_avro_files(root)`. Group files by their parent directory. For each directory group:
     - Check if a file named `pages.avro` exists in the group.
     - If so, scan the directory for `urls.txt`, `urls.jsonl`, or `urls.avro` (in that priority order) and set `is_crawl_dataset=True` and `input_url_path` accordingly.
     - For each `AvroFileInfo` in the group, attempt a cache lookup via `get_cached(db_path, path, mtime)`. If it hits, populate `record_count` and `schema_name`. If it misses, use `avrokit.CountTool` to count records and `avrokit.avro_reader` to read the schema name, then call `set_cached`.
     - Return `list[DirectoryInfo]` sorted by `rel_path`.

2. **Add the index route to `app.py`.**
   ```python
   @app.route("/")
   def index():
       root = current_app.config["ROOT"]
       db_path = os.path.join(root, "db.sqlite")
       init_db(db_path)
       directories = discover_directories(root, db_path)
       return render_template("index.html", directories=directories)
   ```

3. **Create `rubbernecker/server/templates/index.html`.**
   Minimal Jinja2 template. For each directory:
   - Show the relative path as a heading.
   - List each `.avro` file with its `rel_path`, `record_count`, and `mtime` (formatted as a human-readable datetime).
   - If `is_crawl_dataset`, badge the directory as "Crawl Dataset".
   - Link each directory to `/dir/<path:rel_path>` (route added in Phase 2).

   No CSS frameworks required — plain HTML is acceptable for v1.

#### Tests — `tests/test_server_discovery.py`

- **`test_find_avro_files_empty_dir`**: Create a temp directory with no files. Assert `find_avro_files(tmpdir)` returns `[]`.
- **`test_find_avro_files_single_file`**: Write one real `.avro` file (use `avrokit.avro_writer` with `PAGE_SCHEMA`). Assert the result contains one `AvroFileInfo` with correct `path`, non-zero `mtime`, and `record_count=None`.
- **`test_find_avro_files_nested`**: Write `.avro` files in two subdirectories. Assert all files are discovered.
- **`test_find_avro_files_ignores_non_avro`**: Write `urls.txt` and `output.json` alongside an `.avro` file. Assert only the `.avro` file is returned.
- **`test_discover_directories_crawl_dataset_detection`**: Write `pages.avro` + `urls.txt` in a subdirectory. Assert the resulting `DirectoryInfo` has `is_crawl_dataset=True` and `input_url_path` pointing to `urls.txt`.
- **`test_discover_directories_not_crawl_without_urls`**: Write only `pages.avro` with no `urls.*` alongside it. Assert `is_crawl_dataset=False`.
- **`test_discover_directories_populates_record_count_from_avro`**: Write an Avro file with 3 records. Assert the `AvroFileInfo` in the result has `record_count=3`.
- **`test_discover_directories_uses_cache_on_second_call`**: Write an Avro file, call `discover_directories` twice. Use `unittest.mock.patch` on `avrokit.CountTool` to assert it is called exactly once (second call hits the cache).

---

### Phase 2: Crawl Status Integration

**Goal:** Add a dataset detail route that renders the full `StatusToolResult` for crawl datasets.

#### Steps

1. **Add a helper `get_status_result` to `rubbernecker/server/status.py`.**
   This wraps the `StatusTool` library call so the route handler stays thin:
   ```python
   from rubbernecker.status.tool import StatusTool, StatusToolResult

   def get_status_result(
       input_path: str,
       output_path: str,
       window: int = 100,
   ) -> StatusToolResult | None:
       """Return a StatusToolResult, or None if the output file is unreadable."""
       tool = StatusTool()
       try:
           return tool.status(
               input_url_strs=[input_path],
               output_url_strs=[output_path],
               input_format="text",   # detect format from extension if needed
               window=window,
           )
       except Exception:
           return None
   ```
   Detect the input format from the file extension: `.txt` → `text`, `.jsonl` → `json`, `.avro` → `avro`.

2. **Add the directory detail route to `app.py`.**
   ```python
   @app.route("/dir/<path:rel_path>")
   def directory_detail(rel_path: str):
       root = current_app.config["ROOT"]
       db_path = os.path.join(root, "db.sqlite")
       init_db(db_path)
       directories = discover_directories(root, db_path)
       # Find the matching DirectoryInfo
       directory = next((d for d in directories if d.rel_path == rel_path), None)
       if directory is None:
           abort(404)
       status_result = None
       if directory.is_crawl_dataset and directory.input_url_path:
           pages_path = os.path.join(directory.path, "pages.avro")
           status_result = get_status_result(directory.input_url_path, pages_path)
       return render_template(
           "directory.html",
           directory=directory,
           status_result=status_result,
       )
   ```

3. **Create `rubbernecker/server/templates/directory.html`.**
   - Show the directory `rel_path` as a heading.
   - If `status_result` is not `None`:
     - Show a progress section: processed / total (as a fraction and percentage).
     - Show success count, error count, and error rate.
     - Show overall and recent pages/sec rates.
     - Show crawl start time, last record time, and ETA.
   - List all `.avro` files in the directory with their record counts (same as the index listing).
   - Each `.avro` file links to `/file/<path:rel_path>` (route added in Phase 3).

#### Tests — `tests/test_server_status.py`

- **`test_get_status_result_text_input`**: Write a `urls.txt` with 5 URLs and a `pages.avro` with 3 corresponding Page records. Call `get_status_result(input_path, output_path)`. Assert the result is a `StatusToolResult` with `count_input=5`, `count_processed=3`.
- **`test_get_status_result_jsonl_input`**: Same but with `urls.jsonl` as input. Assert correct counts.
- **`test_get_status_result_avro_input`**: Same but with a `SitemapEntry` Avro file as input.
- **`test_get_status_result_returns_none_on_corrupt_output`**: Write a valid `urls.txt` but write garbage bytes to `pages.avro`. Assert `get_status_result` returns `None` without raising.
- **`test_directory_detail_route_crawl_dataset`** (Flask test client): Create the app with a temp root containing `pages.avro` + `urls.txt`. Use `app.test_client()` to GET `/dir/<rel_path>`. Assert HTTP 200 and that the response body contains "processed" or the URL count.
- **`test_directory_detail_route_404`**: GET `/dir/nonexistent`. Assert HTTP 404.

---

### Phase 3: Avro Introspection UI

**Goal:** Add a file detail route that shows the Avro schema and paginated sample records.

#### Steps

1. **Create `rubbernecker/server/reader.py`.**
   Implement two functions:

   - `get_schema_json(path: str) -> str | None`
     Open the Avro file with `avrokit.avro_reader`. Access `reader.GetMeta("avro.schema")` (the raw bytes of the embedded schema), decode as UTF-8, and return it as a pretty-printed JSON string. Return `None` on any exception.

   - `get_records_page(path: str, offset: int, limit: int) -> tuple[list[dict], bool]`
     Open the Avro file with `avrokit.avro_reader`. Skip the first `offset` records by iterating (do not load into memory). Collect up to `limit` records into a list. Return `(records, has_more)` where `has_more` is `True` if there are records beyond `offset + limit`. Never hold more than `limit + 1` records in memory at once.

2. **Add the file detail route to `app.py`.**
   ```python
   @app.route("/file/<path:rel_path>")
   def file_detail(rel_path: str):
       root = current_app.config["ROOT"]
       abs_path = os.path.join(root, rel_path)
       if not os.path.isfile(abs_path) or not rel_path.endswith(".avro"):
           abort(404)
       offset = request.args.get("offset", 0, type=int)
       limit = request.args.get("limit", 25, type=int)
       schema_json = get_schema_json(abs_path)
       records, has_more = get_records_page(abs_path, offset=offset, limit=limit)
       return render_template(
           "file.html",
           rel_path=rel_path,
           schema_json=schema_json,
           records=records,
           offset=offset,
           limit=limit,
           has_more=has_more,
       )
   ```

3. **Create `rubbernecker/server/templates/file.html`.**
   - Show `rel_path` as the page heading.
   - Show the schema as a `<pre><code>` block (formatted JSON).
   - Render records as an HTML table. Use the keys of the first record as column headers. Render each value as its string representation (truncated to 200 chars if necessary to keep the table readable).
   - Show pagination controls: "Previous" link (if `offset > 0`) and "Next" link (if `has_more`). Links should adjust the `offset` query parameter by `limit`.

#### Tests — `tests/test_server_reader.py`

- **`test_get_schema_json_returns_valid_json`**: Write a real Avro file with `PAGE_SCHEMA`. Call `get_schema_json`. Assert the result parses as JSON and contains the key `"name"` with value `"Page"`.
- **`test_get_schema_json_returns_none_on_corrupt_file`**: Write garbage bytes to a `.avro` path. Assert `get_schema_json` returns `None`.
- **`test_get_records_page_first_page`**: Write an Avro file with 10 records. Call `get_records_page(offset=0, limit=5)`. Assert 5 records returned and `has_more=True`.
- **`test_get_records_page_last_page`**: Call `get_records_page(offset=8, limit=5)` on a 10-record file. Assert 2 records returned and `has_more=False`.
- **`test_get_records_page_exact_boundary`**: Call `get_records_page(offset=5, limit=5)` on a 10-record file. Assert 5 records returned and `has_more=False`.
- **`test_get_records_page_beyond_end`**: Call `get_records_page(offset=20, limit=5)` on a 10-record file. Assert empty list and `has_more=False`.
- **`test_file_detail_route_200`** (Flask test client): Write a real Avro file. GET `/file/<rel_path>`. Assert HTTP 200 and the schema name appears in the response body.
- **`test_file_detail_route_404_nonexistent`**: GET `/file/no/such/file.avro`. Assert HTTP 404.
- **`test_file_detail_route_404_non_avro`**: Write a `urls.txt`. GET `/file/urls.txt`. Assert HTTP 404.

---

### Phase 4: Pipeline Grouping

**Goal:** Extend the directory detail page to show all `.avro` files in a directory as an ordered pipeline with record count deltas between stages.

#### Steps

1. **Create `rubbernecker/server/pipeline.py`.**
   Implement:

   - `order_pipeline_stages(files: list[AvroFileInfo]) -> list[AvroFileInfo]`
     Sort files by `mtime` ascending. If two files share an identical `mtime`, sort alphabetically by filename as a tiebreaker.

   - `compute_deltas(files: list[AvroFileInfo]) -> list[int | None]`
     Given an ordered list of `AvroFileInfo`, return a parallel list of deltas where `deltas[i]` is `files[i].record_count - files[i-1].record_count` for `i > 0`, and `None` for `i == 0`. If either adjacent file has `record_count=None`, the delta is `None`.

2. **Update `rubbernecker/server/templates/directory.html`.**
   - If the directory contains more than one `.avro` file, add a "Pipeline" section above the file list.
   - Render each stage as a row: stage number, filename, schema name, record count, and delta from the previous stage (show `+N`, `-N`, or `—` if unavailable).

3. **Update `discovery.py` to populate `schema_name`.**
   When reading schema from an Avro file (either from cache or from a fresh read), store the top-level Avro schema name (e.g., `"Page"`, `"StandardPage"`) in `AvroFileInfo.schema_name` and persist it in the cache. This was stubbed as `None` in Phase 1b — implement it now.

   To extract the schema name: open the file with `avrokit.avro_reader`, read `reader.datum_reader.writers_schema.name` or parse the embedded `avro.schema` metadata.

#### Tests — `tests/test_server_pipeline.py`

- **`test_order_pipeline_stages_by_mtime`**: Construct three `AvroFileInfo` instances with mtimes `3.0`, `1.0`, `2.0`. Assert `order_pipeline_stages` returns them in ascending mtime order.
- **`test_order_pipeline_stages_alpha_tiebreak`**: Two files with identical mtime — assert they are sorted alphabetically by filename.
- **`test_compute_deltas_first_element_is_none`**: Three files with record counts `[100, 90, 45]`. Assert `compute_deltas` returns `[None, -10, -45]`.
- **`test_compute_deltas_with_none_record_count`**: One file has `record_count=None`. Assert the delta for that stage and the adjacent stage are both `None`.
- **`test_schema_name_populated_in_discovery`**: Write a real Avro file with `PAGE_SCHEMA`. Call `discover_directories`. Assert the `AvroFileInfo` has `schema_name="Page"`.
- **`test_schema_name_cached`**: Write a real Avro file, call `discover_directories` twice. Patch the avro reader to assert the file is only opened once (second call reads from cache).

## 7. Future Work

The following gaps were identified during the initial implementation audit. They are punted from v1 but should be addressed before the server is recommended for production use.

### Path Traversal Guard on `/file/` Route

**Problem:** `app.py` validates that the resolved path `isfile` and ends with `.avro`, but does not verify the resolved absolute path is contained within `--root`. A crafted `rel_path` containing `../` segments could serve a valid Avro file located outside the root directory.

**Proposed fix:** After computing `abs_path = os.path.join(root, rel_path)`, assert that `os.path.commonpath([root, abs_path]) == os.path.realpath(root)`. Return HTTP 400 or 404 if the check fails.

**Acceptance Criteria:**
- [ ] `/file/` route rejects any `rel_path` that resolves outside `--root` with HTTP 404
- [ ] Test: construct a symlink or `../` path that points outside root and assert 404

---

### Pre-format Timestamps in the View Layer

**Problem:** `directory.html` calls `status_result._format_ts(...)` directly from Jinja2. This couples the template to the internal API of `StatusToolResult`, making the template fragile and untestable in isolation.

**Proposed fix:** Pre-format `first_timestamp` and `last_timestamp` in the route handler (or in a thin view-model dataclass) before passing them to the template. Expose `formatted_start`, `formatted_last` as plain strings in the template context.

**Acceptance Criteria:**
- [ ] `directory.html` no longer calls any Python method directly; all values are pre-formatted strings
- [ ] Template test (or route test) can verify timestamp display without importing `StatusToolResult`

---

### Offset Cap on `/file/` Pagination

**Problem:** `get_records_page(path, offset, limit)` iterates through `offset` records on every request to seek to the desired position. There is no upper bound on `offset` or `limit`; a large `offset` on a multi-million-record file will cause a long-running request that blocks the server thread.

**Proposed fix:** Add configurable caps (e.g., `MAX_OFFSET = 100_000`, `MAX_LIMIT = 500`) enforced in the route handler before calling `get_records_page`. Return HTTP 400 with an explanatory message if the cap is exceeded.

**Acceptance Criteria:**
- [ ] Requests with `offset` > `MAX_OFFSET` return HTTP 400
- [ ] Requests with `limit` > `MAX_LIMIT` are clamped or rejected
- [ ] Caps are defined as module-level constants in `app.py` (not magic numbers)

---

### Remove Dead Code: `AvroFileInfo.from_row`

**Problem:** `AvroFileInfo.from_row()` is defined in `models.py` (per PRD spec) but never called. Cache deserialization is performed inline in `discovery.py` by directly constructing field values from the row tuple. The dead method adds noise and misleads readers into thinking it is the canonical deserialization path.

**Proposed fix:** Either remove `from_row` from `AvroFileInfo` and update the PRD spec to reflect this, or update `discovery.py` to actually call it for consistency with `DirectoryInfo` and the stated design intent.

**Acceptance Criteria:**
- [ ] No dead `from_row` method exists, OR `discovery.py` calls `AvroFileInfo.from_row` for all cache deserialization
- [ ] Section 6 ("Considerations") updated to reflect the chosen approach

---

## 8. Considerations

- **Data modeling:** All server-side models use `@dataclass`, consistent with the rest of the rubbernecker codebase. No Pydantic dependency is introduced. SQLite rows are deserialized via `@classmethod from_row(cls, row: tuple)` on each dataclass for full type-checker coverage.

- **Partial Avro reads:** In-progress crawls produce partially written Avro files. All reads must be wrapped in `try/except`; partial data should be surfaced rather than returning an error page. The `avrokit repair` utility may be used as a fallback.

- **Record count performance:** `CountTool` uses Avro block-counting (no full deserialization) and is fast on large files. Counts are cached in `db.sqlite` keyed by `(path, mtime)` so repeated page loads do not re-read the file unless it has changed.

- **Concurrency:** Flask's development server is used with `threaded=True`. For production-style deployments, Gunicorn is recommended but not bundled.

- **Dependencies:**
  - `avrokit >= 0.0.7` — all Avro I/O (`avro_reader`, `CountTool`, schema extraction)
  - `flask >= 3.0` — web framework and Jinja2 templating; installable via `rubbernecker[server]` optional extra
  - `sqlite3` — standard library; caches derived data (record counts, mtimes) in `db.sqlite` under `--root`
  - `rubbernecker.status.tool.StatusTool` — reused as a library for crawl status computation

## 9. Revisions

| Date       | Author      | Changes                                              |
| ---------- | ----------- | ---------------------------------------------------- |
| 2026-03-29 | Greg Brandt | Initial draft                                        |
| 2026-03-29 | Greg Brandt | Resolved open questions; promoted to Review status   |
| 2026-03-29 | Greg Brandt | Expanded phases into step-by-step playbook with tests |
| 2026-03-29 | Greg Brandt | Post-implementation audit: marked AC checkboxes; fixed AC 10 (degraded crawl view), mtime formatting; added Future Work section |
