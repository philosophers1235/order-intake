"""Turn whatever the customer sent into parts the model can read.

Images and PDFs go to the model as they are (it reads scans and handwriting
better than OCR does). Spreadsheets and emails become text first.
"""
from __future__ import annotations

import email
import io
from dataclasses import dataclass, field
from email import policy
from pathlib import Path

import pymupdf
from openpyxl import load_workbook
from PIL import Image

IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
MAX_SIDE = 2000


@dataclass
class Part:
    kind: str  # "text", "image" or "pdf"
    data: bytes | str
    media_type: str | None = None


@dataclass
class Document:
    name: str
    parts: list[Part] = field(default_factory=list)
    preview: bytes | None = None  # PNG of the first page, for the review screen


def _image(data: bytes) -> tuple[bytes, bytes]:
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    jpeg, png = io.BytesIO(), io.BytesIO()
    img.save(jpeg, "JPEG", quality=88)
    img.save(png, "PNG")
    return jpeg.getvalue(), png.getvalue()


def _pdf_preview(data: bytes) -> bytes:
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        return pdf[0].get_pixmap(dpi=110).tobytes("png")


def _sheet_text(data: bytes) -> str:
    book = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    out = []
    for sheet in book.worksheets:
        out.append(f"# sheet: {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            cells = ["" if v is None else str(v) for v in row]
            if any(cells):
                out.append("\t".join(cells).rstrip())
    return "\n".join(out)


def _email(data: bytes) -> tuple[list[Part], bytes | None]:
    msg = email.message_from_bytes(data, policy=policy.default)
    header = "\n".join(f"{k}: {msg[k]}" for k in ("From", "To", "Date", "Subject") if msg[k])
    parts: list[Part] = []
    preview = None
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body else ""
    parts.append(Part("text", f"{header}\n\n{text}".strip()))
    for attachment in msg.iter_attachments():
        name = attachment.get_filename() or "attachment"
        inner = load_bytes(name, attachment.get_content())
        parts.append(Part("text", f"--- attachment: {name} ---"))
        parts.extend(inner.parts)
        preview = preview or inner.preview
    return parts, preview


def load_bytes(name: str, data: bytes) -> Document:
    suffix = Path(name).suffix.lower()
    doc = Document(name)
    if suffix in IMAGE_TYPES:
        jpeg, png = _image(data)
        doc.parts.append(Part("image", jpeg, "image/jpeg"))
        doc.preview = png
    elif suffix == ".pdf":
        doc.parts.append(Part("pdf", data, "application/pdf"))
        doc.preview = _pdf_preview(data)
    elif suffix in {".xlsx", ".xlsm"}:
        doc.parts.append(Part("text", _sheet_text(data)))
    elif suffix == ".eml":
        doc.parts, doc.preview = _email(data)
    else:
        doc.parts.append(Part("text", data.decode("utf-8", errors="replace")))
    return doc


def load(path: str | Path) -> Document:
    path = Path(path)
    return load_bytes(path.name, path.read_bytes())
