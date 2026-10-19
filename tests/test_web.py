from pathlib import Path

from fastapi.testclient import TestClient

from intake.web import create_app

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def client():
    return TestClient(create_app(SAMPLES, fixtures=True))


def test_inbox_lists_every_sample():
    page = client().get("/").text
    for folder in SAMPLES.iterdir():
        for file in (folder / "inbox").glob("*"):
            assert file.name in page


def test_processing_a_sample_opens_its_review_page():
    c = client()
    response = c.post("/process", data={"ws": "ricambi-lazio", "file": "fax-de-santis.jpg"},
                      follow_redirects=False)
    assert response.status_code == 303
    order = response.headers["location"]

    page = c.get(order).text
    assert "Officina Meccanica De Santis" in page
    assert '"CD-1560K"' in page  # name of the suggested replacement is sent to the page

    csv = c.get(f"{order}/export.csv").text.splitlines()
    assert csv[0].startswith("customer_id,")
    assert len(csv) == 4


def test_uploads_are_off_in_fixture_mode():
    response = client().post("/upload", data={"ws": "ricambi-lazio"},
                             files={"file": ("order.txt", b"2 filtri olio")})
    assert response.status_code == 403
