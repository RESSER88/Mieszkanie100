#!/usr/bin/env python3
"""Fragmenty stron, które pokazują, gdzie portale trzymają położenie i metraż, oraz adresy API mScanner.

Uruchamiać na Raspberry Pi po scripts/portale_probe.sh i po karcie Morizon (rcn/karta.py LINK):
  python3 scripts/diag_portale.py
Czyta pliki z ref/zrodla/ i ref/oferty/. Z sieci pobiera tylko: listę Morizon dla Katowic (1 strona) i do 8
plików JavaScript mScanner, po jednym, z pauzą 2 s i uczciwym identyfikatorem. Wypisuje krótkie wycinki tekstu.
"""
import glob
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ref", "zrodla")
UA = "Mozilla/5.0 (compatible; mieszkanie100/0.1; prywatne narzedzie, jedno zapytanie na zadanie)"


def get(url, name):
    path = os.path.join(OUT, name)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read().decode("utf-8", "replace")
        with open(path, "w", encoding="utf-8") as f:
            f.write(data)
        print("== pobrano %s (%d znaków)" % (url, len(data)))
    except Exception as exc:          # a probe: report and go on
        print("== %s: %s" % (url, exc))
        data = ""
    time.sleep(2)
    return data


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def snippets(text, pattern, n=3, width=160):
    out = []
    for m in re.finditer(pattern, text):
        start = max(0, m.start() - width // 2)
        out.append(" ".join(text[start:m.end() + width // 2].split()))
        if len(out) == n:
            break
    for s in out:
        print("   …%s…" % s)
    if not out:
        print("   (brak: %s)" % pattern)


def main():
    os.makedirs(OUT, exist_ok=True)
    print("### Nieruchomosci-online: lista wyników (ref/zrodla/no_wyniki.html)")
    no = read(os.path.join(OUT, "no_wyniki.html"))
    snippets(no, r'"?latitude"?', 3)
    snippets(no, r"var map[A-Za-z_-]*\s*=", 2)

    print("### Morizon: strona ogłoszenia zapisana przez kartę (ref/oferty/*morizon*)")
    pages = sorted(glob.glob(os.path.join(ROOT, "ref", "oferty", "*morizon*.html")))
    page = read(pages[-1]) if pages else ""
    print("   plik:", pages[-1] if pages else "brak (uruchom najpierw rcn/karta.py z linkiem Morizon)")
    print("   __INITIAL_STATE__:", "__INITIAL_STATE__" in page, "| JSON-LD:", page.count("application/ld+json"),
          "| __NEXT_DATA__:", "__NEXT_DATA__" in page, "| __NUXT:", "__NUXT" in page)
    for pattern in (r'"coords"', r'"latitude"|"lat"\s*:', r'"area"|"livingArea"|powierzchnia', r'"price"\s*:'):
        snippets(page, pattern, 2)

    print("### Morizon: lista wyników")
    lst = get("https://www.morizon.pl/mieszkania/katowice/", "morizon_lista.html")
    snippets(lst, r'"coords"|"latitude"|"lat"\s*:', 3)

    print("### mScanner: pliki ładowane później (adresy API)")
    bundles = "".join(read(p) for p in glob.glob(os.path.join(OUT, "mscanner*")))
    names = sorted(set(re.findall(r"assets/[A-Za-z0-9_.-]+\.js", bundles)))
    wanted = [n for n in names if re.search(r"develop|primary|offer|invest|permit|map|heat|new|api|search", n, re.I)]
    print("   plików w odnośnikach: %d, wybrane: %s" % (len(names), ", ".join(wanted[:8]) or "brak"))
    texts = [bundles] + [get("https://mscanner.pl/" + n, "mscanner_chunk_%d.js" % i) for i, n in enumerate(wanted[:8])]
    found = sorted(set(m for t in texts for m in re.findall(r"(?:https://api\.mscanner\.pl)?/api/[A-Za-z0-9_./{}$-]+", t)))
    print("   adresy /api/:", ", ".join(found[:40]) or "brak")
    joined = "\n".join(texts)
    snippets(joined, r"api\.mscanner\.pl", 4)
    snippets(joined, r"developer[-_]?offers|new[-_]?developments|investments|permits", 4)
    return 0


if __name__ == "__main__":
    sys.exit(main())
