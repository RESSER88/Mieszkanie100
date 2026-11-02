#!/usr/bin/env bash
# Sondy źródeł do karty (2026-11-02), z Raspberry Pi:  bash scripts/sondy_listopad.sh
# Punkt testowy: ul. Szurmana, EPSG:2180 northing 262720.44, easting 497795.80 (WGS84 50.23168, 18.96909).
# Każde zapytanie raz, z pauzą 2 s i uczciwym identyfikatorem; odpowiedzi w ref/sondy/ (poza repozytorium).
# Wypisuje krótkie wycinki, które wystarczą do napisania kodu: nazwy warstw, pola, formaty, przykładową odpowiedź.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=ref/sondy
mkdir -p "$OUT"
UA="Mozilla/5.0 (compatible; mieszkanie100/0.1; prywatne narzedzie, jedno zapytanie na zadanie)"
N=262720.44; E=497795.80; LAT=50.23168; LON=18.96909

get() {   # get NAME URL
  local code size=0
  code=$(curl -sS -L -m 60 -A "$UA" -o "$OUT/$1" -w '%{http_code}' "$2" 2>"$OUT/$1.err") || code="błąd"
  [ -f "$OUT/$1" ] && size=$(wc -c < "$OUT/$1")
  echo "== $1: HTTP $code, $size bajtów"
  [ -s "$OUT/$1.err" ] && head -1 "$OUT/$1.err"
  sleep 2
}
show() { head -c "${2:-700}" "$OUT/$1" 2>/dev/null | tr '\n' ' ' | sed 's/^/   /'; echo; }
names() { grep -oE "<(Name|Title)>[^<]*</(Name|Title)>" "$OUT/$1" 2>/dev/null | sed -E 's/<[^>]+>//g' | head -${2:-30} | tr '\n' '|' | sed 's/^/   /'; echo; }

echo "### 1. MIDAS: pola warstw i nasz moduł na punkcie"
get midas_1.json "https://cbdgmapa.pgi.gov.pl/arcgis/rest/services/midas/MapServer/1?f=json"
python3 -c "import json,sys; d=json.load(open('$OUT/midas_1.json')); print('   ', d.get('name'), '|', [f['name'] for f in d.get('fields', [])])" 2>/dev/null
get midas_2.json "https://cbdgmapa.pgi.gov.pl/arcgis/rest/services/midas/MapServer/2?f=json"
python3 -c "import json,sys; d=json.load(open('$OUT/midas_2.json')); print('   ', d.get('name'), '|', [f['name'] for f in d.get('fields', [])])" 2>/dev/null
echo "   rcn/grunt.py dla punktu (działka i górnictwo):"
python3 rcn/grunt.py "$N" "$E" | head -30 | sed 's/^/   /'

echo "### 2. MPZP: formaty i odpowiedź o punkt (GetFeatureInfo)"
MPZP="https://mapy.geoportal.gov.pl/wss/ext/KrajowaIntegracjaMiejscowychPlanowZagospodarowaniaPrzestrzennego"
get mpzp_caps.xml "$MPZP?SERVICE=WMS&REQUEST=GetCapabilities"
grep -oE "<Format>[^<]*</Format>" "$OUT/mpzp_caps.xml" | sort -u | tr '\n' ' ' | sed 's/^/   /'; echo
BB="$(python3 -c "print('%.2f,%.2f,%.2f,%.2f' % ($N-50, $E-50, $N+50, $E+50))")"
for fmt in text/html application/vnd.ogc.gml text/plain; do
  get "mpzp_gfi_${fmt//\//_}" "$MPZP?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo&LAYERS=plany,wektor-pow&QUERY_LAYERS=plany,wektor-pow&CRS=EPSG:2180&BBOX=$BB&WIDTH=101&HEIGHT=101&I=50&J=50&INFO_FORMAT=$fmt&STYLES="
  show "mpzp_gfi_${fmt//\//_}" 900
done

echo "### 4. Powódź (ISOK): strona mapy i odnośniki do usług"
get isok.html "https://wody.isok.gov.pl/imap_kzgw/"
grep -oiE "https?://[^\"' <>]*(wms|wfs|arcgis/rest|MapServer|wss)[^\"' <>]*" "$OUT/isok.html" | sort -u | head -15 | sed 's/^/   /'
grep -oiE "[\"'][^\"']*(MZP|MRP|zagrozeni|ryzyk)[^\"']*[\"']" "$OUT/isok.html" | sort -u | head -15 | sed 's/^/   /'

echo "### 5. Osuwiska (PIG geozagrożenia): usługi i warstwy"
get geozagrozenia.json "https://cbdgmapa.pgi.gov.pl/arcgis/rest/services/geozagrozenia?f=json"
python3 - "$OUT/geozagrozenia.json" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as exc:
    print("   brak JSON:", exc); sys.exit()
for s in d.get("services", []) + [{"name": f, "type": "folder"} for f in d.get("folders", [])]:
    print("   ", s.get("type"), s.get("name"))
PY
for svc in $(python3 -c "import json; d=json.load(open('$OUT/geozagrozenia.json')); print(' '.join(s['name'] for s in d.get('services',[]) if s.get('type')=='MapServer'))" 2>/dev/null | tr ' ' '\n' | head -4); do
  safe=$(echo "$svc" | tr '/' '_')
  get "gz_$safe.json" "https://cbdgmapa.pgi.gov.pl/arcgis/rest/services/$svc/MapServer?f=json"
  python3 -c "import json; d=json.load(open('$OUT/gz_$safe.json')); print('   ', '$svc', [(l['id'], l['name']) for l in d.get('layers', [])][:20])" 2>/dev/null
done

echo "### 6. Hałas: strona GDDKiA o mapach hałasu 2022 (odnośniki do usług)"
get halas_gddkia.html "https://www.gov.pl/web/gddkia/strategiczne-mapy-halasu-2022"
grep -oiE "https?://[^\"' <>]*(wms|wfs|arcgis|MapServer|geoportal|zip|shp|gpkg)[^\"' <>]*" "$OUT/halas_gddkia.html" | sort -u | head -12 | sed 's/^/   /'

echo "### 9. Jakość powietrza (GIOŚ): najbliższa stacja i indeks"
get gios_stacje.json "https://api.gios.gov.pl/pjp-api/v1/rest/station/findAll?size=500"
python3 - "$OUT/gios_stacje.json" "$LAT" "$LON" <<'PY'
import json, math, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as exc:
    print("   brak JSON:", exc); sys.exit()
rows = d if isinstance(d, list) else next((v for v in d.values() if isinstance(v, list)), [])
print("   klucze rekordu:", list(rows[0].keys()) if rows else "brak", "| rekordów:", len(rows), "| klucze odpowiedzi:", list(d)[:8] if isinstance(d, dict) else "lista")
lat0, lon0 = float(sys.argv[2]), float(sys.argv[3])
def num(r, *words):
    for k, v in r.items():
        if all(w in k.lower() for w in words):
            try:
                return float(str(v).replace(",", "."))
            except ValueError:
                pass
best = []
for r in rows:
    lat, lon = num(r, "φ") or num(r, "lat") or num(r, "n"), num(r, "λ") or num(r, "lon") or num(r, "e")
    if lat and lon:
        best.append((math.hypot((lat - lat0) * 111.2, (lon - lon0) * 71.2), r))
best.sort(key=lambda x: x[0])
for dist, r in best[:3]:
    print("   %.1f km" % dist, json.dumps(r, ensure_ascii=False)[:220])
PY

echo "### Gotowe. Proszę wkleić cały wynik. Pliki w $OUT/."
