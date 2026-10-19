from types import SimpleNamespace

import pytest

from intake.extract import ClaudeExtractor, ExtractionError
from intake.models import ExtractedOrder
from intake.sources import Document, Part


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def extractor(response):
    messages = FakeMessages(response)
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return ClaudeExtractor(model="claude-opus-5-5", client=client), messages


DOC = Document("note.jpg", [Part("image", b"\xff\xd8fake", "image/jpeg"), Part("text", "hello")])


def test_sends_the_document_and_returns_the_parsed_order():
    order = ExtractedOrder(customer_name="Elettrica Romana", lines=[])
    extract, messages = extractor(SimpleNamespace(stop_reason="end_turn", parsed_output=order, stop_details=None))
    assert extract(DOC, "Elettroforniture Roma srl") is order

    call = messages.calls[0]
    content = call["messages"][0]["content"]
    assert [block["type"] for block in content] == ["image", "text", "text"]
    assert "Elettroforniture Roma srl" in call["system"]
    assert call["output_format"] is ExtractedOrder
    assert call["output_config"] == {"effort": "medium"}


def test_refusal_is_an_error_not_an_empty_order():
    details = SimpleNamespace(category="cyber")
    extract, _ = extractor(SimpleNamespace(stop_reason="refusal", parsed_output=None, stop_details=details))
    with pytest.raises(ExtractionError, match="declined"):
        extract(DOC, "Seller")


def test_truncated_output_is_an_error():
    extract, _ = extractor(SimpleNamespace(stop_reason="max_tokens", parsed_output=None, stop_details=None))
    with pytest.raises(ExtractionError, match="too long"):
        extract(DOC, "Seller")
