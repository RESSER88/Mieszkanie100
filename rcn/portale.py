"""Turn a saved listing page into one normalised offer (price, area, rooms, address, coordinates).

Supported: Gratka (Nuxt `__NUXT_DATA__` devalue payload) and Nieruchomosci-online.pl
(JSON-LD). Other portals fall back to generic JSON-LD. Free text is only scanned for
mentions (garden, terrace, balcony, parking, build year); it is never stored, so contact
data in descriptions does not leak. Standard library only.
"""
import json
import math
import re
import urllib.parse
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional, Set

from rcn.oferta import _PageParser

REQUIRED = ("cena", "powierzchnia_m2", "wspolrzedne")
_SPECIAL_SKIP = {"Reactive", "ShallowReactive", "Ref", "ShallowRef"}
_SPECIAL_EMPTY = {"EmptyRef", "EmptyShallowRef", "undefined"}


def devalue_hydrate(arr: List[Any], start: int = 0) -> Any:
    """Rebuild the value at `start` from a devalue-flattened array (as used by Nuxt 3)."""
    memo: Dict[int, Any] = {}

    def ref(i):
        if not isinstance(i, int) or isinstance(i, bool):
            return i
        if i < 0:
            return None                 # undefined, hole, NaN, infinities
        if i in memo:
            return memo[i]
        v = arr[i]
        if isinstance(v, dict):
            out: Dict[str, Any] = {}
            memo[i] = out
            for key, child in v.items():
                out[key] = ref(child)
            return out
        if isinstance(v, list):
            if v and isinstance(v[0], str):
                tag = v[0]
                if tag in _SPECIAL_SKIP:
                    memo[i] = ref(v[1])
                elif tag in _SPECIAL_EMPTY:
                    memo[i] = None
                elif tag == "Date":
                    memo[i] = v[1]
                elif tag in ("Set", "BigInt"):
                    memo[i] = [ref(x) for x in v[1:]] if tag == "Set" else int(v[1])
                elif tag in ("Map", "null"):
                    memo[i] = {str(ref(v[k])): ref(v[k + 1]) for k in range(1, len(v) - 1, 2)}
                else:
                    memo[i] = None
                return memo[i]
            out_list: List[Any] = []
            memo[i] = out_list
            out_list.extend(ref(x) for x in v)
            return out_list
        memo[i] = v
        return v

    return ref(start)


def devalue_find_first(arr: List[Any], keys: Set[str]) -> Optional[dict]:
    """Hydrate the first object (lowest index) that has all `keys`: the page's main record."""
    for i, v in enumerate(arr):
        if isinstance(v, dict) and keys <= set(v):
            return devalue_hydrate(arr, i)
    return None


def to_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("amount", "value", "price"):
            if key in value:
                return to_number(value[key])
        return None
    text = re.sub(r"\s+", "", str(value)).replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def _to_int(value: Any) -> Optional[int]:
    if isinstance(value, str) and value.strip().lower() in ("parter", "ground floor"):
        return 0
    number = to_number(value)
    return int(number) if number is not None else None


def _find_key(data: Any, pattern: str) -> Any:
    """First value whose key matches `pattern` (case-insensitive), depth-first."""
    rx = re.compile(pattern, re.I)
    stack = [data]
    while stack:
        item = stack.pop(0)
        if isinstance(item, dict):
            for key, child in item.items():
                if rx.fullmatch(key) and child not in (None, "", [], {}):
                    return child
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return None


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def html_to_text(html: str) -> str:
    parser = _TextParser()
    parser.feed(html)
    return " ".join(parser.parts)


_AREA = r"[^.\d]{0,40}?(\d+(?:[.,]\d+)?)\s*(?:m²|m2|mkw|m\b)"
_MENTIONS = (("ogrod", r"ogr[oó]d(?!z)"), ("taras", r"taras"), ("balkon", r"balkon"), ("loggia", r"loggi"))
_PARKING = r"(miejsc\w*\s+postojow|gara[żz]|hal\w*\s+gara)"
_YEAR = r"(?:rok\s+budowy|wybudowan\w*|oddan\w*\s+do\s+u[żz]ytku|budynek\s+z)\D{0,40}?((?:19|20)\d{2})"


