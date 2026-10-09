"""Pack-size parsing and unit-price normalisation.

Index prices are always *unit prices*: price per 1000 g, per 1000 ml, or per piece.
That makes pack-size changes (shrinkflation) show up as price increases, as they should.
"""
from __future__ import annotations
import re

_UNITS = {
    "kg": ("g", 1000), "kgs": ("g", 1000), "g": ("g", 1), "gm": ("g", 1), "gms": ("g", 1),
    "gram": ("g", 1), "grams": ("g", 1),
    "l": ("ml", 1000), "ltr": ("ml", 1000), "litre": ("ml", 1000), "liter": ("ml", 1000),
    "litres": ("ml", 1000), "liters": ("ml", 1000), "ml": ("ml", 1),
    "pc": ("pc", 1), "pcs": ("pc", 1), "piece": ("pc", 1), "pieces": ("pc", 1),
    "unit": ("pc", 1), "units": ("pc", 1), "dozen": ("pc", 12),
}
_NUM = r"(\d+(?:\.\d+)?)"
_MULTI = re.compile(rf"{_NUM}\s*[x×*]\s*{_NUM}\s*-?\s*([a-z]+)")
_SINGLE = re.compile(rf"{_NUM}\s*-?\s*([a-z]+)")          # '-?' : storefront pack labels such as '15-Ltr Tin', '1-Ltr Pouch', '15-Kg Tin'
_PACK_OF = re.compile(r"(?:pack|set|box) of (\d+)")


def parse_quantity(text: str):
    """Parse '6 x 100 g', '1.5 L', 'Atta 5kg', 'pack of 4' -> (qty_in_base_units, base_unit) or None."""
    t = (text or "").lower().replace(",", "")
    m = _MULTI.search(t)
    if m and m.group(3) in _UNITS:
        base, f = _UNITS[m.group(3)]
        return float(m.group(1)) * float(m.group(2)) * f, base
    for m in _SINGLE.finditer(t):
        u = m.group(2)
        if u in _UNITS and _UNITS[u][0] in ("g", "ml"):
            base, f = _UNITS[u]
            return float(m.group(1)) * f, base
    m = _PACK_OF.search(t)
    if m:
        return float(m.group(1)), "pc"
    for m in _SINGLE.finditer(t):
        u = m.group(2)
        if u in _UNITS:
            base, f = _UNITS[u]
            return float(m.group(1)) * f, base
    if re.search(r"\bdozen\b", t):
        return 12.0, "pc"
    return None


def unit_price(price: float | None, qty_base: float | None, base_unit: str | None):
    """Price per 1000 g / 1000 ml / 1 pc. If the pack size is unknown, assume 1 unit."""
    if price is None:
        return None
    if not qty_base or not base_unit:
        return float(price)
    scale = 1000.0 if base_unit in ("g", "ml") else 1.0
    return float(price) / float(qty_base) * scale
