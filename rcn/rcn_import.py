#!/usr/bin/env python3
"""Resumable importer of RCN (Rejestr Cen Nieruchomosci) records from the WFS.

Pages are keyed on gid (TERYT = X AND gid > last_gid, sorted by gid), so the
download does not depend on startIndex. The row batch and the checkpoint are
saved in one SQLite transaction. The report never claims completeness unless
a reference count is given with --expect-count.

Standard library only (Python 3.8+). Design: docs/superpowers/specs/.
"""
import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

DEFAULT_URL = "https://mapy.geoportal.gov.pl/wss/service/rcn"

# obj_id names for budynki/dzialki are not confirmed against a real record yet.
LAYERS = {
    "lokale": dict(price="LOK_CENA_BRUTTO", area="LOK_POW_UZYT", addr="LOK_ADRES",
                   obj_id="LOK_ID_LOKALU", kind="LOK_FUNKCJA", rooms="LOK_LICZBA_IZB", prefix="LOK_"),
    "budynki": dict(price="BUD_CENA_BRUTTO", area="BUD_POW_UZYT", addr="BUD_ADRES",
                    obj_id="BUD_ID_BUDYNKU", kind="BUD_RODZAJ", rooms=None, prefix="BUD_"),
    "dzialki": dict(price="DZI_CENA_BRUTTO", area="DZI_POW_EWID", addr="DZI_ADRES",
                    obj_id="DZI_ID_DZIALKI", kind="DZI_SPOSOB_UZYT", rooms=None, prefix="DZI_"),
}

NS = {
    "wfs": "http://www.opengis.net/wfs/2.0",
    "gml": "http://www.opengis.net/gml/3.2",
    "ms": "http://mapserver.gis.umn.edu/mapserver",
}


class RcnError(Exception):
    """Importer-level problem (server ignores a filter, bad arguments)."""


class WfsError(RcnError):
    """Transport or MapServer error that may be worth retrying."""


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _num(text):
    if text is None:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _parse_address(text):
    out = {}
    for part in (text or "").split(";"):
        if ":" in part:
            key, value = part.split(":", 1)
            out[key.strip()] = value.strip() or None
    return out.get("MSC"), out.get("UL"), out.get("NR_PORZ")


def _price_per_m2(tran, nier, obj, area):
    """Only when the three prices agree (single-object deal) and values are valid."""
    if None in (tran, nier, obj, area):
        return None
    if tran <= 0 or nier <= 0 or obj <= 0 or area <= 0:
        return None
    if abs(tran - nier) > 0.005 or abs(tran - obj) > 0.005:
        return None
    return round(obj / area, 4)


def parse_feature_collection(xml_bytes, layer):
    """Return (records, number_returned). Raises WfsError on a MapServer exception."""
    cfg = LAYERS[layer]
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise WfsError("odpowiedź nie jest poprawnym XML: %s" % exc)
    if _local(root.tag) == "ExceptionReport":
        text = " ".join(t.strip() for t in root.itertext() if t.strip())
        raise WfsError("ExceptionReport: %s" % text)
    records = []
    for member in root.findall("wfs:member", NS):
        feature = next(iter(member), None)
        if feature is None:
            continue
        raw, north, east = {}, None, None
        for child in feature:
            name = _local(child.tag)
            if name == "GEOMETRIA":
                pos = child.find(".//gml:pos", NS)
                if pos is not None and pos.text:
                    parts = pos.text.split()
                    if len(parts) >= 2:
                        north, east = _num(parts[0]), _num(parts[1])
                continue
            stamp = child.find(".//gml:timePosition", NS)
            text = stamp.text if stamp is not None else (child.text or "")
            text = text.strip() if text else ""
            raw[name] = text or None
        records.append(_build_record(raw, north, east, cfg))
    return records, len(records)


