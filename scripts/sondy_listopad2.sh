#!/usr/bin/env bash
# Druga sonda (2026-11-02), z Raspberry Pi:  bash scripts/sondy_listopad2.sh
# Sprawdza: nowe moduły karty na punkcie przy Szurmana, czy warstwy WMS przyjmują EPSG:3857 (mapa w przeglądarce),
# hałas (GDDKiA, halas.katowice.eu), powódź (ISOK), osuwiska (SOPO), indeks GIOŚ. Odpowiedzi w ref/sondy/.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=ref/sondy
mkdir -p "$OUT"
UA="Mozilla/5.0 (compatible; mieszkanie100/0.1; prywatne narzedzie, jedno zapytanie na zadanie)"
N=262720.44; E=497795.80

get() {
  local code size=0
  code=$(curl -sS -L -m 60 -A "$UA" -o "$OUT/$1" -w '%{http_code}' "$2" 2>"$OUT/$1.err") || code="błąd"
  [ -f "$OUT/$1" ] && size=$(wc -c < "$OUT/$1")
  echo "== $1: HTTP $code, $size bajtów"
  sleep 2
}
names() { grep -oE "<Name>[^<]*</Name>" "$OUT/$1" 2>/dev/null | sed -E 's/<[^>]+>//g' | head -${2:-25} | tr '\n' '|' | sed 's/^/   /'; echo; }
links() { grep -oiE "https?://[^\"' <>]*(wms|wfs|arcgis|MapServer|wss|geoserver|jarc)[^\"' <>]*" "$OUT/$1" 2>/dev/null | sort -u | head -${2:-12} | sed 's/^/   /'; }

echo "### A. Moduły karty na punkcie (działka, plan, górnictwo, geozagrożenia, powietrze)"
python3 - <<PY
import json, sys
sys.path.insert(0, ".")
from rcn import grunt, powietrze, otoczenie
point = ($N, $E)
r = grunt.report(point, "ref/sondy/bufor_sonda.sqlite")
print("   bledy:", r["bledy"])
print("   dzialka:", r["dzialka"])
print("   plan:", json.dumps(r["plan"], ensure_ascii=False)[:600])
print("   gornictwo:", r.get("gornictwo_opis"))
print("   geozagrozenia:", json.dumps(r["geozagrozenia"], ensure_ascii=False)[:500])
lat, lon = otoczenie.pl1992_to_wgs84(*point)
try:
    print("   powietrze:", powietrze.air_quality(lat, lon, "ref/sondy/bufor_sonda.sqlite"))
except Exception as exc:
    print("   powietrze: BŁĄD", exc)
PY

echo "### B. Czy warstwy WMS przyjmują EPSG:3857 (potrzebne do mapy w przeglądarce)"
for f in kieg_caps.xml mpzp_caps.xml gdos_caps.xml orto_arch_caps.xml; do
  printf "   %-20s 3857: %s  2180: %s\n" "$f" "$(grep -c 'EPSG:3857' "$OUT/$f" 2>/dev/null)" "$(grep -c 'EPSG:2180' "$OUT/$f" 2>/dev/null)"
done
echo "   warstwy KIEG:"; names kieg_caps.xml 40

echo "### C. Hałas: usługi GDDKiA (warstwy) i mapa Katowic"
get halas_ldwn_caps.xml "https://mapy.geoportal.gov.pl/wss/service/gddkia/mapaImisyjnaLDWN?SERVICE=WMS&REQUEST=GetCapabilities"
names halas_ldwn_caps.xml 15
printf "   3857: %s\n" "$(grep -c 'EPSG:3857' "$OUT/halas_ldwn_caps.xml" 2>/dev/null)"
get halas_katowice.html "http://halas.katowice.eu/"
links halas_katowice.html 15
grep -oiE "[\"'][^\"']*(ldwn|lden|lnight|halas|layer|warstw)[^\"']*[\"']" "$OUT/halas_katowice.html" | sort -u | head -15 | sed 's/^/   /'

echo "### D. Powódź (ISOK): kandydaci usług WMS"
for u in "https://wody.isok.gov.pl/wss/INSPIRE/INSPIRE_NZ_HY_MZPMRP_WMS" "https://wody.isok.gov.pl/gpservices/KZGW/MZP_MRP/MapServer/WMSServer" \
         "https://mapy.geoportal.gov.pl/wss/ext/KZGW/MapaZagrozeniaPowodziowego"; do
  safe=$(echo "$u" | md5sum | cut -c1-8)
  get "isok_$safe.xml" "$u?SERVICE=WMS&REQUEST=GetCapabilities"
  head -c 300 "$OUT/isok_$safe.xml" | tr '\n' ' ' | sed 's/^/   /'; echo
done
echo "   skrypty strony mapy ISOK:"
grep -oE 'src="[^"]+\.js[^"]*"' "$OUT/isok.html" 2>/dev/null | head -8 | sed 's/^/   /'

echo "### E. Osuwiska SOPO: warstwy"
get sopo.json "https://cbdgmapa.pgi.gov.pl/arcgis/rest/services/geozagrozenia/sopo_obszary/MapServer?f=json"
python3 -c "import json; d=json.load(open('$OUT/sopo.json')); print('   ', [(l['id'], l['name']) for l in d.get('layers', [])])" 2>/dev/null

echo "### Gotowe. Proszę wkleić cały wynik."
