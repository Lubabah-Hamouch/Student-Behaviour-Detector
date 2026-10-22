"""Page and static-file tests. Run from the project root:  python -m pytest app/tests"""
import re

from app.server import config


def test_index_serves_the_app_shell(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<title>Focal</title>" in r.text
    assert 'type="module" src="/static/js/main.js"' in r.text
    assert r.headers["cache-control"] == "no-cache"


def test_every_asset_referenced_by_index_exists(client):
    html = client.get("/").text
    for url in set(re.findall(r'(?:href|src)="(/static/[^"]+)"', html)):
        assert client.get(url).status_code == 200, url


def test_static_js_modules_import_only_files_that_exist(client):
    for module in (config.WEB_DIR / "js").rglob("*.js"):
        for target in re.findall(r'from "(\.[^"]+)"', module.read_text(encoding="utf-8")):
            assert (module.parent / target).resolve().exists(), f"{module.name} imports missing {target}"


def test_every_element_id_the_scripts_look_up_exists_in_the_page():
    """A mistyped id only fails in the browser, so check them here: each $("#id") in main.js and modelinfo.js."""
    page = (config.WEB_DIR / "index.html").read_text(encoding="utf-8")
    page_ids = set(re.findall(r'\bid="([^"]+)"', page))
    for script in ("main.js", "modelinfo.js", "panel.js"):
        source = (config.WEB_DIR / "js" / script).read_text(encoding="utf-8")
        wanted = set(re.findall(r'(?:\$|querySelector)\(["\']#([\w-]+)["\']\)', source))
        assert wanted, f"no ids found in {script}"
        assert wanted <= page_ids, f"{script} looks up ids missing from index.html: {sorted(wanted - page_ids)}"


def test_video_player_markup_is_present():
    page = (config.WEB_DIR / "index.html").read_text(encoding="utf-8")
    for needle in ('<video id="video"', 'id="video-overlay"', 'id="timeline-track"', 'role="slider"', 'id="cancel-btn"'):
        assert needle in page, needle


def test_fonts_are_served_as_woff2(client):
    r = client.get("/static/fonts/ibm-plex-sans-latin-400-normal.woff2")
    assert r.status_code == 200 and r.headers["content-type"] == "font/woff2"


def test_limitations_page_renders_the_document(client):
    r = client.get("/limitations")
    assert r.status_code == 200
    assert "Known limitations and evaluation notes" in r.text
    assert '<nav class="toc"' in r.text and 'href="#summary"' in r.text
    assert "{{" not in r.text  # every template placeholder was filled
    assert r.text.count("<table>") == r.text.count('<div class="table-wrap"><table>') > 0
    assert 'href="/limitations/files/eye_state_review.csv"' in r.text
    assert "full_run_v1" in r.text


def test_limitations_csv_download(client):
    r = client.get("/limitations/files/eye_state_review.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].startswith("crop_id,split,source_video")
    assert "attachment" in r.headers["content-disposition"]


def test_limitations_files_are_an_allow_list(client):
    assert client.get("/limitations/files/requirements.txt").status_code == 404
    assert client.get("/limitations/files/..%2F..%2Frequirements.txt").status_code == 404


def test_limitations_404_when_the_document_is_missing(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "LIMITATIONS_PATH", tmp_path / "missing.md")
    assert client.get("/limitations").status_code == 404


def test_source_link_appears_only_when_configured(client, monkeypatch):
    assert client.get("/api/model").json()["source_url"] is None
    assert ">Source</a>" not in client.get("/limitations").text
    monkeypatch.setattr(config, "SOURCE_URL", "https://example.com/focal")
    assert client.get("/api/model").json()["source_url"] == "https://example.com/focal"
    assert 'href="https://example.com/focal">Source</a>' in client.get("/limitations").text
