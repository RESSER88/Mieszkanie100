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

## Raspberry Pi: pobranie i aktualizacja kodu

Pierwsze podłączenie istniejącego folderu (który powstał z paczki `.tar.gz`) do repozytorium. Pliki kodu zostaną zastąpione wersją z GitHuba, a baza, pliki w `ref/` i logi zostaną (są w `.gitignore`):

```bash
cd /mnt/nas/projects/mieszkanie100 && git init -b main && git remote add origin https://github.com/RESSER88/Mieszkanie100.git && git fetch origin main && git checkout -f -B main origin/main
```

Każda kolejna aktualizacja:

```bash
cd /mnt/nas/projects/mieszkanie100 && git pull && bash scripts/pi_check.sh
```

`scripts/pi_check.sh` uruchamia testy jednostkowe, a jeśli w folderze jest `rcn_test.sqlite`, także raport bazy i raport okolicy. Inną bazę wskazuje zmienna `RCN_DB`.

## Mapa na Raspberry Pi

```bash
cd /mnt/nas/projects/mieszkanie100 && python3 rcn/mapa.py
```

Serwer wypisuje adres (np. `http://192.168.1.20:8100`). Otwórz go na telefonie lub komputerze w sieci domowej, wklej link do ogłoszenia albo wpisz ulicę, cenę i metraż. Zatrzymanie: Ctrl+C. Serwer nie ma logowania, więc działa tylko w sieci domowej (bez przekierowania portu w routerze). Pobiera wyłącznie strony z listy portali.

Kolejka prac i technologia: `docs/superpowers/plans/2026-10-28-kolejka-prac.md`.
