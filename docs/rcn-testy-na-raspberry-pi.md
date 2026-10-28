# Testy importera RCN na Raspberry Pi

Importer przeszedł 15 testów automatycznych na atrapie serwera WFS (2026-10-28, środowisko chmurowe) i te same 15 testów na Raspberry Pi. Krok 0 i krok 1 zostały wykonane na Raspberry Pi i dały wynik pozytywny (szczegóły w projekcie, sekcja „Wyniki testów na prawdziwej usłudze"). Kroki 2–4 czekają na wykonanie. Przed uznaniem importera za działający trzeba wykonać wszystkie.

Wymagany jest Python 3.8 lub nowszy. Nie trzeba instalować żadnych pakietów.

## Krok 0. Testy jednostkowe

```bash
python3 -m unittest discover -s tests -v
```

Oczekiwany wynik: `OK`, 15 testów.

## Krok 1. Próba na 3 stronach

```bash
python3 rcn/rcn_import.py --teryt 2469 --layer lokale --db rcn_test.sqlite --page-size 200 --max-pages 3
```

Do sprawdzenia:

- Czy nie ma komunikatu `serwer nie respektuje filtra gid`. Gdyby był, serwer nie obsługuje filtra `gid > N` razem z `TERYT`, a podejście ze stronicowaniem kluczem trzeba zmienić (decyzja nr 1 w projekcie).
- Czy w raporcie `rekordów w bazie` jest równe sumie pobranych stron.
- Czy `zakres dat` zaczyna się od najstarszych dat (sortowanie po `gid` rosnąco).

## Krok 2. Przerwanie i wznowienie

```bash
python3 rcn/rcn_import.py --teryt 2469 --layer lokale --db rcn_test.sqlite --page-size 200
```

Po kilkunastu sekundach przerwać klawiszami Ctrl+C, potem uruchomić to samo polecenie jeszcze raz. Oczekiwane: komunikat o zapisanym checkpoincie, a przy wznowieniu pierwsza strona zaczyna od ostatniego `last_gid`.

## Krok 3. Pełny import i kontrola kompletności

Po zakończeniu importu porównać `rekordów w bazie` z niezależną liczbą:

- liczba rekordów z tego samego okresu w migawce deweloperuch (`data/katowice/katowice_rcn.gml`: 2157 transakcji, wrzesień 2024 – wrzesień 2025) albo
- liczba rekordów z oficjalnego pliku GeoPackage dla powiatu 2469, jeśli adres pliku okaże się poprawny.

```bash
python3 rcn/rcn_import.py --teryt 2469 --layer lokale --db rcn_test.sqlite --report-only --expect-count LICZBA
```

Status `ZGODNA` pojawi się tylko przy zgodnej liczbie. Inaczej raport mówi `NIEZGODNA` lub `NIEZWERYFIKOWANA`. Liczby z migawki obejmują wszystkie typy nieruchomości i inny okres, więc porównanie trzeba robić po zawężeniu zakresu dat.

## Krok 4. Budynki i działki

Powtórzyć kroki 1–3 z `--layer budynki`, potem `--layer dzialki`. Nazwy pól identyfikatorów obiektów (`BUD_ID_BUDYNKU`, `DZI_ID_DZIALKI`) są domysłem. Sprawdzić w bazie, czy kolumna `obj_id` nie jest pusta:

```bash
sqlite3 rcn_test.sqlite "SELECT COUNT(*), SUM(obj_id IS NULL) FROM budynki;"
```

## Co zgłosić z powrotem

Wynik kroku 1 (cały tekst), raport z kroku 3 i ewentualne komunikaty `BŁĄD`.

## Test zapytania „okolica" (etap 2)

Zapytanie `rcn/okolica.py` przeszło 22 testy na danych sztucznych. Na prawdziwej bazie nie było jeszcze uruchamiane.

Najpierw sprawdzić, jakie wartości ma pole `rodzaj_rynku` w prawdziwych danych, bo raport rozdziela rynek wtórny (`rynekWtorny`) i pierwotny (`rynekPierwotny`), a druga nazwa jest założeniem:

```bash
sqlite3 /mnt/nas/projects/mieszkanie100/rcn_test.sqlite "SELECT rodzaj_rynku, COUNT(*) FROM lokale GROUP BY 1;"
```

Potem uruchomić raport dla okolicy ul. Braci Mniejszych:

```bash
cd /mnt/nas/projects/mieszkanie100 && python3 rcn/okolica.py --db rcn_test.sqlite --street "Braci Mniejszych" --radius 500 --months 24
```

Do sprawdzenia: czy ulica została znaleziona, ile rekordów ma środek okolicy, czy próbki mają sens (kilkadziesiąt transakcji, nie 0 ani 5000) i czy mediana zł/m² jest wiarygodna dla tej okolicy. Wynik wkleić do dokumentu projektowego.

## Otoczenie z OpenStreetMap (pozycja 3 kolejki)

Moduł `rcn/otoczenie.py` przeszedł 17 testów na danych sztucznych (w tym przeliczanie współrzędnych na EPSG:2180 zgodne z pyproj co do 5 cm). Na prawdziwym wycinku OSM nie był jeszcze uruchamiany.

1. Instalacja narzędzia `osmium` (jednorazowo, wymaga hasła `sudo`):

```bash
sudo apt update && sudo apt install -y osmium-tool
```

2. Pobranie wycinku województwa śląskiego z Geofabrik (według opisu około 177 MB, rozmiar niezweryfikowany). Odświeżać rzadko, np. raz w miesiącu:

```bash
mkdir -p /mnt/nas/projects/mieszkanie100/ref/osm && cd /mnt/nas/projects/mieszkanie100/ref/osm && wget -O slaskie-latest.osm.pbf https://download.geofabrik.de/europe/poland/slaskie-latest.osm.pbf && ls -l
```

3. Wyfiltrowanie potrzebnych obiektów i zapis do GeoJSON:

```bash
cd /mnt/nas/projects/mieszkanie100/ref/osm && osmium tags-filter slaskie-latest.osm.pbf nwr/amenity=school,kindergarten n/highway=bus_stop n/railway=tram_stop nwr/public_transport=platform w/highway=construction,proposed,motorway,trunk,primary,motorway_link,trunk_link,primary_link w/railway=rail nwr/power=line,substation nwr/man_made=mast,tower,wastewater_plant nwr/landuse=industrial,landfill,quarry -o otoczenie-slask.osm.pbf --overwrite && osmium export otoczenie-slask.osm.pbf -f geojsonseq --add-unique-id=type_id -o otoczenie-slask.geojsonseq --overwrite && ls -l
```

4. Wczytanie do bazy i raport dla ul. Braci Mniejszych w promieniu 3 km:

```bash
cd /mnt/nas/projects/mieszkanie100 && python3 rcn/otoczenie.py import --geojsonseq ref/osm/otoczenie-slask.geojsonseq --osm-db osm_slask.sqlite && python3 rcn/otoczenie.py near --osm-db osm_slask.sqlite --rcn-db rcn_test.sqlite --street "Braci Mniejszych" --radius 3000
```

Do sprawdzenia: ile obiektów zapisano, ile błędnych, czy najbliższe przedszkola, szkoły, przystanki i linie energetyczne zgadzają się z tym, co użytkownik zna z okolicy.