def features_from_text(text: str) -> Dict[str, Any]:
    """Mentions found in free text; an area in m² when the text gives one, else True."""
    found: Dict[str, Any] = {}
    for key, word in _MENTIONS:
        match = re.search(word + r"\w*" + _AREA, text, re.I)
        if match:
            found[key] = float(match.group(1).replace(",", "."))
        elif re.search(word, text, re.I):
            found[key] = True
    if re.search(_PARKING, text, re.I):
        found["miejsce_postojowe"] = True
    year = re.search(_YEAR, text, re.I)
    if year:
        found["rok"] = int(year.group(1))
    return found


def _market(value: Any) -> Optional[str]:
    text = str(value or "").lower()
    if "wtórn" in text or "wtorn" in text or "secondary" in text:
        return "wtorny"
    if "pierwotn" in text or "primary" in text or "developer" in text:
        return "pierwotny"
    return None


def _portal_and_id(url: str):
    parts = urllib.parse.urlsplit(url)
    host = parts.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    if host.endswith("nieruchomosci-online.pl"):
        portal = "nieruchomosci-online"
    elif host.endswith("gratka.pl"):
        portal = "gratka"
    elif host.endswith("otodom.pl"):
        portal = "otodom"
    elif host.endswith("morizon.pl"):
        portal = "morizon"
    else:
        portal = host
    numbers = re.findall(r"\d{5,}", parts.path)
    return portal, (numbers[-1] if numbers else None)


def _empty_offer(url: str) -> Dict[str, Any]:
    portal, oid = _portal_and_id(url)
    return {"portal": portal, "id": oid, "url": url, "tytul": None, "cena": None, "powierzchnia_m2": None,
            "cena_m2": None, "pokoje": None, "pietro": None, "rok_budowy": None, "rynek": None, "ulica": None,
            "miejscowosc": None, "dzielnica": None, "lat": None, "lon": None, "lokalizacja_przyblizona": False,
            "wzmianki": {}, "wzmianki_zrodlo": None, "inwestycja": None, "brakuje": []}


def _from_json_ld(offer: Dict[str, Any], blocks: Iterable[Any]) -> Optional[str]:
    candidates = [b for b in blocks if isinstance(b, dict) and ("floorSize" in b or "geo" in b or "offers" in b)]
    if not candidates:
        candidates = [b for b in blocks if isinstance(b, dict) and "price" in b]
    if not candidates:
        return None
    block = candidates[0]
    offers = block.get("offers")
    first = offers[0] if isinstance(offers, list) and offers else (offers if isinstance(offers, dict) else block)
    offer["cena"] = to_number(first.get("price"))
    spec = first.get("priceSpecification") if isinstance(first, dict) else None
    if isinstance(spec, dict) and spec.get("unitCode") in ("MTK", "M2", "m2"):
        offer["cena_m2"] = to_number(spec.get("price"))
    offer["powierzchnia_m2"] = to_number(block.get("floorSize"))
    offer["pokoje"] = _to_int(block.get("numberOfRooms"))
    offer["pietro"] = _to_int(block.get("floorLevel"))
    offer["rok_budowy"] = _to_int(block.get("yearBuilt"))
    address = block.get("address") if isinstance(block.get("address"), dict) else {}
    offer["ulica"] = address.get("streetAddress")
    offer["miejscowosc"] = address.get("addressLocality")
    geo = block.get("geo") if isinstance(block.get("geo"), dict) else {}
    offer["lat"], offer["lon"] = to_number(geo.get("latitude")), to_number(geo.get("longitude"))
    description = block.get("description")
    return description if isinstance(description, str) and description.strip() else None


def _places(value: Any):
    """(city, district) from "Katowice, Ligota" or ["śląskie", "Katowice", "Ligota"]."""
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
    elif isinstance(value, list):
        parts = [p.strip() for p in value if isinstance(p, str) and p.strip()]
    else:
        return None, None
    parts = [p for p in parts if not p.lower().endswith("skie") and "województwo" not in p.lower()]
    return (parts[0] if parts else None), (parts[1] if len(parts) > 1 else None)


