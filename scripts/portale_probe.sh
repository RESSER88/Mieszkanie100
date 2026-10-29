#!/usr/bin/env bash
# Rozpoznanie wyszukiwania Nieruchomosci-online i nowych inwestycji w mScanner (2026-10-29). Na Raspberry Pi:
#   bash scripts/portale_probe.sh "ADRES_STRONY_WYNIKÓW_NIERUCHOMOSCI_ONLINE"
# Adres to strona wyników dla Katowic skopiowana z przeglądarki. Bez adresu skrypt próbuje strony miasta.
# Każda strona pobierana raz, z pauzą, z uczciwym identyfikatorem; kopie w ref/zrodla/ (poza repozytorium).
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=ref/zrodla
mkdir -p "$OUT"
UA="Mozilla/5.0 (compatible; mieszkanie100/0.1; prywatne narzedzie, jedno zapytanie na zadanie)"
NO_URL="${1:-https://katowice.nieruchomosci-online.pl/}"

get() {   # get NAME URL
  local code size=0
  code=$(curl -sS -L -m 60 -A "$UA" -o "$OUT/$1" -w '%{http_code}' "$2" 2>"$OUT/$1.err") || code="błąd"
  [ -f "$OUT/$1" ] && size=$(wc -c < "$OUT/$1")
  echo "== $1: HTTP $code, $size bajtów ($2)"
  [ -s "$OUT/$1.err" ] && head -2 "$OUT/$1.err"
  sleep 2
}

echo "### Nieruchomosci-online: strona wyników"
get no_wyniki.html "$NO_URL"
python3 - "$OUT/no_wyniki.html" <<'PY'
import re, sys
html = open(sys.argv[1], encoding="utf-8", errors="replace").read()
print("   kafelków 'tile':", len(re.findall(r'class="[^"]*\btile\b', html)))
print("   tytułów h2.name:", len(re.findall(r'<h2[^>]*class="[^"]*\bname\b', html)))
print("   pól ceny/metrażu tertiary__box--primary:", len(re.findall(r'tertiary__box--primary', html)))
print("   bloków JSON-LD:", html.count("application/ld+json"), "| wzmianek 'latitude':", html.count("latitude"))
for m in list(re.finditer(r'<h2[^>]*class="[^"]*\bname\b[^"]*"[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S))[:3]:
    print("   przykład:", re.sub(r"<[^>]+>|\s+", " ", m.group(2)).strip()[:70], "|", m.group(1)[:90])
pages = sorted({int(p) for p in re.findall(r'[?&]p=(\d+)', html)})
print("   numery stron w linkach:", pages[:10], "..." if len(pages) > 10 else "")
PY

echo "### mScanner: strona i skrypty (szukam adresów API, zwłaszcza inwestycji)"
get mscanner.html "https://mscanner.pl/"
grep -oE '<script[^>]+src="[^"]+"' "$OUT/mscanner.html" 2>/dev/null | sed -E 's/.*src="([^"]+)".*/\1/' | head -6 > "$OUT/mscanner_js.txt"
n=0
while read -r src; do
  n=$((n + 1))
  case "$src" in http*) url="$src" ;; /*) url="https://mscanner.pl$src" ;; *) url="https://mscanner.pl/$src" ;; esac
  get "mscanner_$n.js" "$url"
done < "$OUT/mscanner_js.txt"
cat "$OUT"/mscanner.html "$OUT"/mscanner_*.js 2>/dev/null | grep -oE '(https://api\.mscanner\.pl)?/api/[A-Za-z0-9_./{}-]+' | sort -u | head -40 | sed 's/^/   /'
echo "   wzmianki o inwestycjach:"
cat "$OUT"/mscanner.html "$OUT"/mscanner_*.js 2>/dev/null | grep -oiE '.{0,40}(inwestycj|investment|developer|deweloper).{0,40}' | sort -u | head -15 | sed 's/^/   /'
echo "### Gotowe. Pliki w $OUT/."
