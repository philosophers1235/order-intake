from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import anthropic

from .models import ExtractedOrder
from .sources import Document

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM = """\
You read purchase orders received by {seller}, a wholesale distributor. They \
arrive as faxes, phone photos of handwritten notes, PDFs, spreadsheets, \
emails and chat messages, in Italian or English.

Extract the order exactly as the customer wrote it:
- The customer is the business placing the order, never {seller}.
- Do not translate, correct or complete item names or codes. Copy codes \
character by character, typos included.
- Do not guess quantities. If the customer wrote "the usual", "le solite" or \
left the quantity out, set quantity to null and say so in the note.
- Keep the quantity's unit separate from the description: "200 m cavo FS17" \
is quantity 200, unit "m", description "cavo FS17".
- Keep lines in the original order. Skip greetings, signatures and stamps.
- Mark a value with confidence "low" when the handwriting or print quality \
makes it uncertain, and explain in the note.\
"""


class ExtractionError(RuntimeError):
    pass


def _content(doc: Document) -> list[dict]:
    blocks: list[dict] = []
    for part in doc.parts:
        if part.kind == "image":
            data = base64.standard_b64encode(part.data).decode()
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": part.media_type, "data": data}})
        elif part.kind == "pdf":
            data = base64.standard_b64encode(part.data).decode()
            blocks.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}})
        else:
            blocks.append({"type": "text", "text": part.data})
    blocks.append({"type": "text", "text": f"File name: {doc.name}\nExtract the order."})
    return blocks


class ClaudeExtractor:
    mode = "claude"

    def __init__(self, model: str | None = None, client: anthropic.Anthropic | None = None):
        self.model = model or os.environ.get("INTAKE_MODEL", DEFAULT_MODEL)
        self.client = client or anthropic.Anthropic()

    def __call__(self, doc: Document, seller: str) -> ExtractedOrder:
        try:
            response = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM.format(seller=seller),
                messages=[{"role": "user", "content": _content(doc)}],
                output_format=ExtractedOrder,
                output_config={"effort": "medium"},
                # If the primary model declines, the API retries on a fallback
                # model inside the same call instead of failing the order.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as e:
            raise ExtractionError("No valid Anthropic credentials. Set ANTHROPIC_API_KEY or use --fixtures.") from e
        except anthropic.RateLimitError as e:
            raise ExtractionError("Rate limited by the API; try again in a minute.") from e
        except anthropic.APIStatusError as e:
            raise ExtractionError(f"API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise ExtractionError("Could not reach the Anthropic API.") from e

        if response.stop_reason == "refusal":
            category = response.stop_details.category if response.stop_details else None
            raise ExtractionError(f"The model declined this document ({category or 'no category'}).")
        if response.stop_reason == "max_tokens":
            raise ExtractionError("The order is too long for one pass; split it and try again.")
        if response.parsed_output is None:
            raise ExtractionError("The model did not return a structured order.")
        return response.parsed_output


class FixtureExtractor:
    """Replays saved extractions, so the pipeline runs without an API key.

    Fixtures live next to the inbox: samples/<workspace>/fixtures/<file>.json
    """

    mode = "fixtures"

    def __init__(self, folder: str | Path):
        self.folder = Path(folder)

    def __call__(self, doc: Document, seller: str) -> ExtractedOrder:
        path = self.folder / f"{doc.name}.json"
        if not path.exists():
            raise ExtractionError(f"No fixture for {doc.name}. Run with an API key to process new files.")
        return ExtractedOrder.model_validate(json.loads(path.read_text(encoding="utf-8")))
