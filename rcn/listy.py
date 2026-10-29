#!/usr/bin/env python3
"""Result lists of Nieruchomosci-online and Morizon, read the way marcmos/flatscraper reads them.

A result page gives link, price and area. Offers that pass the area and price filters get one more
request each for their listing page, read by rcn/portale.py (position, rooms, market, mentions),
because the lists carry no coordinates. One page at a time, a pause between requests, an honest
user agent, a stop at the first refusal. Results go to the same store as OLX and Otodom
(oferty.sqlite), so the map's area search and similar offers see them.

The selectors come from flatscraper (Kraków, 2026-01) and are not yet checked on Katowice pages:
run scripts/portale_probe.sh first.

Usage on the Pi:
  python3 rcn/listy.py szukaj --portal nieruchomosci-online --url "STRONA_WYNIKÓW" --metraz-od 100
  python3 rcn/listy.py szukaj --portal morizon --url "STRONA_WYNIKÓW" --metraz-od 100
"""
import argparse
import os
import re
import sys
import time
import urllib.parse
from datetime import date
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Optional

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rcn import portale  # noqa: E402
from rcn.oferta import fetch  # noqa: E402
from rcn.olx import OfferStore  # noqa: E402

PORTALS = {"nieruchomosci-online": "p", "morizon": "page"}     # portal -> page number parameter
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: Dict[str, str], parent: Optional["Node"]):
        self.tag, self.attrs, self.children, self.parent = tag, attrs, [], parent

    def classes(self) -> List[str]:
        return (self.attrs.get("class") or "").split()

    def text(self) -> str:
        parts = []
        for c in self.children:
            parts.append(c if isinstance(c, str) else c.text())
        return " ".join(" ".join(parts).split())

    def find_all(self, match: Callable[["Node"], bool]) -> List["Node"]:
        out = []
        for c in self.children:
            if isinstance(c, Node):
                if match(c):
                    out.append(c)
                out.extend(c.find_all(match))
        return out

    def find(self, match: Callable[["Node"], bool]) -> Optional["Node"]:
        found = self.find_all(match)
        return found[0] if found else None


