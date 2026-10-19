from pathlib import Path

from intake.sources import load, load_bytes

INBOX = Path(__file__).resolve().parent.parent / "samples" / "ricambi-lazio" / "inbox"


def test_email_keeps_headers_and_body():
    doc = load(INBOX / "email-atlas-fleet.eml")
    text = doc.parts[0].data
    assert "From: Daniel Borg <ops@atlasfleet.example>" in text
    assert "60 iridium spark plugs" in text


def test_spreadsheet_becomes_tab_separated_text():
    doc = load(INBOX / "ordine-prati.xlsx")
    text = doc.parts[0].data
    assert "FO-3l6\tFiltro olio\t5" in text


def test_images_are_sent_as_jpeg_with_a_png_preview():
    doc = load(INBOX / "fax-de-santis.jpg")
    assert doc.parts[0].kind == "image" and doc.parts[0].media_type == "image/jpeg"
    assert doc.preview.startswith(b"\x89PNG")


def test_plain_text_fallback():
    doc = load_bytes("chat.txt", "ciao, 10 interruttori".encode())
    assert doc.parts[0].data == "ciao, 10 interruttori"
