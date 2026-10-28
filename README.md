# Mieszkanie100

Narzędzie pomagające ocenić ofertę mieszkania w Katowicach na tle rzeczywistych cen transakcyjnych z Rejestru Cen Nieruchomości (RCN). Na tym etapie jest gotowy importer cen (`rcn/rcn_import.py`). Importer nie był jeszcze uruchamiany na prawdziwej usłudze.

## Uruchomienie na Raspberry Pi

Wymagany jest Python 3.8 lub nowszy. Nie trzeba instalować żadnych pakietów.

Kod może leżeć na dysku sieciowym (np. `/mnt/nas/projects/mieszkanie100`), ale **bazę SQLite trzymaj na lokalnym dysku Raspberry Pi** (np. `~/rcn/rcn.sqlite`). SQLite na udziale sieciowym bywa zawodne i może uszkodzić bazę przy przerwanym zapisie.

```bash
cd /mnt/nas/projects/mieszkanie100
python3 -m unittest discover -s tests -v
mkdir -p ~/rcn
python3 rcn/rcn_import.py --teryt 2469 --layer lokale --db ~/rcn/rcn_test.sqlite --page-size 200 --max-pages 3
```

Dalsze kroki testowe: `docs/rcn-testy-na-raspberry-pi.md`. Projekt i uzasadnienie decyzji: `docs/superpowers/specs/2026-10-28-rcn-importer-design.md`.
