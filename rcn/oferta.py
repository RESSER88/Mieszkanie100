#!/usr/bin/env python3
"""Read one property listing on demand: fetch the page and pull out structured data.

`probe` fetches a single listing URL given by the user (one request, no crawling),
saves the HTML under ref/oferty/ (not in git) and prints only candidate fields such as
price, area, rooms, year, address and coordinates from JSON-LD, __NEXT_DATA__ and meta
tags. Contact data (phones, e-mails, agent names) is never printed. The output is what
portal-specific parsers are written from. Standard library only.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

USER_AGENT = "Mozilla/5.0 (compatible; mieszkanie100/0.1; prywatne narzedzie, jedno zapytanie na zadanie)"
MAX_CANDIDATES = 80
MAX_TEXT = 120
_TRACKING = re.compile(r"^(utm_.*|gclid|gad_.*|fbclid|msclkid|dclid|yclid|_ga)$", re.I)
_INCLUDE = re.compile(
    r"(price|cena|amount|area|powierzchn|surface|size|room|pokoj|pokoi|floor|pietr|piętr|year|rok|build|"
    r"lat|lon|lng|geo|coord|street|ulica|address|adres|city|miasto|district|dzielnic|locality|location|"
    r"lokalizac|market|rynek|title|tytul|garden|ogrod|ogród|terrace|taras|balcon|balkon|parking|garage|garaz)", re.I)
_EXCLUDE = re.compile(r"(phone|tel|mail|contact|kontakt|agent|owner|user|seller|advertiser|broker|person|"
                      r"agency|office|biuro|realtor|posrednik|pośrednik)", re.I)


def clean_url(url: str) -> str:
    """Drop advertising and tracking parameters; only http and https are accepted."""
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("to nie jest adres strony internetowej: %r" % url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if not _TRACKING.match(k)]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), ""))


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.meta, self.blocks = "", [], []
        self._in_title, self._script = False, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = a.get("property") or a.get("name") or ""
            if key.startswith(("og:", "product:", "place:")) and a.get("content"):
                self.meta.append((key, a["content"]))
        elif tag == "script":
            kind = (a.get("type") or "").lower()
            if kind == "application/ld+json":
                self._script = ["ld_json", []]
            elif a.get("id") == "__NEXT_DATA__":
                self._script = ["next_data", []]
            elif kind == "application/json":
                self._script = ["json_%s" % (a.get("id") or "bez_id"), []]

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._script is not None:
            self.blocks.append((self._script[0], "".join(self._script[1])))
            self._script = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._script is not None:
            self._script[1].append(data)


def _walk(value: Any, path: str, out: List[Tuple[str, Any]]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _walk(child, "%s.%s" % (path, key), out)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _walk(child, "%s[%d]" % (path, i), out)
    elif value is not None and value != "":
        segments = re.split(r"[.\[\]]+", path)
        if any(_EXCLUDE.search(s) for s in segments):
            return
        if not any(_INCLUDE.search(s) for s in segments[1:]):
            return
        if isinstance(value, str):
            value = " ".join(value.split())
            if len(value) > MAX_TEXT:
                value = value[:MAX_TEXT - 1] + "…"
        out.append((path, value))


def extract_structured(html: str) -> Dict[str, Any]:
    """Title, counts of structured sources and (path, value) candidates without contact data."""
    parser = _PageParser()
    parser.feed(html)
    sources: Dict[str, int] = {}
    candidates: List[Tuple[str, Any]] = []
    broken = 0
    ld_index = 0
    for kind, text in parser.blocks:
        try:
            data = json.loads(text)
        except ValueError:
            broken += 1
            continue
        if kind == "ld_json":
            prefix, ld_index = "ld_json[%d]" % ld_index, ld_index + 1
        else:
            prefix = kind
        group = "inne_json" if kind.startswith("json_") else kind
        sources[group] = sources.get(group, 0) + 1
        _walk(data, prefix, candidates)
    if parser.meta:
        sources["meta"] = len(parser.meta)
        for key, content in parser.meta:
            _walk(content, "meta.%s" % key, candidates)
    return {"tytul": " ".join(parser.title.split()), "zrodla": sources,
            "kandydaci": candidates, "bledne_bloki": broken}


def fetch(url: str, timeout: float = 30.0) -> Tuple[int, Optional[str]]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "pl,en;q=0.5"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.status, resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, None


def save_html(url: str, html: str, out_dir: str) -> str:
    parts = urllib.parse.urlsplit(url)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", parts.netloc + "_" + parts.path.strip("/").split("/")[-1])[:120]
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, stem + ".html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def format_probe(url: str, status: int, saved: Optional[str], result: Optional[Dict[str, Any]],
                 from_file: Optional[str] = None) -> str:
    lines = ["Adres: %s" % url, "Plik: %s" % from_file if from_file else "HTTP %d" % status]
    if status != 200 or result is None:
        lines.append("HTTP %d: portal odmówił lub strony nie ma. Nie ponawiać w pętli; wkleić ten wynik." % status)
        return "\n".join(lines)
    total = len(result["kandydaci"])
    if not from_file:
        lines.append("Zapisano: %s" % saved)
    lines += ["Tytuł: %s" % result["tytul"],
              "Źródła danych: %s" % (", ".join("%s=%d" % kv for kv in sorted(result["zrodla"].items())) or "brak"),
              "Błędne bloki JSON: %d" % result["bledne_bloki"],
              "Pola kandydujące (%d z %d):" % (min(total, MAX_CANDIDATES), total)]
    lines += ["  %s = %s" % (path, value) for path, value in result["kandydaci"][:MAX_CANDIDATES]]
    lines.append("Bez danych kontaktowych. Proszę wkleić ten wynik do rozmowy.")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Odczyt jednego ogłoszenia (na żądanie użytkownika).")
    sub = p.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("probe", help="pobierz jedno ogłoszenie i pokaż dane strukturalne")
    probe.add_argument("url")
    probe.add_argument("--out-dir", default=os.path.join("ref", "oferty"))
    probe.add_argument("--file", help="strona zapisana w przeglądarce (bez pobierania z internetu)")
    args = p.parse_args(argv)
    try:
        url = clean_url(args.url)
    except ValueError as exc:
        print("BŁĄD: %s" % exc, file=sys.stderr)
        return 2
    if args.file:
        try:
            with open(args.file, encoding="utf-8", errors="replace") as f:
                html = f.read()
        except OSError:
            print("BŁĄD: nie ma pliku %s" % args.file, file=sys.stderr)
            return 2
        print(format_probe(url, 200, None, extract_structured(html), from_file=args.file))
        return 0
    try:
        status, html = fetch(url)
    except (urllib.error.URLError, OSError) as exc:
        print("BŁĄD połączenia: %s" % exc, file=sys.stderr)
        return 2
    saved = save_html(url, html, args.out_dir) if html is not None else None
    result = extract_structured(html) if html is not None else None
    print(format_probe(url, status, saved, result))
    return 0 if status == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
