"""The page is served with its module graph preloaded (ui_page.py): one fetch
level instead of an import waterfall, and the static files say how to cache."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_server import FakeEngine

from kuulas import server
from kuulas.session import Session
from kuulas.ui_page import index_html, module_graph, static_imports

UI = Path(__file__).parents[1] / "ui"


def test_static_imports_finds_every_form_of_relative_import():
    text = """
import * as api from "./api.js";
import { a, b } from './two.js';
import {
  c,
  d,
} from "./multi.js";
export { e } from "./re-export.js";
export * from "./star.js";
import "./side-effect.js";
import json from "https://example.org/not-ours.js";
const later = () => import("./dynamic.js");
"""
    assert static_imports(text) == [
        "api.js", "two.js", "multi.js", "re-export.js", "star.js", "side-effect.js"]


def write_graph(ui: Path, edges: dict[str, list[str]]) -> None:
    ui.mkdir(exist_ok=True)
    for name, deps in edges.items():
        lines = [f'import "./{dep}";' for dep in deps]
        (ui / name).write_text("\n".join(lines) + "\nexport const x = 1;\n")


def test_module_graph_is_breadth_first_without_the_entry_or_duplicates(tmp_path):
    write_graph(tmp_path, {
        "app.js": ["b.js", "c.js"],
        "b.js": ["d.js", "c.js"],
        "c.js": ["d.js"],
        "d.js": [],
        "unused.js": ["d.js"],
    })
    assert module_graph(tmp_path, "app.js") == ["b.js", "c.js", "d.js"]


def test_module_graph_skips_files_that_do_not_exist(tmp_path):
    # A stale import (or one in a comment) must not become a preload of a 404.
    write_graph(tmp_path, {"app.js": ["b.js", "gone.js"], "b.js": []})
    assert module_graph(tmp_path, "app.js") == ["b.js"]


def test_module_graph_survives_a_cycle(tmp_path):
    write_graph(tmp_path, {"app.js": ["b.js"], "b.js": ["app.js"]})
    assert module_graph(tmp_path, "app.js") == ["b.js"]


def test_index_html_preloads_the_graph_before_the_entry_script(tmp_path):
    write_graph(tmp_path, {"app.js": ["b.js"], "b.js": ["c.js"], "c.js": []})
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><title>x</title>\n'
        '    <script type="module" src="/app.js"></script>\n'
        '  </head><body></body></html>')
    page = index_html(tmp_path)
    links = [line.strip() for line in page.splitlines() if "modulepreload" in line]
    assert links == ['<link rel="modulepreload" href="/b.js" />',
                     '<link rel="modulepreload" href="/c.js" />']
    assert page.index("/b.js") < page.index("/c.js") < page.index('src="/app.js"')
    assert page.count('src="/app.js"') == 1


def test_the_real_page_preloads_every_module_app_js_reaches():
    graph = module_graph(UI, "app.js")
    assert len(graph) > 100
    assert all((UI / name).is_file() for name in graph)
    assert "app.js" not in graph
    page = index_html(UI)
    assert page.count('rel="modulepreload"') == len(graph)


@pytest.fixture
def client(tmp_path):
    write_graph(tmp_path / "ui", {"app.js": ["b.js"], "b.js": []})
    (tmp_path / "ui" / "index.html").write_text(
        '<!doctype html><html><head><script type="module" src="/app.js"></script>'
        '</head><body></body></html>')
    session = Session(tmp_path / "Talk.kuulas")
    app = server.create_app(session, FakeEngine(), language="en", ui_dir=tmp_path / "ui")
    with TestClient(app) as c:
        yield c
    session.close()


def test_root_serves_the_page_with_preloads_and_no_cache(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert '<link rel="modulepreload" href="/b.js" />' in r.text
    assert r.headers["cache-control"] == "no-cache"


def test_static_modules_say_no_cache_and_keep_their_etag(client):
    r = client.get("/b.js")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers["etag"]
    again = client.get("/b.js", headers={"If-None-Match": r.headers["etag"]})
    assert again.status_code == 304