def _build_record(raw, north, east, cfg):
    tran, nier = _num(raw.get("TRAN_CENA_BRUTTO")), _num(raw.get("NIER_CENA_BRUTTO"))
    obj, area = _num(raw.get(cfg["price"])), _num(raw.get(cfg["area"]))
    obj_id = raw.get(cfg["obj_id"])
    if obj_id is None:
        obj_id = next((v for k, v in raw.items() if k.startswith(cfg["prefix"]) and "_ID_" in k), None)
    city, street, number = _parse_address(raw.get(cfg["addr"]))
    date = raw.get("DOK_DATA")
    rooms = raw.get(cfg["rooms"]) if cfg["rooms"] else None
    return {
        "gid": int(raw["gid"]),
        "teryt": raw.get("TERYT"),
        "tran_id": raw.get("TRAN_LOKALNY_ID_IIP"),
        "obj_id": obj_id,
        "dok_data": date[:10] if date else None,
        "rodzaj_rynku": raw.get("TRAN_RODZAJ_RYNKU"),
        "rodzaj_obiektu": raw.get(cfg["kind"]),
        "liczba_izb": int(rooms) if rooms and rooms.isdigit() else None,
        "tran_cena": tran,
        "nier_cena": nier,
        "obj_cena": obj,
        "pow_m2": area,
        "cena_m2": _price_per_m2(tran, nier, obj, area),
        "miejscowosc": city,
        "ulica": street,
        "nr": number,
        "y_pl1992": north,     # EPSG:2180 axis order is northing, easting
        "x_pl1992": east,
        "raw_json": json.dumps(raw, ensure_ascii=False, sort_keys=True),
    }


def build_filter(teryt, last_gid):
    if not str(teryt).isdigit():
        raise RcnError("TERYT musi składać się z cyfr: %r" % (teryt,))
    return (
        '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0"><fes:And>'
        "<fes:PropertyIsEqualTo><fes:ValueReference>TERYT</fes:ValueReference>"
        "<fes:Literal>%s</fes:Literal></fes:PropertyIsEqualTo>"
        "<fes:PropertyIsGreaterThan><fes:ValueReference>gid</fes:ValueReference>"
        "<fes:Literal>%d</fes:Literal></fes:PropertyIsGreaterThan>"
        "</fes:And></fes:Filter>" % (teryt, int(last_gid))
    )


class WfsClient:
    def __init__(self, url=DEFAULT_URL, timeout=60, retries=5, backoff=2.0, sleep=time.sleep):
        self.url, self.timeout, self.retries = url, timeout, retries
        self.backoff, self.sleep = backoff, sleep
        self.retries_used = 0

    def get_features(self, layer, teryt, last_gid, page_size):
        params = {
            "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
            "TYPENAMES": "ms:%s" % layer, "COUNT": str(page_size),
            "SORTBY": "gid A", "FILTER": build_filter(teryt, last_gid),
        }
        url = "%s?%s" % (self.url, urllib.parse.urlencode(params))
        request = urllib.request.Request(url, headers={"User-Agent": "mieszkanie100-rcn-importer/0.1"})
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    body = resp.read()
                return parse_feature_collection(body, layer)
            except (urllib.error.URLError, OSError, WfsError) as exc:
                last_error = exc
                if attempt < self.retries:
                    self.retries_used += 1
                    self.sleep(self.backoff * (2 ** attempt))
        raise WfsError("po %d próbach: %s" % (self.retries + 1, last_error))


