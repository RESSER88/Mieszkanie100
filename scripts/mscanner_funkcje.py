#!/usr/bin/env python3
"""Lista funkcji mScanner z jego publicznych stron, do porównania z Mieszkanie100 (tylko odniesienie).

Uruchamiać na Raspberry Pi:  python3 scripts/mscanner_funkcje.py
Czyta tylko strony publiczne; ścieżek /app/ i /api/ nie dotyka (blokuje je robots.txt mScanner, które deklaruje
też ai-train=no, use=reference). Nic nie jest kopiowane do repozytorium: wynik idzie na ekran, pliki do ref/mscanner/.
Każda strona raz, pauza 3 s, uczciwy identyfikator. Wypisuje nagłówki stron i nazwy funkcji z napisów interfejsu.
"""
import html
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ref", "mscanner")
UA = "Mozilla/5.0 (compatible; mieszkanie100/0.1; prywatne narzedzie, jedno zapytanie na zadanie)"
PAGES = ["/", "/porownywarka-mieszkan", "/ceny-mieszkan", "/raport-nieruchomosci/porownanie",
         "/ceny-transakcyjne-mieszkan/katowice", "/index-en"]
FEATURE_KEYS = re.compile(r'"((?:primary|pricing|feature|features|report|raport|faq|hero|module|section|card|panel|'
                          r'compare|commute|heatmap|map|plan|noise|flood|permit)[A-Za-z0-9_.-]*)"\s*:\s*"([^"]{3,160})"')


def allowed(path: str) -> bool:
    return not (path.startswith("/app/") or path.startswith("/api/"))


def get(path: str) -> str:
    url = "https://mscanner.pl" + path
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8", "replace")
        print("== %s: %d znaków" % (path, len(text)))
    except Exception as exc:          # a probe: report and continue
        print("== %s: %s" % (path, exc))
        text = ""
    time.sleep(3)
    return text


def headings(page: str):
    for level, inner in re.findall(r"<h([1-3])[^>]*>(.*?)</h\1>", page, re.S | re.I)[:40]:
        text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", inner)).split())
        if text:
            print("   %sh%s %s" % ("  " * (int(level) - 1), level, text[:120]))


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    scripts = set()
    for path in PAGES:
        if not allowed(path):
            continue
        page = get(path)
        with open(os.path.join(OUT, (path.strip("/").replace("/", "_") or "index") + ".html"), "w", encoding="utf-8") as f:
            f.write(page)
        headings(page)
        scripts.update(s for s in re.findall(r'<script[^>]+src="(/[^"]+\.js)"', page) if allowed(s))
    print("### Napisy interfejsu z plików JavaScript (nazwy funkcji i sekcji)")
    seen = set()
    for src in sorted(scripts)[:12]:
        for key, value in FEATURE_KEYS.findall(get(src)):
            if (key, value) not in seen:
                seen.add((key, value))
                print("   %-40s %s" % (key[:40], value))
    return 0


if __name__ == "__main__":
    sys.exit(main())
