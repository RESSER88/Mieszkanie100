#!/usr/bin/env python3
"""Otodom sale listings for Katowice from the public search result pages.

Search pages carry the results in __NEXT_DATA__ (props.pageProps.data.searchAds.items)
and the page count in props.pageProps.tracking.listing.page_count. One page at a time,
a pause between pages, an honest user agent, a stop at the first refusal. Items have no
coordinates, so the comparison with RCN uses the street's mean RCN position and says so;
`rcn/karta.py LINK` fetches the listing page, which does have coordinates. Developer
listings are expanded into their units (relatedAds). Seller and agency data are not read.

Usage on the Pi:  python3 rcn/otodom.py szukaj --dzielnica "Ligota-Panewniki" --metraz-od 100
"""
import argparse
import os
import sqlite3
import sys
import time
import urllib.parse
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rcn import okolica, portale  # noqa: E402
from rcn.oferta import _PageParser, fetch  # noqa: E402
from rcn.olx import OfferStore, _comparison, also_on, format_offer_line, matches, unique_by_id  # noqa: E402

SEARCH_URL = "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/slaskie/katowice/katowice/katowice"
QUERY = {"viewType": "listing", "by": "LATEST", "direction": "DESC", "limit": "72"}
ROOMS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9,
         "TEN": 10, "MORE": 10}
FLOORS = {"CELLAR": -1, "GROUND": 0, "FIRST": 1, "SECOND": 2, "THIRD": 3, "FOURTH": 4, "FIFTH": 5, "SIXTH": 6,
          "SEVENTH": 7, "EIGHTH": 8, "NINTH": 9, "TENTH": 10, "ABOVE_TENTH": 11}


class OtodomError(Exception):
    def __init__(self, message: str, partial: Optional[List[dict]] = None):
        super().__init__(message)
        self.partial = partial or []


def page_url(base: str, page: int, area_min: Optional[float] = None) -> str:
    """Search page URL; areaMin narrows results on Otodom's side (filters are applied here too)."""
    query = dict(QUERY, page=str(page))
    if area_min:
        query["areaMin"] = str(int(area_min))
    return base + "?" + urllib.parse.urlencode(query)


def parse_page(html: str) -> Tuple[List[dict], int]:
    import json
    parser = _PageParser()
    parser.feed(html)
    for kind, text in parser.blocks:
        if kind == "next_data":
            props = (json.loads(text).get("props") or {}).get("pageProps") or {}
            items = ((props.get("data") or {}).get("searchAds") or {}).get("items") or []
            count = ((props.get("tracking") or {}).get("listing") or {}).get("page_count") or 0
            return items, int(count)
    return [], 0


def search_all(base: str = SEARCH_URL, pause: float = 3.0, max_pages: int = 10, sleep=time.sleep,
               fetch_page=fetch, area_min: Optional[float] = None) -> Tuple[List[dict], int]:
    items: List[dict] = []
    pages, page = 0, 1
    while True:
        if page > 1:
            sleep(pause)
        status, html = fetch_page(page_url(base, page, area_min))
        if status != 200 or html is None:
            raise OtodomError("Otodom odmówił: HTTP %d na stronie %d" % (status, page), items)
        got, count = parse_page(html)
        pages = count or pages or 1
        items.extend(got)
        if not got or page >= pages or page >= max_pages:
            return items, pages
        page += 1


def _single(item: dict, development: Optional[str], primary: bool) -> Dict[str, Any]:
    url = "https://www.otodom.pl/pl/oferta/%s" % item.get("slug")
    offer = portale._empty_offer(url)
    location = item.get("location") or {}
    street = (location.get("address") or {}).get("street") or {}
    places = {p.get("locationLevel"): p.get("name")
              for p in (location.get("reverseGeocoding") or {}).get("locations") or []}
    price = None if item.get("hidePrice") else portale.to_number(item.get("totalPrice"))
    area = portale.to_number(item.get("areaInSquareMeters"))
    offer.update({
        "portal": "otodom", "id": str(item.get("id")), "tytul": item.get("title"), "cena": price,
        "powierzchnia_m2": area,
        "cena_m2": (portale.to_number(item.get("pricePerSquareMeter")) if price else None),
        "pokoje": ROOMS.get(str(item.get("roomsNumber"))), "pietro": FLOORS.get(str(item.get("floorNumber"))),
        "rynek": "pierwotny" if primary else None, "ulica": street.get("name"),
        "miejscowosc": places.get("city_or_village"), "dzielnica": places.get("district"),
        "inwestycja": development or item.get("developmentTitle") or None,
    })
    if offer["cena_m2"] is None and price and area:
        offer["cena_m2"] = round(price / area, 2)
    offer["brakuje"] = [f for f in ("cena", "powierzchnia_m2") if offer.get(f) is None]
    return offer


