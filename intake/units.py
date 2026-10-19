from __future__ import annotations

import math

from .workspace import Item

# How customers actually write units, in Italian and English.
_ALIASES = {
    "pc": "pz pz. pezzi pezzo pcs pc piece pieces n nr n. x",
    "m": "m mt mt. metri metro meters metres meter",
    "kg": "kg kilo chili",
    "l": "l lt litri litro liters litres",
    "box": "box boxes scatola scatole cf cf. conf conf. confezione confezioni carton cartons",
    "pack": "pack packs pk confezione",
    "set": "set sets kit kits coppia coppie treno treni",
    "coil": "coil coils matassa matasse rotolo rotoli bobina bobine roll rolls",
    "can": "can cans tanica taniche latta",
}
_CANONICAL = {alias: unit for unit, words in _ALIASES.items() for alias in words.split()}


def canonical(unit: str | None) -> str | None:
    if not unit:
        return None
    return _CANONICAL.get(unit.strip().lower(), unit.strip().lower())


def to_sale_units(qty: float, unit: str | None, item: Item) -> tuple[float | None, str | None]:
    """Convert an ordered quantity into the unit the item is sold in.

    Returns (quantity, problem). A problem means a person should look at it.
    """
    ordered = canonical(unit)
    sold_by = canonical(item.unit)
    content = canonical(item.content_unit)

    if ordered is None or ordered == sold_by:
        converted = qty
    elif content and ordered == content and item.content_qty:
        converted = qty / item.content_qty
    elif ordered == "pc":
        # People write "pezzi" for anything countable; trust the catalog unit.
        converted = qty
    else:
        return None, f"ordered in {unit}, sold per {item.unit}"

    if not math.isclose(converted, round(converted)):
        whole = math.ceil(converted)
        per = f"{item.content_qty:g} {item.content_unit}" if item.content_qty else item.unit
        return converted, f"{qty:g} {unit} is {converted:g} {item.unit}; sold in whole units of {per}, round up to {whole}?"
    return round(converted), None
