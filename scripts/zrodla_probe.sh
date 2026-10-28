#!/usr/bin/env bash
# Rozpoznanie oficjalnych źródeł PSE i GDDKiA (pozycja 7 kolejki). Uruchamiać na Raspberry Pi:
#   bash scripts/zrodla_probe.sh
# Każda strona jest pobierana raz, z uczciwym identyfikatorem, i zapisywana w ref/zrodla/ do wglądu.
# Skrypt niczego nie zapisuje w bazach. Wypisuje: kod HTTP, rozmiar, nazwy warstw usług WMS/WFS
# oraz linki do usług map (WMS, WFS, ArcGIS) i plików z danymi (xlsx, csv, json, kml, zip, pdf).
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=ref/zrodla
mkdir -p "$OUT"
UA="Mozilla/5.0 (compatible; mieszkanie100/0.1; prywatne narzedzie, jedno zapytanie na zadanie)"

fetch() {   # fetch NAME URL
  local name=$1 url=$2 code
  code=$(curl -sS -L -m 60 -A "$UA" -o "$OUT/$name" -w '%{http_code}' "$url" 2>"$OUT/$name.err") || code="błąd"
  local size=0
  [ -f "$OUT/$name" ] && size=$(wc -c < "$OUT/$name")
  echo "== $name: HTTP $code, $size bajtów ($url)"
  [ -s "$OUT/$name.err" ] && head -2 "$OUT/$name.err"
  sleep 2
}

links() {   # links NAME
  grep -oiE "https?://[^\"'<> ]+\.(xlsx|xls|csv|json|geojson|kml|kmz|zip|gpkg|shp|pdf)|https?://[^\"'<> ]*(wms|wfs|wmts|arcgis/rest|MapServer|FeatureServer|geoserver)[^\"'<> ]*" \
    "$OUT/$1" 2>/dev/null | sort -u | head -40 | sed 's/^/   /'
}

layers() {  # layers NAME : layer names and titles from a WMS/WFS GetCapabilities answer
  grep -oE "<(Name|Title)>[^<]*</(Name|Title)>" "$OUT/$1" 2>/dev/null | sed -E 's/<[^>]+>//g' | head -60 | sed 's/^/   /'
}

echo "### GDDKiA"
fetch gddkia_siec_wms.xml "https://mapy.geoportal.gov.pl/wss/ext/GDDKiA/SiecDrogowa?SERVICE=WMS&REQUEST=GetCapabilities"
layers gddkia_siec_wms.xml
fetch gddkia_siec_wfs.xml "https://mapy.geoportal.gov.pl/wss/ext/GDDKiA/SiecDrogowa?SERVICE=WFS&REQUEST=GetCapabilities"
layers gddkia_siec_wfs.xml
fetch gddkia_uslugi_wms.html "https://www.gddkia.gov.pl/pl/1823/Uslugi-WMS"
links gddkia_uslugi_wms.html
fetch gddkia_msbd.html "https://www.gov.pl/web/gddkia/msbd"
links gddkia_msbd.html
fetch gddkia_mapy.html "https://drogi.gddkia.gov.pl/mapy"
links gddkia_mapy.html

echo "### PSE"
fetch pse_plan.html "https://www.pse.pl/obszary-dzialalnosci/krajowy-system-elektroenergetyczny/plan-sieci-elektroenergetycznej-najwyzszych-napiec"
links pse_plan.html
fetch pse_inwestycje.html "https://www.pse.pl/inwestycje/interaktywna-mapa-inwestycji"
links pse_inwestycje.html
fetch osm_wiki_pse.html "https://wiki.openstreetmap.org/wiki/Power_networks/Poland/PSE"
grep -oE "relation/[0-9]+" "$OUT/osm_wiki_pse.html" 2>/dev/null | sort -u | wc -l | sed 's/^/   relacji OSM na stronie wiki: /'

echo "### Gotowe. Pliki w $OUT/ (nie trafiają do repozytorium)."
