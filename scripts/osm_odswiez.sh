#!/usr/bin/env bash
# Odświeżenie bazy otoczenia z OpenStreetMap (śląskie) na Raspberry Pi, jednym poleceniem:
#   bash scripts/osm_odswiez.sh            # przefiltruj istniejący plik PBF i wczytaj bazę
#   bash scripts/osm_odswiez.sh --pobierz  # najpierw pobierz świeży plik PBF z Geofabrik (ok. 190 MB)
# Wczytanie ma zabezpieczenie: jeśli nowy plik ma mniej niż połowę obiektów bazy, baza zostaje bez zmian.
# Zatrzymaj wcześniej rcn/mapa.py (Ctrl+C), a po skrypcie uruchom go ponownie.
set -euo pipefail
cd "$(dirname "$0")/.."
DIR=ref/osm
PBF="$DIR/slaskie-latest.osm.pbf"
mkdir -p "$DIR"
if [ "${1:-}" = "--pobierz" ] || [ ! -f "$PBF" ]; then
  echo "== Pobieram $PBF (Geofabrik)"
  curl -sS -L -o "$PBF.tmp" "https://download.geofabrik.de/europe/poland/slaskie-latest.osm.pbf"
  mv "$PBF.tmp" "$PBF"
fi
command -v osmium >/dev/null || { echo "BŁĄD: brak osmium (sudo apt install osmium-tool)"; exit 2; }
echo "== Filtruję obiekty otoczenia (szkoły, przystanki, linie, kolej, tramwaje, drogi, lotniska, przemysł)"
osmium tags-filter "$PBF" \
  nwr/amenity=school,kindergarten n/highway=bus_stop n/railway=tram_stop nwr/public_transport=platform \
  w/highway=construction,proposed,motorway,trunk,primary,motorway_link,trunk_link,primary_link,secondary,secondary_link \
  w/railway=rail,tram nwr/aeroway=aerodrome nwr/power=line,substation nwr/man_made=mast,tower,wastewater_plant \
  nwr/landuse=industrial,landfill,quarry -o "$DIR/otoczenie-slask.osm.pbf" --overwrite
osmium export "$DIR/otoczenie-slask.osm.pbf" -f geojsonseq --add-unique-id=type_id \
  -o "$DIR/otoczenie-slask.geojsonseq" --overwrite
echo "== Wczytuję do osm_slask.sqlite"
python3 rcn/otoczenie.py import --geojsonseq "$DIR/otoczenie-slask.geojsonseq" --osm-db osm_slask.sqlite
echo "== Liczba obiektów wg rodzaju"
python3 -c "import sqlite3; [print('%-22s %d' % r) for r in sqlite3.connect('osm_slask.sqlite').execute('SELECT kategoria, COUNT(*) FROM osm_obiekty GROUP BY 1 ORDER BY 2 DESC')]"
echo "== Gotowe. Uruchom mapę: python3 rcn/mapa.py"
