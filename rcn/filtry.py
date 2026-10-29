#!/usr/bin/env python3
"""Filters for searching saved offers around a point (the map's "Szukaj ofert w okolicy").

Only fields the saved search results really carry are filterable: price, area, price per m²,
rooms, floor, market, building type (OLX), portal, investment name and the days an offer was
first and last seen. A filter that is set rejects an offer whose value is unknown (it cannot be
shown to match); an unset filter never rejects. Distances to nuisances are applied separately
in rcn/mapa.py, because they need the OSM database. Standard library only.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Set

MARKETS = ("pierwotny", "wtorny")
DEVELOPERS = ("grupuj", "ukryj", "tylko")
SORTS = ("odleglosc", "cena_m2", "cena", "metraz", "najnowsze")
RANGES = ("cena", "cena_m2", "metraz", "pokoje", "pietro")
NUISANCES = {          # filter key -> OSM categories that must be farther than the given distance
    "z_dala_linie": ("linia_najwyzsza", "linia_wn"),
    "z_dala_kolej": ("kolej",),
    "z_dala_droga": ("droga_glowna",),
    "z_dala_przemysl": ("przemysl", "skladowisko", "oczyszczalnia", "kamieniolom"),
}


class FilterError(ValueError):
    """A filter value that cannot be read; the message is shown on the page."""


@dataclass
class Filters:
    cena_od: Optional[float] = None
    cena_do: Optional[float] = None
    cena_m2_od: Optional[float] = None
    cena_m2_do: Optional[float] = None
    metraz_od: Optional[float] = None
    metraz_do: Optional[float] = None
    pokoje_od: Optional[float] = None
    pokoje_do: Optional[float] = None
    pietro_od: Optional[float] = None
    pietro_do: Optional[float] = None
    bez_parteru: bool = False
    rynek: Optional[str] = None
    zabudowa: Set[str] = field(default_factory=set)
    portale: Set[str] = field(default_factory=set)
    deweloperzy: str = "grupuj"
    nowe_dni: Optional[int] = None
    tylko_aktualne: bool = False
    sortuj: str = "odleglosc"
    z_dala: Dict[str, float] = field(default_factory=dict)


def _number(params: Dict[str, str], key: str) -> Optional[float]:
    text = "".join((params.get(key) or "").split()).replace(",", ".")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        raise FilterError("„%s” nie jest liczbą: %s" % (key, params[key]))
    if value < 0:
        raise FilterError("„%s” nie może być ujemne" % key)
    return value


def _choice(params: Dict[str, str], key: str, allowed, default=None) -> Optional[str]:
    value = (params.get(key) or "").strip() or default
    if value is not None and value not in allowed:
        raise FilterError("„%s”: dozwolone %s" % (key, ", ".join(allowed)))
    return value


def _set(params: Dict[str, str], key: str) -> Set[str]:
    return {p.strip().casefold() for p in (params.get(key) or "").split(",") if p.strip()}


def parse(params: Dict[str, str]) -> Filters:
    f = Filters()
    for name in RANGES:
        low, high = _number(params, name + "_od"), _number(params, name + "_do")
        if low is not None and high is not None and low > high:
            raise FilterError("„%s”: wartość „od” większa niż „do”" % name)
        setattr(f, name + "_od", low)
        setattr(f, name + "_do", high)
    f.bez_parteru = params.get("bez_parteru") in ("1", "tak", "on")
    f.rynek = _choice(params, "rynek", MARKETS)
    f.zabudowa, f.portale = _set(params, "zabudowa"), _set(params, "portale")
    f.deweloperzy = _choice(params, "deweloperzy", DEVELOPERS, "grupuj")
    days = _number(params, "nowe_dni")
    f.nowe_dni = int(days) if days else None
    f.tylko_aktualne = params.get("tylko_aktualne") in ("1", "tak", "on")
    f.sortuj = _choice(params, "sortuj", SORTS, "odleglosc")
    for key in NUISANCES:
        distance = _number(params, key)
        if distance:
            f.z_dala[key] = distance
    return f


def _in_range(value, low, high) -> bool:
    if low is None and high is None:
        return True
    if value is None:
        return False
    return (low is None or value >= low) and (high is None or value <= high)


def is_developer(offer: Dict[str, Any]) -> bool:
    return bool(offer.get("inwestycja")) or offer.get("rynek") == "pierwotny"


def keep(offer: Dict[str, Any], f: Filters, latest: Dict[str, str], today: date) -> bool:
    """True when the offer passes every set filter; `latest` is the last search day per portal."""
    ranges = (("cena", "cena"), ("cena_m2", "cena_m2"), ("metraz", "powierzchnia_m2"), ("pokoje", "pokoje"),
              ("pietro", "pietro"))
    for name, fieldname in ranges:
        if not _in_range(offer.get(fieldname), getattr(f, name + "_od"), getattr(f, name + "_do")):
            return False
    if f.bez_parteru and offer.get("pietro") in (None, 0, -1):
        return False
    if f.rynek and offer.get("rynek") != f.rynek:
        return False
    if f.zabudowa and (offer.get("zabudowa") or "").casefold() not in f.zabudowa:
        return False
    if f.portale and not ({offer.get("portal")} | set(offer.get("takze_na") or [])) & f.portale:
        return False
    if f.deweloperzy == "ukryj" and is_developer(offer):
        return False
    if f.deweloperzy == "tylko" and not is_developer(offer):
        return False
    if f.nowe_dni and (offer.get("pierwszy_raz") or "") < (today - timedelta(days=f.nowe_dni)).isoformat():
        return False
    if f.tylko_aktualne and offer.get("ostatnio") != latest.get(offer.get("portal")):
        return False
    return True


_SORT_KEYS = {"odleglosc": ("odleglosc_m", False), "cena_m2": ("cena_m2", False), "cena": ("cena", False),
              "metraz": ("powierzchnia_m2", True), "najnowsze": ("pierwszy_raz", True)}


def sort(offers: Iterable[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    """Sorted copy; offers without the value go last, ties keep the distance order."""
    fieldname, descending = _SORT_KEYS[key]
    offers = list(offers)
    known = [x for x in offers if x.get(fieldname) is not None]
    known.sort(key=lambda x: x[fieldname], reverse=descending)
    return known + [x for x in offers if x.get(fieldname) is None]
