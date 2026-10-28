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
