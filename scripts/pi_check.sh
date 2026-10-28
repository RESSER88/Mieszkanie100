#!/usr/bin/env bash
# Run on the Raspberry Pi after "git pull": unit tests, then a smoke run on the real database if it exists.
# Usage: bash scripts/pi_check.sh            (database: rcn_test.sqlite in the repository folder)
#        RCN_DB=/path/to/db.sqlite bash scripts/pi_check.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Wersja kodu: $(git rev-parse --short HEAD 2>/dev/null || echo 'brak git')"
echo "== Python: $(python3 --version)"
echo "== Testy jednostkowe"
python3 -m unittest discover -s tests

DB="${RCN_DB:-rcn_test.sqlite}"
if [ ! -f "$DB" ]; then
  echo "== Brak bazy $DB: pomijam test na prawdziwych danych."
  exit 0
fi

echo "== Raport importu ($DB)"
python3 rcn/rcn_import.py --teryt 2469 --layer lokale --db "$DB" --report-only
echo "== Wartości rodzaj_rynku"
python3 - "$DB" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
for value, n in con.execute("SELECT rodzaj_rynku, COUNT(*) FROM lokale GROUP BY 1 ORDER BY 2 DESC"):
    print("%-20s %d" % (value, n))
PY
echo "== Okolica: ul. Braci Mniejszych, 500 m, 24 miesiące"
python3 rcn/okolica.py --db "$DB" --street "Braci Mniejszych" --radius 500 --months 24
echo "== Gotowe"