class Store:
    def __init__(self, path):
        self.con = sqlite3.connect(path)
        # Default rollback journal: WAL is unreliable on network shares (NAS).
        self.con.execute("PRAGMA synchronous=FULL")
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS checkpoint (layer TEXT, teryt TEXT, last_gid INTEGER NOT NULL,"
            " pages INTEGER NOT NULL, updated TEXT, PRIMARY KEY (layer, teryt))")
        for layer in LAYERS:
            self.con.execute(
                "CREATE TABLE IF NOT EXISTS %s (gid INTEGER PRIMARY KEY, teryt TEXT, tran_id TEXT, obj_id TEXT,"
                " dok_data TEXT, rodzaj_rynku TEXT, rodzaj_obiektu TEXT, liczba_izb INTEGER, tran_cena REAL,"
                " nier_cena REAL, obj_cena REAL, pow_m2 REAL, cena_m2 REAL, miejscowosc TEXT, ulica TEXT,"
                " nr TEXT, y_pl1992 REAL, x_pl1992 REAL, raw_json TEXT, fetched_at TEXT)" % layer)
        self.con.commit()

    _COLS = ("gid", "teryt", "tran_id", "obj_id", "dok_data", "rodzaj_rynku", "rodzaj_obiektu", "liczba_izb",
             "tran_cena", "nier_cena", "obj_cena", "pow_m2", "cena_m2", "miejscowosc", "ulica", "nr",
             "y_pl1992", "x_pl1992", "raw_json")

    def checkpoint(self, layer, teryt):
        row = self.con.execute("SELECT last_gid FROM checkpoint WHERE layer=? AND teryt=?", (layer, teryt)).fetchone()
        return row[0] if row else 0

    def save_page(self, layer, teryt, records, last_gid):
        """Rows and checkpoint in one transaction; re-saving the same gid is harmless."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        sql = "INSERT OR REPLACE INTO %s (%s, fetched_at) VALUES (%s)" % (
            layer, ", ".join(self._COLS), ", ".join("?" * (len(self._COLS) + 1)))
        with self.con:
            self.con.executemany(sql, [tuple(r[c] for c in self._COLS) + (now,) for r in records])
            self.con.execute(
                "INSERT INTO checkpoint (layer, teryt, last_gid, pages, updated) VALUES (?, ?, ?, 1, ?)"
                " ON CONFLICT(layer, teryt) DO UPDATE SET last_gid=excluded.last_gid,"
                " pages=checkpoint.pages+1, updated=excluded.updated", (layer, teryt, last_gid, now))

    def count(self, layer, teryt):
        return self.con.execute("SELECT COUNT(*) FROM %s WHERE teryt=?" % layer, (teryt,)).fetchone()[0]

    def close(self):
        self.con.close()


class ImportStats:
    def __init__(self):
        self.pages = 0
        self.records = 0
        self.retries = 0
        self.finished = False


def import_layer(client, store, layer, teryt, page_size=1000, pause=0.5, max_pages=None, log=None):
    if layer not in LAYERS:
        raise RcnError("nieznana warstwa: %s" % layer)
    stats, last = ImportStats(), store.checkpoint(layer, teryt)
    retries_before = client.retries_used
    while True:
        if max_pages is not None and stats.pages >= max_pages:
            break
        records, _ = client.get_features(layer, teryt, last, page_size)
        if not records:
            stats.finished = True      # only an empty page ends the import, never a short one
            break
        gids = [r["gid"] for r in records]
        if min(gids) <= last or gids != sorted(gids):
            raise RcnError("serwer nie respektuje filtra gid lub sortowania po gid (poprzedni gid=%d, "
                           "otrzymano %d..%d). Stronicowanie kluczem gid nie działa." % (last, min(gids), max(gids)))
        if any(r["teryt"] != teryt for r in records):
            raise RcnError("serwer zwrócił rekordy spoza TERYT %s: filtr TERYT nie działa." % teryt)
        last = max(gids)
        store.save_page(layer, teryt, records, last)
        stats.pages += 1
        stats.records += len(records)
        if log:
            log("%s %s: strona %d, +%d rekordów, last_gid=%d" % (layer, teryt, stats.pages, len(records), last))
        if pause > 0:
            time.sleep(pause)
    stats.retries = client.retries_used - retries_before
    return stats


def build_report(store, layer, teryt, expect_count=None):
    q = lambda sql, *a: store.con.execute(sql % layer, (teryt,) + a).fetchone()
    total = q("SELECT COUNT(*) FROM %s WHERE teryt=?")[0]
    first, last = q("SELECT MIN(dok_data), MAX(dok_data) FROM %s WHERE teryt=?")
    no_price = q("SELECT COUNT(*) FROM %s WHERE teryt=? AND obj_cena IS NULL")[0]
    no_area = q("SELECT COUNT(*) FROM %s WHERE teryt=? AND (pow_m2 IS NULL OR pow_m2 <= 0)")[0]
    with_m2 = q("SELECT COUNT(*) FROM %s WHERE teryt=? AND cena_m2 IS NOT NULL")[0]
    dup_keys = q("SELECT COALESCE(SUM(n - 1), 0) FROM (SELECT COUNT(*) AS n FROM %s WHERE teryt=? AND tran_id IS NOT NULL"
                 " GROUP BY tran_id, obj_id HAVING n > 1)")[0]
    years = store.con.execute(
        "SELECT substr(dok_data, 1, 4), COUNT(*) FROM %s WHERE teryt=? GROUP BY 1 ORDER BY 1" % layer,
        (teryt,)).fetchall()
    cp = store.con.execute("SELECT last_gid, pages FROM checkpoint WHERE layer=? AND teryt=?", (layer, teryt)).fetchone()
    lines = [
        "Raport RCN: warstwa=%s TERYT=%s" % (layer, teryt),
        "rekordów w bazie:      %10d" % total,
        "zakres dat dok_data:   %s .. %s" % (first, last),
        "bez ceny obiektu:      %10d" % no_price,
        "bez powierzchni:       %10d" % no_area,
        "z ceną za m2:          %10d" % with_m2,
        "powtórzone klucze (tran_id+obj_id, wiele wersji?): %d" % dup_keys,
        "rozkład wg roku: " + ", ".join("%s: %d" % (y, n) for y, n in years),
        "checkpoint: last_gid=%s, stron=%s" % (cp if cp else ("brak", "brak")),
    ]
    if expect_count is None:
        lines.append("STATUS KOMPLETNOŚCI: NIEZWERYFIKOWANA (brak liczby referencyjnej, użyj --expect-count)")
    elif expect_count == total:
        lines.append("STATUS KOMPLETNOŚCI: ZGODNA z liczbą referencyjną (%d)" % expect_count)
    else:
        lines.append("STATUS KOMPLETNOŚCI: NIEZGODNA (baza %d, oczekiwano %d, różnica %+d)"
                     % (total, expect_count, total - expect_count))
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description="Import cen transakcyjnych RCN z WFS do SQLite.")
    p.add_argument("--teryt", required=True, help="kod TERYT powiatu, np. 2469 (Katowice)")
    p.add_argument("--layer", default="lokale", choices=list(LAYERS) + ["all"])
    p.add_argument("--db", default="rcn.sqlite")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--page-size", type=int, default=1000)
    p.add_argument("--pause", type=float, default=0.5, help="przerwa między stronami [s]")
    p.add_argument("--max-pages", type=int, default=None, help="ogranicz liczbę stron (test)")
    p.add_argument("--expect-count", type=int, default=None, help="liczba referencyjna rekordów do porównania")
    p.add_argument("--report-only", action="store_true")
    args = p.parse_args(argv)

    layers = list(LAYERS) if args.layer == "all" else [args.layer]
    store = Store(args.db)
    client = WfsClient(args.url)
    exit_code = 0
    try:
        for layer in layers:
            if not args.report_only:
                stats = import_layer(client, store, layer, args.teryt, args.page_size, args.pause,
                                     args.max_pages, log=lambda m: print(m, file=sys.stderr))
                print("%s: stron %d, nowych rekordów %d, ponowień %d, zakończono: %s"
                      % (layer, stats.pages, stats.records, stats.retries, "tak" if stats.finished else "NIE"))
                if not stats.finished:
                    exit_code = 1
            print(build_report(store, layer, args.teryt, args.expect_count))
            print()
    except KeyboardInterrupt:
        print("Przerwano. Checkpoint zapisany, uruchom ponownie, aby wznowić.", file=sys.stderr)
        exit_code = 130
    except RcnError as exc:
        print("BŁĄD: %s" % exc, file=sys.stderr)
        exit_code = 2
    finally:
        store.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
