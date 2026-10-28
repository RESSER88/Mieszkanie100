#!/usr/bin/env python3
"""OLX sale listings for a city via the GraphQL search the OLX site itself uses.

One request at a time, a pause between pages, an honest user agent, and a stop at the
first refusal (no retry loop, no attempt to look like a browser). Listing pages are not
fetched: OLX answers them with 403. Results are kept in SQLite, so new offers can be
flagged and an OLX link can later be turned into a card. OLX map points are approximate.
This is an unofficial interface and may change or be closed at any time.

Usage on the Pi:  python3 rcn/olx.py szukaj --dzielnica "Ligota-Panewniki" --metraz-od 100
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rcn import portale  # noqa: E402
from rcn.oferta import USER_AGENT  # noqa: E402

GRAPHQL_URL = "https://www.olx.pl/apigateway/graphql"
PAGE_SIZE = 40
KATOWICE = (7691, 6)          # (city_id, region_id) on OLX
CATEGORY_SALE = "14"          # flats for sale; 15 = flats for rent
QUERY = ("query S($p:[SearchParameter!]=[]){clientCompatibleListings(searchParameters:$p){__typename"
         " ... on ListingSuccess{data{id url title location{city{name} district{name}} map{lat lon}"
         " params{key value{__typename ... on GenericParam{key label} ... on PriceParam{value currency}}}}"
         " metadata{total_elements}} ... on ListingError{error{code detail}}}}")


class OlxError(Exception):
    def __init__(self, message: str, partial: Optional[List[dict]] = None):
        super().__init__(message)
        self.partial = partial or []


class OlxClient:
    def __init__(self, url: str = GRAPHQL_URL, timeout: float = 30.0, sleep=time.sleep):
        self.url, self.timeout, self.sleep = url, timeout, sleep

    def fetch_page(self, city_id: int, region_id: int, offset: int, category_id: str = CATEGORY_SALE,
                   limit: int = PAGE_SIZE) -> Tuple[List[dict], int]:
        params = [("offset", offset), ("limit", limit), ("city_id", city_id), ("region_id", region_id),
                  ("category_id", category_id)]
        body = json.dumps({"operationName": "S", "query": QUERY,
                           "variables": {"p": [{"key": k, "value": str(v)} for k, v in params]}}).encode()
        request = urllib.request.Request(self.url, data=body, method="POST", headers={
            "User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json",
            "x-client": "DESKTOP"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise OlxError("OLX odmówił: HTTP %d" % exc.code)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise OlxError("błąd połączenia lub odpowiedzi: %s" % exc)
        result = (data.get("data") or {}).get("clientCompatibleListings") or {}
        if result.get("__typename") != "ListingSuccess":
            raise OlxError("OLX zwrócił błąd: %s" % result.get("error"))
        return result.get("data") or [], int((result.get("metadata") or {}).get("total_elements") or 0)

    def search_all(self, city_id: int, region_id: int, category_id: str = CATEGORY_SALE, pause: float = 3.0,
                   max_pages: int = 30) -> Tuple[List[dict], int]:
        items: List[dict] = []
        total, offset = 0, 0
        for page in range(max_pages):
            if page:
                self.sleep(pause)
            try:
                data, total = self.fetch_page(city_id, region_id, offset, category_id)
            except OlxError as exc:
                exc.partial = items
                raise
            items.extend(data)
            offset += len(data)
            if not data or offset >= total:
                break
        return items, total


def _params(raw: dict) -> Dict[str, Any]:
    out = {}
    for p in raw.get("params") or []:
        value = p.get("value") or {}
        out[p.get("key")] = value.get("value") if value.get("__typename") == "PriceParam" else value.get("label")
    return out


def parse_item(raw: dict) -> Dict[str, Any]:
    """One search result as an offer in the same shape as rcn.portale.parse_listing."""
    params = _params(raw)
    offer = portale._empty_offer(raw.get("url") or "https://www.olx.pl/")
    location = raw.get("location") or {}
    area = portale.to_number(params.get("m"))
    price = portale.to_number(params.get("price"))
    position = raw.get("map") or {}
    offer.update({
        "portal": "olx", "id": str(raw.get("id")), "tytul": raw.get("title"), "cena": price,
        "powierzchnia_m2": area,
        "cena_m2": round(price / area, 2) if price and area else portale.to_number(params.get("price_per_m")),
        "pokoje": portale._to_int(params.get("rooms")), "pietro": portale._to_int(params.get("floor_select")),
        "rynek": portale._market(params.get("market")), "zabudowa": params.get("builttype"),
        "miejscowosc": (location.get("city") or {}).get("name"),
        "dzielnica": (location.get("district") or {}).get("name"),
        "lat": portale.to_number(position.get("lat")), "lon": portale.to_number(position.get("lon")),
        "lokalizacja_przyblizona": True,
    })
    offer["brakuje"] = [f for f in portale.REQUIRED
                        if (f == "wspolrzedne" and (offer["lat"] is None or offer["lon"] is None))
                        or (f != "wspolrzedne" and offer.get(f) is None)]
    return offer


def matches(offer: Dict[str, Any], dzielnice: Optional[Sequence[str]] = None, area_min: Optional[float] = None,
            area_max: Optional[float] = None, price_max: Optional[float] = None,
            rynek: Optional[str] = None) -> bool:
    if dzielnice and (offer.get("dzielnica") or "").casefold() not in {d.casefold() for d in dzielnice}:
        return False
    area, price = offer.get("powierzchnia_m2"), offer.get("cena")
    if area_min is not None and (area is None or area < area_min):
        return False
    if area_max is not None and (area is None or area > area_max):
        return False
    if price_max is not None and (price is None or price > price_max):
        return False
    return rynek is None or offer.get("rynek") == rynek


def _url_key(url: str) -> str:
    return urllib.parse.urlsplit(url).path.rstrip("/")


class OfferStore:
    def __init__(self, path: str):
        self.con = sqlite3.connect(path)
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS oferty (portal TEXT, id TEXT, url TEXT, url_klucz TEXT, dane_json TEXT,"
            " pierwszy_raz TEXT, ostatnio TEXT, PRIMARY KEY (portal, id))")
        self.con.execute("CREATE INDEX IF NOT EXISTS oferty_url ON oferty (url_klucz)")
        self.con.commit()

    def upsert(self, offers: Iterable[Dict[str, Any]], day: str) -> List[Dict[str, Any]]:
        """Store offers; return the ones not seen before."""
        new = []
        with self.con:
            for o in offers:
                seen = self.con.execute("SELECT 1 FROM oferty WHERE portal=? AND id=?", (o["portal"], o["id"]))
                if seen.fetchone() is None:
                    new.append(o)
                    self.con.execute("INSERT INTO oferty VALUES (?,?,?,?,?,?,?)",
                                     (o["portal"], o["id"], o["url"], _url_key(o["url"] or ""),
                                      json.dumps(o, ensure_ascii=False), day, day))
                else:
                    self.con.execute("UPDATE oferty SET dane_json=?, ostatnio=? WHERE portal=? AND id=?",
                                     (json.dumps(o, ensure_ascii=False), day, o["portal"], o["id"]))
        return new

    def find_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        row = self.con.execute("SELECT dane_json FROM oferty WHERE url_klucz=? ORDER BY ostatnio DESC",
                               (_url_key(url),)).fetchone()
        return json.loads(row[0]) if row else None

    def close(self):
        self.con.close()


def _zl(value: Optional[float]) -> str:
    return "brak" if value is None else "{:,.0f}".format(value).replace(",", " ")


def format_offer_line(o: Dict[str, Any], is_new: bool, comparison: str) -> str:
    return "%s%s%s | %s | %s m² | %s zł | %s zł/m² | %s | %s | %s" % (
        "[NOWA] " if is_new else "", o.get("tytul"), " (%s)" % o["inwestycja"] if o.get("inwestycja") else "",
        o.get("dzielnica") or "dzielnica nieznana",
        ("%g" % o["powierzchnia_m2"]).replace(".", ",") if o.get("powierzchnia_m2") else "?",
        _zl(o.get("cena")), _zl(o.get("cena_m2")),
        {"wtorny": "wtórny", "pierwotny": "pierwotny"}.get(o.get("rynek") or "", "rynek ?"), comparison, o.get("url"))


def _comparison(offer, rcn_con, radius_m, months, today) -> str:
    from rcn import karta
    try:
        card = karta.build_card(offer, rcn_con, None, radius_m, months, today=today)
    except karta.CardError:
        return "brak współrzędnych, bez porównania"
    label = dict(karta.okolica.MARKETS)[card["rynek_porownania"]]
    summary = dict(card["porownanie"])[label]
    if card["polozenie"] is None:
        return "%s: brak danych w promieniu %g m" % (label.lower(), radius_m)
    return "%s (%s, mediana %s, próbka %d%s)" % (card["polozenie"], label.lower(), _zl(summary.median_m2), summary.n,
                                                ", za mała" if summary.status == "za_mala_proba" else "")


def main(argv=None, today: Optional[date] = None) -> int:
    p = argparse.ArgumentParser(description="Oferty sprzedaży mieszkań z OLX (wyszukiwanie GraphQL).")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("szukaj", help="pobierz oferty z miasta, odfiltruj i porównaj z RCN")
    s.add_argument("--url", default=GRAPHQL_URL)
    s.add_argument("--city-id", type=int, default=KATOWICE[0])
    s.add_argument("--region-id", type=int, default=KATOWICE[1])
    s.add_argument("--kategoria", default=CATEGORY_SALE)
    s.add_argument("--rcn-db", default="rcn_test.sqlite")
    s.add_argument("--oferty-db", default="oferty.sqlite")
    s.add_argument("--dzielnica", action="append", help="nazwa dzielnicy z OLX, można podać kilka razy")
    s.add_argument("--metraz-od", type=float)
    s.add_argument("--metraz-do", type=float)
    s.add_argument("--cena-do", type=float)
    s.add_argument("--rynek", choices=["wtorny", "pierwotny"])
    s.add_argument("--max-stron", type=int, default=30)
    s.add_argument("--pauza", type=float, default=3.0, help="przerwa między stronami [s]")
    s.add_argument("--promien", type=float, default=500.0)
    s.add_argument("--miesiace", type=int, default=24)
    args = p.parse_args(argv)

    today = today or date.today()
    client = OlxClient(args.url)
    exit_code, note = 0, ""
    try:
        raw, total = client.search_all(args.city_id, args.region_id, args.kategoria, args.pauza, args.max_stron)
    except OlxError as exc:
        raw, total, exit_code = exc.partial, None, 1
        note = "UWAGA: %s. Wynik niepełny, nie ponawiać w pętli." % exc
    offers = [parse_item(r) for r in raw]
    store = OfferStore(args.oferty_db)
    try:
        new_ids = {o["id"] for o in store.upsert(offers, today.isoformat())}
    finally:
        store.close()
    chosen = [o for o in offers if matches(o, args.dzielnica, args.metraz_od, args.metraz_do, args.cena_do,
                                            args.rynek)]
    print("OLX: pobrano %d z %s ofert, pasuje do filtrów: %d, nowych od ostatniego razu: %d" % (
        len(offers), total if total is not None else "?", len(chosen), len(new_ids & {o["id"] for o in chosen})))
    if note:
        print(note)
    rcn = sqlite3.connect(args.rcn_db)
    try:
        for o in sorted(chosen, key=lambda x: (x["id"] not in new_ids, x.get("cena_m2") or 0)):
            print(format_offer_line(o, o["id"] in new_ids, _comparison(o, rcn, args.promien, args.miesiace, today)))
    finally:
        rcn.close()
    print("Ceny ofertowe z OLX porównane z cenami transakcyjnymi RCN (promień %g m, ostatnie %d mies., podobny metraż)."
          " Lokalizacja z OLX jest przybliżona." % (args.promien, args.miesiace))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
