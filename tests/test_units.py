from intake.units import canonical, to_sale_units
from intake.workspace import Item


def item(unit="pc", content_qty=None, content_unit=None):
    return Item("X", "x", (), unit, content_qty, content_unit, None, None, "active", None)


def test_canonical_units():
    assert canonical("pz") == canonical("pezzi") == "pc"
    assert canonical("matasse") == canonical("rolls") == "coil"
    assert canonical(None) is None


def test_metres_to_coils():
    cable = item("coil", 100, "m")
    assert to_sale_units(200, "m", cable) == (2, None)
    assert to_sale_units(1, "rotolo", cable) == (1, None)


def test_partial_coil_needs_a_person():
    qty, problem = to_sale_units(150, "m", item("coil", 100, "m"))
    assert qty == 1.5
    assert "round up to 2" in problem


def test_pieces_into_boxes():
    assert to_sale_units(100, "pz", item("box", 50, "pc")) == (2, None)


def test_incompatible_unit():
    qty, problem = to_sale_units(3, "kg", item("set"))
    assert qty is None and "sold per set" in problem


def test_generic_pieces_count_as_sale_unit():
    assert to_sale_units(4, "pz", item("set")) == (4, None)
