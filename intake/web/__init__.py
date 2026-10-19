from __future__ import annotations

import base64
import json
import uuid
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..export import to_csv, to_dict
from ..extract import ClaudeExtractor, ExtractionError, FixtureExtractor
from ..models import OrderResult
from ..pipeline import process
from ..sources import Document, load, load_bytes
from ..workspace import Workspace

HERE = Path(__file__).resolve().parent


def kind_of(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        return "PDF"
    if suffix == ".eml":
        return "Email"
    if suffix in {".xlsx", ".xlsm", ".csv"}:
        return "Spreadsheet"
    if suffix == ".txt":
        return "Chat" if "whatsapp" in name.lower() else "Text"
    return "Fax" if "fax" in name.lower() else "Photo"


def text_of(doc: Document) -> str:
    return "\n".join(p.data for p in doc.parts if p.kind == "text" and isinstance(p.data, str)).strip()


def create_app(samples: Path, fixtures: bool = False) -> FastAPI:
    app = FastAPI(title="order-intake", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals["kind_of"] = kind_of

    workspaces = {
        p.name: Workspace.load(p)
        for p in sorted(samples.iterdir())
        if (p / "workspace.json").exists()
    }
    inbox = {name: sorted((ws.path / "inbox").iterdir()) for name, ws in workspaces.items()}
    docs: dict[tuple[str, str], Document] = {}
    results: dict[str, tuple[OrderResult, Document]] = {}

    def sample(ws: str, file: str) -> Document:
        key = (ws, file)
        if key not in docs:
            path = workspaces[ws].path / "inbox" / file
            if not path.is_file():
                raise HTTPException(404)
            docs[key] = load(path)
        return docs[key]

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request, error: str | None = None):
        previews = {
            (ws, f.name): text_of(sample(ws, f.name))[:420]
            for ws, files in inbox.items() for f in files
        }
        return templates.TemplateResponse(request, "inbox.html", {
            "workspaces": workspaces, "inbox": inbox, "previews": previews,
            "error": error, "uploads": not fixtures,
        })

    @app.get("/thumb/{ws}/{file}")
    def thumb(ws: str, file: str):
        doc = sample(ws, file)
        if not doc.preview:
            raise HTTPException(404)
        return Response(doc.preview, media_type="image/png")

    def show(result: OrderResult, doc: Document) -> RedirectResponse:
        order_id = uuid.uuid4().hex[:10]
        results[order_id] = (result, doc)
        return RedirectResponse(f"/orders/{order_id}", status_code=303)

    @app.post("/process")
    def process_sample(ws: str = Form(...), file: str = Form(...)):
        workspace = workspaces[ws]
        doc = sample(ws, file)
        return show(process(doc, workspace, FixtureExtractor(workspace.path / "fixtures")), doc)

    @app.post("/upload")
    async def upload(ws: str = Form(...), file: UploadFile = File(...)):
        if fixtures:
            raise HTTPException(403, "Started with --fixtures: uploads are off.")
        doc = load_bytes(file.filename or "upload", await file.read())
        try:
            result = process(doc, workspaces[ws], ClaudeExtractor())
        except ExtractionError as e:
            return RedirectResponse(f"/?{urlencode({'error': str(e)})}", status_code=303)
        return show(result, doc)

    @app.get("/orders/{order_id}", response_class=HTMLResponse)
    def order(request: Request, order_id: str):
        if order_id not in results:
            raise HTTPException(404)
        result, doc = results[order_id]
        workspace = workspaces[result.workspace]
        # Names for every code a suggestion might switch a line to.
        names = {code: item.name for code, item in workspace.items.items()
                 if any(i.suggestion and i.suggestion.code == code for line in result.lines for i in line.issues)}
        preview = base64.b64encode(doc.preview).decode() if doc.preview else None
        return templates.TemplateResponse(request, "order.html", {
            "r": result,
            "order_id": order_id,
            "seller": workspace.seller,
            "preview": preview,
            "text": text_of(doc),
            # Escaped so a line of the order can never close the <script> tag.
            "data": json.dumps({"order": to_dict(result), "names": names},
                               ensure_ascii=False).replace("</", "<\\/"),
        })

    @app.get("/orders/{order_id}/export.csv")
    def order_csv(order_id: str):
        if order_id not in results:
            raise HTTPException(404)
        result, _ = results[order_id]
        name = Path(result.source).stem + ".csv"
        return Response(to_csv(result), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    return app