def _from_gratka(offer: Dict[str, Any], blocks: Dict[str, Any]) -> Optional[str]:
    arr = blocks.get("json___NUXT_DATA__")
    if not isinstance(arr, list):
        return None
    # Gratka and Morizon share a platform; Morizon's record has no numberOfRooms key.
    listing = devalue_find_first(arr, {"area", "price", "numberOfRooms"}) or \
        devalue_find_first(arr, {"area", "price", "priceM2"})
    if not listing:
        return None
    offer["cena"] = to_number(listing.get("price"))
    offer["powierzchnia_m2"] = to_number(listing.get("area"))
    offer["cena_m2"] = to_number(listing.get("priceM2"))
    offer["pokoje"] = _to_int(listing.get("numberOfRooms"))
    offer["pietro"] = _to_int(listing.get("floor"))
    offer["rynek"] = _market(listing.get("marketType"))
    offer["tytul"] = listing.get("title") if isinstance(listing.get("title"), str) else None
    location = listing.get("location")
    offer["ulica"] = _find_key(location, r"street")
    offer["miejscowosc"], offer["dzielnica"] = _places(_find_key(location, r"location|city|locality"))
    center = _find_key(listing, r"center")       # the map centre, not the map bounds (northeast, southwest)
    where = center if isinstance(center, dict) else listing
    offer["lat"] = to_number(_find_key(where, r"lat(itude)?"))
    offer["lon"] = to_number(_find_key(where, r"lon(gitude)?|lng"))
    details = listing.get("buildingDetailedInformation")
    for item in details if isinstance(details, list) else []:
        if isinstance(item, dict) and "rok budowy" in str(item.get("label", "")).lower():
            offer["rok_budowy"] = _to_int(item.get("value"))
    if offer["rok_budowy"] is None:
        offer["rok_budowy"] = _to_int(_find_key(listing, r"(build|construction)(ing)?Year|yearBuilt"))
    description = listing.get("description")
    return description if isinstance(description, str) else None


_OTODOM_EXTRAS = {"balcony": "balkon", "garden": "ogrod", "terrace": "taras", "garage": "miejsce_postojowe",
                  "loggia": "loggia"}


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def otodom_floor(value: Any) -> Optional[int]:
    """Otodom floor codes: "ground_floor" -> 0, "floor_4" -> 4, "floor_higher_10" -> 10."""
    value = _first(value)
    if not value:
        return None
    if str(value) == "ground_floor":
        return 0
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def _from_otodom(offer: Dict[str, Any], blocks: Dict[str, Any]) -> Optional[str]:
    ad = (((blocks.get("next_data") or {}).get("props") or {}).get("pageProps") or {}).get("ad")
    if not isinstance(ad, dict):
        return None
    target = ad.get("target") or {}
    offer["id"] = str(ad["id"]) if ad.get("id") is not None else offer["id"]
    offer["tytul"] = html_to_text(ad["title"]) if isinstance(ad.get("title"), str) else None
    offer["cena"] = to_number(target.get("Price"))
    offer["cena_m2"] = to_number(target.get("Price_per_m"))
    offer["powierzchnia_m2"] = to_number(target.get("Area"))
    offer["pokoje"] = _to_int(_first(target.get("Rooms_num")))
    offer["pietro"] = otodom_floor(target.get("Floor_no"))
    offer["rok_budowy"] = _to_int(target.get("Build_year"))
    offer["rynek"] = _market(ad.get("market"))
    offer["zabudowa"] = _first(target.get("Building_type"))
    offer["inwestycja"] = ad.get("developmentTitle") or None
    location = ad.get("location") or {}
    address = location.get("address") or {}
    offer["ulica"] = (address.get("street") or {}).get("name")
    city = (address.get("city") or {}).get("name") or target.get("City")
    offer["miejscowosc"] = city.capitalize() if isinstance(city, str) and city.islower() else city
    for place in (location.get("reverseGeocoding") or {}).get("locations") or []:
        if place.get("locationLevel") == "district":
            offer["dzielnica"] = place.get("name")
    offer["lat"] = to_number(_find_key(location, r"latitude|lat"))
    offer["lon"] = to_number(_find_key(location, r"longitude|lon|lng"))
    extras = target.get("Extras_types") or []
    offer["_cechy"] = {_OTODOM_EXTRAS[e]: True for e in extras if e in _OTODOM_EXTRAS}
    description = ad.get("description")
    return html_to_text(description) if isinstance(description, str) else None