class _TreeBuilder(HTMLParser):
    """A small, forgiving DOM: enough for class and data-cy lookups (scripts and styles are skipped)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {}, None)
        self.cur = self.root
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
            return
        node = Node(tag, {k: v or "" for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in _VOID:
            self.cur = node

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
            return
        node = self.cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.cur = node.parent

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.cur.children.append(data)


def tree(html: str) -> Node:
    builder = _TreeBuilder()
    builder.feed(html)
    return builder.root


def has_class(name: str):
    return lambda n: name in n.classes()


def attr_is(key: str, value: str):
    return lambda n: n.attrs.get(key) == value


def _number(text: str) -> Optional[float]:
    match = re.search(r"\d[\d\s ]*(?:[.,]\d+)?", text or "")
    return portale.to_number(match.group(0)) if match else None


def _item(portal: str, url: str, title: Optional[str], price, area) -> Dict[str, Any]:
    offer = portale._empty_offer(url)
    offer.update({"portal": portal, "id": portale._portal_and_id(url)[1], "tytul": title, "cena": price,
                  "powierzchnia_m2": area,
                  "cena_m2": round(price / area, 2) if price and area else None})
    return offer


def parse_no_list(html: str, city_url: str = "https://katowice.nieruchomosci-online.pl") -> List[Dict[str, Any]]:
    """Tiles of a Nieruchomosci-online result page; investments (link ending with "?") and other cities left out."""
    root = tree(html)
    out = []
    for tile in root.find_all(has_class("tile")):
        link = tile.find(lambda n: n.tag == "a" and n.parent is not None and n.parent.tag == "h2"
                         and "name" in n.parent.classes())
        if link is None:
            continue
        url = link.attrs.get("href", "")
        if not url.startswith(city_url) or url.endswith("?"):
            continue
        box = tile.find(has_class("tertiary__box--primary"))
        spans = [s.text() for s in box.find_all(lambda n: n.tag == "span")] if box else []
        price = _number(spans[0]) if spans else None
        area = _number(spans[1]) if len(spans) > 1 else None
        out.append(_item("nieruchomosci-online", url, link.text(), price, area))
    return out


def _floor(text: str) -> Optional[int]:
    if re.search(r"\bparter\b", text):
        return 0
    match = re.search(r"piętro (\d+)", text)
    return int(match.group(1)) if match else None


def parse_morizon_list(html: str) -> List[Dict[str, Any]]:
    """Cards of a Morizon result page (data-cy="card")."""
    root = tree(html)
    out = []
    for card in root.find_all(attr_is("data-cy", "card")):
        link = card.find(attr_is("data-cy", "propertyUrl"))
        if link is None:
            continue
        url = urllib.parse.urljoin("https://www.morizon.pl", link.attrs.get("href", ""))
        price_node = card.find(attr_is("data-cy", "cardPropertyOfferPrice"))
        price = _number(price_node.text().split("zł")[0]) if price_node else None
        info = card.find(has_class("property-info"))
        info_text = info.text() if info else ""
        area_match = re.search(r"(\d+(?:[.,]\d+)?)\s*m²", info_text)
        rooms = re.search(r"([1-9])\s*pok", info_text)
        item = _item("morizon", url, None, price, portale.to_number(area_match.group(1)) if area_match else None)
        ids = re.findall(r"(\d{6,})", url)
        item["id"] = ids[-1] if ids else item["id"]
        item.update(pokoje=int(rooms.group(1)) if rooms else None, pietro=_floor(info_text))
        out.append(item)
    return out


PARSERS = {"nieruchomosci-online": parse_no_list, "morizon": parse_morizon_list}


def page_url(base: str, page: int, param: str) -> str:
    """Result page number `page`; page 1 is the address as given."""
    if page <= 1:
        return base
    parts = urllib.parse.urlsplit(base)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k != param]
    query.append((param, str(page)))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def _passes(o: Dict[str, Any], area_min, area_max, price_max) -> bool:
    area, price = o.get("powierzchnia_m2"), o.get("cena")
    if area_min is not None and (area is None or area < area_min):
        return False
    if area_max is not None and (area is None or area > area_max):
        return False
    return price_max is None or (price is not None and price <= price_max)


def search(portal: str, url: str, db_path: str, area_min: Optional[float] = None, area_max: Optional[float] = None,
           price_max: Optional[float] = None, max_pages: int = 5, max_details: int = 40, pause: float = 3.0,
           fetch_page=fetch, sleep=time.sleep, today: Optional[date] = None) -> Dict[str, Any]:
    """Read result pages, then the listing page of each matching offer; store everything read. Returns a report."""
    parse = PARSERS[portal]
    city = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(url))
    listed: List[Dict[str, Any]] = []
    note, requests = "", 0

    def get(address):
        nonlocal requests
        if requests:
            sleep(pause)
        requests += 1
        return fetch_page(address)

    seen = set()
    for page in range(1, max_pages + 1):
        status, html = get(page_url(url, page, PORTALS[portal]))
        if status != 200 or html is None:
            note = "%s odmówił: HTTP %d na stronie %d. Wynik niepełny, nie ponawiać w pętli." % (portal, status, page)
            break
        items = parse(html, city) if portal == "nieruchomosci-online" else parse(html)
        fresh = [i for i in items if (i["portal"], i["id"]) not in seen]
        if not fresh:
            break
        seen.update((i["portal"], i["id"]) for i in fresh)
        listed.extend(fresh)
    matching = [o for o in listed if _passes(o, area_min, area_max, price_max)]
    detailed = []
    for o in matching[:max_details]:
        status, html = get(o["url"])
        if status != 200 or html is None:
            note = note or "%s odmówił strony ogłoszenia: HTTP %d. Pozostałe bez szczegółów." % (portal, status)
            break
        full = portale.parse_listing(html, o["url"])
        for key, value in o.items():          # the listing page wins; the list fills what the page lacks
            if full.get(key) in (None, "", [], {}):
                full[key] = value
        full["portal"], full["id"] = portal, o["id"]
        detailed.append(full)
    detailed_ids = {o["id"] for o in detailed}
    to_store = detailed + [o for o in matching if o["id"] not in detailed_ids]
    store = OfferStore(db_path)
    try:
        new = store.upsert(to_store, (today or date.today()).isoformat())
    finally:
        store.close()
    return {"na_liscie": len(listed), "pasuje": len(matching), "ze_szczegolami": len(detailed), "nowe": len(new),
            "bez_polozenia": sum(1 for o in to_store if o.get("lat") is None), "uwaga": note}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Oferty z list wyników Nieruchomosci-online i Morizon.")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("szukaj")
    s.add_argument("--portal", choices=sorted(PORTALS), required=True)
    s.add_argument("--url", required=True, help="strona wyników z przeglądarki (np. mieszkania na sprzedaż, Katowice)")
    s.add_argument("--oferty-db", default="oferty.sqlite")
    s.add_argument("--metraz-od", type=float)
    s.add_argument("--metraz-do", type=float)
    s.add_argument("--cena-do", type=float)
    s.add_argument("--max-stron", type=int, default=5)
    s.add_argument("--max-szczegolow", type=int, default=40, help="ile stron ogłoszeń pobrać (po jednej na ofertę)")
    s.add_argument("--pauza", type=float, default=3.0)
    args = p.parse_args(argv)
    report = search(args.portal, args.url, args.oferty_db, args.metraz_od, args.metraz_do, args.cena_do,
                    args.max_stron, args.max_szczegolow, args.pauza)
    print("%s: na liście %d ofert, pasuje do filtrów %d, pobrano szczegóły %d, nowych %d, bez położenia %d" % (
        args.portal, report["na_liscie"], report["pasuje"], report["ze_szczegolami"], report["nowe"],
        report["bez_polozenia"]))
    if report["uwaga"]:
        print("UWAGA: " + report["uwaga"])
    if report["na_liscie"] == 0 and not report["uwaga"]:
        print("UWAGA: strona nie ma ofert w znanym układzie; sprawdź ją skryptem scripts/portale_probe.sh.")
    return 1 if report["uwaga"] else 0


if __name__ == "__main__":
    sys.exit(main())