def parse_item(item: dict) -> List[Dict[str, Any]]:
    """One search item; a developer listing becomes one offer per unit in relatedAds."""
    related = item.get("relatedAds") or []
    if related:
        return [_single(r, item.get("developmentTitle"), True) for r in related]
    return [_single(item, item.get("developmentTitle"), bool(item.get("developmentId")))]


def main(argv=None, today: Optional[date] = None) -> int:
    p = argparse.ArgumentParser(description="Oferty sprzedaży mieszkań z Otodom (strony wyników).")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("szukaj", help="pobierz wyniki dla Katowic, odfiltruj i porównaj z RCN")
    s.add_argument("--url", default=SEARCH_URL)
    s.add_argument("--rcn-db", default="rcn_test.sqlite")
    s.add_argument("--oferty-db", default="oferty.sqlite")
    s.add_argument("--dzielnica", action="append")
    s.add_argument("--metraz-od", type=float)
    s.add_argument("--metraz-do", type=float)
    s.add_argument("--cena-do", type=float)
    s.add_argument("--rynek", choices=["wtorny", "pierwotny"])
    s.add_argument("--max-stron", type=int, default=10)
    s.add_argument("--pauza", type=float, default=3.0)
    s.add_argument("--promien", type=float, default=500.0)
    s.add_argument("--miesiace", type=int, default=24)
    args = p.parse_args(argv)

    today = today or date.today()
    exit_code, note = 0, ""
    try:
        raw, pages = search_all(args.url, args.pauza, args.max_stron, area_min=args.metraz_od)
    except OtodomError as exc:
        raw, pages, exit_code = exc.partial, None, 1
        note = "UWAGA: %s. Wynik niepełny, nie ponawiać w pętli." % exc
    offers = unique_by_id(o for item in raw for o in parse_item(item))
    store = OfferStore(args.oferty_db)
    try:
        new_ids = {o["id"] for o in store.upsert(offers, today.isoformat())}
        others = store.others("otodom")
    finally:
        store.close()
    chosen = [o for o in offers if matches(o, args.dzielnica, args.metraz_od, args.metraz_do, args.cena_do,
                                            args.rynek)]
    print("Otodom: pobrano %d ofert z %s stron, pasuje do filtrów: %d, nowych od ostatniego razu: %d" % (
        len(offers), pages if pages is not None else "?", len(chosen), len(new_ids & {o["id"] for o in chosen})))
    if pages and pages > args.max_stron:
        print("UWAGA: Otodom ma %d stron wyników, pobrano %d (--max-stron). Najstarsze oferty pominięte." % (
            pages, args.max_stron))
    if note:
        print(note)
    rcn = sqlite3.connect(args.rcn_db)
    try:
        for o in sorted(chosen, key=lambda x: (x["id"] not in new_ids, x.get("cena_m2") or 0)):
            center = okolica.find_center(rcn, o["ulica"], o.get("miejscowosc") or "Katowice") if o.get("ulica") else None
            if center is None:
                comparison = "brak ulicy w danych RCN, bez porównania (pełna karta: rcn/karta.py LINK)"
            else:
                o["y_pl1992"], o["x_pl1992"] = center[0], center[1]
                comparison = "%s; położenie: środek ulicy z %d rekordów RCN" % (
                    _comparison(o, rcn, args.promien, args.miesiace, today), center[2])
            print(format_offer_line(o, o["id"] in new_ids, comparison + also_on(o, others)))
    finally:
        rcn.close()
    print("Ceny ofertowe z Otodom porównane z cenami transakcyjnymi RCN (promień %g m, ostatnie %d mies., podobny"
          " metraż). Wyniki wyszukiwania nie mają współrzędnych, więc położenie to środek ulicy." % (
              args.promien, args.miesiace))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