_NO_MAP = re.compile(r"var map[A-Za-z_-]*\s*=\s*(\{.*?\});", re.S)
_COORDS = re.compile(r'"coords"\s*:\s*"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)"')


def _coordinates_from_scripts(offer: Dict[str, Any], html: str) -> None:
    """Positions some portals keep only in page scripts (formats as read by marcmos/flatscraper):
    Nieruchomosci-online `var map… = {"latitude": …, "longitude": …}`, Morizon `"coords": "lat,lon"`."""
    for match in _NO_MAP.finditer(html):
        try:
            data = json.loads(match.group(1))
        except ValueError:
            continue
        lat, lon = to_number(data.get("latitude")), to_number(data.get("longitude"))
        if lat is not None and lon is not None:
            offer["lat"], offer["lon"] = lat, lon
            if str(data.get("isInaccurateLocation")) in ("1", "true", "True"):
                offer["lokalizacja_przyblizona"] = True
            return
    match = _COORDS.search(html)
    if match:
        offer["lat"], offer["lon"] = float(match.group(1)), float(match.group(2))


def parse_listing(html: str, url: str) -> Dict[str, Any]:
    """One normalised offer from a saved listing page; `brakuje` lists what could not be read."""
    offer = _empty_offer(url)
    parser = _PageParser()
    parser.feed(html)
    ld_blocks, other = [], {}
    for kind, text in parser.blocks:
        try:
            data = json.loads(text)
        except ValueError:
            continue
        if kind == "ld_json":
            ld_blocks.extend(data if isinstance(data, list) else [data])
        else:
            other[kind] = data
    meta = dict(parser.meta)
    description = None
    if offer["portal"] in ("gratka", "morizon"):
        description = _from_gratka(offer, other)
    elif offer["portal"] == "otodom":
        description = _from_otodom(offer, other)
    if offer["cena"] is None and offer["powierzchnia_m2"] is None:
        description = _from_json_ld(offer, ld_blocks)
    offer["tytul"] = offer["tytul"] or meta.get("og:title") or " ".join(parser.title.split()) or None
    if offer["cena_m2"] is None and offer["cena"] and offer["powierzchnia_m2"]:
        offer["cena_m2"] = round(offer["cena"] / offer["powierzchnia_m2"], 2)
    text = html_to_text(html)
    offer["lokalizacja_przyblizona"] = "lokalizacja przybliżona" in text.lower()
    if offer["lat"] is None or offer["lon"] is None:
        _coordinates_from_scripts(offer, html)
    # Mentions come from the listing's own description; the whole page also holds recommended listings.
    offer["wzmianki"] = features_from_text(description or text)
    offer["wzmianki_zrodlo"] = "opis" if description else "cała strona"
    extras = offer.pop("_cechy", None)
    if extras:   # structured features from the listing; an area found in the description wins
        offer["wzmianki"] = dict(extras, **offer["wzmianki"])
        offer["wzmianki_zrodlo"] = "opis i cechy ogłoszenia"
    if offer["rok_budowy"] is None and "rok" in offer["wzmianki"]:
        offer["rok_budowy"] = offer["wzmianki"]["rok"]
    offer["brakuje"] = [f for f in REQUIRED if (f == "wspolrzedne" and (offer["lat"] is None or offer["lon"] is None))
                        or (f != "wspolrzedne" and offer.get(f) is None)]
    return offer


def _distance_m(a: Dict[str, Any], b: Dict[str, Any]) -> Optional[float]:
    if None in (a.get("lat"), a.get("lon"), b.get("lat"), b.get("lon")):
        return None
    dy = (a["lat"] - b["lat"]) * 111_320.0
    dx = (a["lon"] - b["lon"]) * 111_320.0 * math.cos(math.radians(a["lat"]))
    return math.hypot(dy, dx)


def same_offer(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """The same flat listed twice: area within 0.5 m², price within 1%, and close if both have coordinates."""
    if None in (a.get("powierzchnia_m2"), b.get("powierzchnia_m2"), a.get("cena"), b.get("cena")):
        return False
    if abs(a["powierzchnia_m2"] - b["powierzchnia_m2"]) > 0.5:
        return False
    if abs(a["cena"] - b["cena"]) > 0.01 * max(a["cena"], b["cena"]):
        return False
    distance = _distance_m(a, b)
    return distance is None or distance < 500
