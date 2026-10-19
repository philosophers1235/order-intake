from pathlib import Path

import pytest

from intake.matching import Matcher, normalize, numbers
from intake.models import ExtractedLine
from intake.workspace import Workspace

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


@pytest.fixture(scope="module")
def parts():
    return Matcher(Workspace.load(SAMPLES / "ricambi-lazio"))


@pytest.fixture(scope="module")
def electrical():
    return Matcher(Workspace.load(SAMPLES / "elettroforniture-roma"))


def line(description, code=None):
    return ExtractedLine(raw=description, description=description, code=code)


def test_normalize_handles_decimal_commas_and_plurals():
    assert normalize("Cavo FS17 2,5 mm²") == "cavo fs17 2.5 mm"
    assert normalize("interruttori bipolari") == normalize("interruttore bipolare")
    assert normalize("5W-30") == "5w30"


def test_numbers_ignore_formatting():
    assert numbers("cavo 2,5") == numbers("cavo 2.5")


@pytest.mark.parametrize("code", ["FO-316", "fo316", "FO 316"])
def test_code_matches_regardless_of_punctuation(parts, code):
    m = parts.match(line("anything", code))
    assert m.item.code == "FO-316" and m.via == "code"


def test_code_with_typo_is_flagged_not_trusted(parts):
    m = parts.match(line("Filtro olio", "FO-3l6"))
    assert m.item.code == "FO-316"
    assert m.via == "code with a typo"
    assert not m.sure


def test_english_description_matches_italian_catalog(parts):
    m = parts.match(line("front brake pads for the Ducato vans"))
    assert m.item.code == "PF-85017" and m.sure


def test_numbers_must_agree(electrical):
    assert electrical.match(line("cavo FS17 2,5 blu")).item.code == "CV-FS17-25-BL"
    assert electrical.match(line("cavo FS17 1,5 blu")).item.code == "CV-FS17-15-BL"


def test_colour_decides_between_cables(electrical):
    assert electrical.match(line("nero 2,5")).item.code == "CV-FS17-25-NE"


def test_vague_description_is_ambiguous(parts):
    m = parts.match(line("filtro"))
    assert m.ambiguous and not m.sure


def test_unknown_item(parts):
    assert parts.match(line("Liquido freni DOT 4")).item is None
