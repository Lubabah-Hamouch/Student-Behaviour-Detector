"""HTML pages: the single-page app shell and the limitations page."""
import html

import markdown
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from .. import config

router = APIRouter()
NO_CACHE = {"Cache-Control": "no-cache"}  # always revalidate, so edits show up on reload
DOWNLOAD_PREFIX = "/limitations/files/"


@router.get("/", include_in_schema=False)
def index():
    return FileResponse(config.WEB_DIR / "index.html", headers=NO_CACHE)


def _toc(tokens: list[dict]) -> str:
    """'On this page' list: the level-2 headings of the document."""
    items = []
    for top in tokens:  # the first level-1 heading is the page title; its children are the sections
        for section in (top["children"] if top["level"] == 1 else [top]):
            items.append(f'<li><a href="#{section["id"]}">{html.escape(section["name"])}</a></li>')
    return f"<ul>{''.join(items)}</ul>"


def render_limitations(text: str) -> str:
    """docs/LIMITATIONS.md -> the styled limitations page."""
    md = markdown.Markdown(extensions=["tables", "sane_lists", "toc"])
    content = md.convert(text)
    content = content.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    for name in config.DOCS_FILES:  # relative links to files that ship with the docs
        content = content.replace(f'href="{name}"', f'href="{DOWNLOAD_PREFIX}{name}"')

    source = f'<a href="{html.escape(config.SOURCE_URL)}">Source</a>' if config.SOURCE_URL else ""
    template = (config.WEB_DIR / "limitations.html").read_text(encoding="utf-8")
    return (template.replace("{{source_link}}", source)
                    .replace("{{toc}}", _toc(md.toc_tokens))
                    .replace("{{content}}", content))


@router.get("/limitations", response_class=HTMLResponse, include_in_schema=False)
def limitations():
    try:
        text = config.LIMITATIONS_PATH.read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(status_code=404, detail="The limitations document is not available.")
    return HTMLResponse(render_limitations(text), headers=NO_CACHE)


@router.get(DOWNLOAD_PREFIX + "{name}", include_in_schema=False)
def limitations_file(name: str):
    path = config.DOCS_FILES.get(name)  # only files listed in the config can be fetched
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail="Unknown file.")
    return FileResponse(path, media_type="text/csv", filename=name)
