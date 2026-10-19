"""End to end on the samples, with the saved extractions instead of the API."""
from pathlib import Path

import pytest

from intake.export import to_csv
from intake.extract import FixtureExtractor
from intake.pipeline import process
from intake.sources import load
from intake.workspace import Workspace

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def run(workspace: str, file: str):
    ws = Workspace.load(SAMPLES / workspace)
    return process(load(SAMPLES / workspace / "inbox" / file), ws, FixtureExtractor(ws.path / "fixtures"))


def kinds(result):
    return {line.number: [i.kind for i in line.issues] for line in result.lines}


def test_fax_suggests_the_kit_this_customer_already_bought():
    result = run("ricambi-lazio", "fax-de-santis.jpg")
    assert result.customer_id == "C001"  # found by fax number
    belt = result.lines[2]
    assert [i.kind for i in belt.issues] == ["discontinued"]
    assert belt.issues[0].suggestion.code == "CD-1560K"
    assert "12 Sep 2026" in belt.issues[0].suggestion.reason
    assert [line.status for line in result.lines[:2]] == ["ok", "ok"]


def test_handwritten_note_resolves_the_usual_quantity():
    result = run("elettroforniture-roma", "appunto-elettrica-romana.jpg")
    assert result.customer_id == "C101"
    assert result.lines[2].quantity == 2 and result.lines[2].unit == "coil"  # 200 m
    boxes = result.lines[3]
    assert boxes.issues[0].kind == "missing_quantity"
    assert boxes.issues[0].suggestion.quantity == 40


def test_old_price_on_a_scanned_pdf():
    result = run("forniture-servizi", "ordine-hotel-belvedere.pdf")
    assert kinds(result) == {1: [], 2: ["price"], 3: []}
    assert "before the last list update" in result.lines[1].issues[0].message


def test_email_flags_quantity_and_unknown_item():
    result = run("ricambi-lazio", "email-atlas-fleet.eml")
    assert result.customer_id == "C003"  # found by email address
    assert kinds(result) == {1: [], 2: [], 3: [], 4: ["unusual_quantity"], 5: ["unknown_item"]}


def test_spreadsheet_with_a_typo_in_a_code():
    result = run("ricambi-lazio", "ordine-prati.xlsx")
    assert kinds(result) == {1: [], 2: [], 3: ["code_typo"], 4: ["unknown_item"]}


def test_clean_whatsapp_order_needs_no_review():
    result = run("elettroforniture-roma", "whatsapp-elettrica-romana.txt")
    assert result.needs_review == 0


@pytest.mark.parametrize("workspace,file", [
    ("ricambi-lazio", "fax-de-santis.jpg"),
    ("forniture-servizi", "ordine-hotel-belvedere.pdf"),
])
def test_csv_export_has_one_row_per_line(workspace, file):
    result = run(workspace, file)
    rows = to_csv(result).strip().splitlines()
    assert len(rows) == len(result.lines) + 1
