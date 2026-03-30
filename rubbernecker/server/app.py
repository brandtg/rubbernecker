# SPDX-FileCopyrightText: 2026 Greg Brandt <brandt.greg@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0

import os

from flask import Flask, abort, current_app, render_template, request

from rubbernecker.server.cache import init_db
from rubbernecker.server.discovery import discover_directories


def create_app(root: str) -> Flask:
    app = Flask(__name__)
    app.config["ROOT"] = root

    @app.template_filter("basename")
    def _basename(path: str) -> str:
        return os.path.basename(path)

    @app.route("/")
    def index():
        root = current_app.config["ROOT"]
        db_path = os.path.join(root, "db.sqlite")
        init_db(db_path)
        directories = discover_directories(root, db_path)
        return render_template("index.html", directories=directories)

    @app.route("/dir/<path:rel_path>")
    def directory_detail(rel_path: str):
        from rubbernecker.server.status import get_status_result

        root = current_app.config["ROOT"]
        db_path = os.path.join(root, "db.sqlite")
        init_db(db_path)
        directories = discover_directories(root, db_path)
        directory = next((d for d in directories if d.rel_path == rel_path), None)
        if directory is None:
            abort(404)
        status_result = None
        if directory.is_crawl_dataset and directory.input_url_path:
            pages_path = os.path.join(directory.path, "pages.avro")
            status_result = get_status_result(directory.input_url_path, pages_path)
        from rubbernecker.server.pipeline import compute_deltas, order_pipeline_stages

        ordered_files = order_pipeline_stages(directory.files)
        deltas = compute_deltas(ordered_files)
        return render_template(
            "directory.html",
            directory=directory,
            status_result=status_result,
            ordered_files=ordered_files,
            deltas=deltas,
        )

    @app.route("/file/<path:rel_path>")
    def file_detail(rel_path: str):
        from rubbernecker.server.reader import get_records_page, get_schema_json

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

    return app
