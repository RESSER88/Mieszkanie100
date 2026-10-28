# Importer cen transakcyjnych RCN – projekt

Data: 2026-10-28. Status: wersja robocza do przeglądu. Importer przeszedł próbę na 3 stronach prawdziwej usługi (wynik w sekcji „Wyniki testów na prawdziwej usłudze"). Pełny import i kontrola kompletności nie zostały jeszcze wykonane.

## Cel

Pobierać rzeczywiste ceny sprzedanych nieruchomości z Rejestru Cen Nieruchomości (RCN) dla wybranego powiatu (TERYT), zapisywać je lokalnie i liczyć cenę za m². Dane mają wspierać ocenę ofert mieszkań w Katowicach (TERYT 2469): osiedle Franciszkańskie, okolice ul. Braci Mniejszych i ul. bp. Szurmana. Importer ma działać na Raspberry Pi (później w Dockerze, cyklicznie).

## Poza zakresem tego etapu

- Kryterium wieku budynku (do 10 lat). Warstwa `ms:lokale` nie ma roku budowy.
- Monitorowanie ogłoszeń, szkoły, komunikacja, planowane inwestycje.
- Harmonogram i Docker.
- Eksport XLSX.

## Ustalenia z testów na Raspberry Pi (2026-10-28)

Potwierdzone ręcznie przez użytkownika:

- Usługa WFS `https://mapy.geoportal.gov.pl/wss/service/rcn` odpowiada z Raspberry Pi. Warstwy: `ms:lokale`, `ms:budynki`, `ms:dzialki`, `ms:powiaty`.
- Filtr FES `PropertyIsEqualTo` na `TERYT` działa. `sortBy=DOK_DATA D` i `sortBy=gid A` działają.
- `numberMatched` ma wartość `unknown`. Liczby rekordów nie da się odczytać z serwera.
- `count=3` zwróciło 2 rekordy. Strona krótsza niż `count` nie oznacza końca danych.
- Sortowanie tylko po `DOK_DATA` z `startIndex` dało powtórzone `gid` między stronami.
- Sortowanie po `gid` z `startIndex` 0 i 10 nie dało powtórzeń w próbce 20 rekordów.

Z jednego surowego rekordu `ms:lokale`:

- Współrzędne punktu są w EPSG:2180 w kolejności północ, wschód (`262221.99 494414.00`).
- `TRAN_LOKALNY_ID_IIP` i `LOK_ID_LOKALU` to stabilne identyfikatory ewidencyjne. `gid` może nie być trwały.
- `TRAN_WERSJA_ID` oznacza, że transakcja może mieć kilka wersji.
- `DOK_DATA` to data dokumentu (aktu), nie dowiedziona data zawarcia transakcji.
- Brakujące wartości występują jako puste elementy (`<ms:LOK_POW_PRZYN></ms:LOK_POW_PRZYN>`).
- Adres ma postać `MSC:Katowice;UL:ul. Łąkowa;NR_PORZ:7`.

Nie potwierdzono: kompletności pobierania, stabilności `gid`, limitów serwera, adresów plików GeoPackage/GeoParquet (adres złożony z kodu wtyczki GUGiK: `https://opendata.geoportal.gov.pl/InneDane/latest_exports/rcn_transakcje_ceny/GPKG/2469_transakcje_ceny.gpkg.zip`).

## Rozważone podejścia

- A. Tylko WFS ze stronicowaniem kluczem `gid`. Dane aktualne, pasuje do zapytań o jeden punkt. Kompletności nie da się sprawdzić z samego serwera.
- B. Tylko plik GeoPackage dla powiatu. Kompletny, łatwy do zliczenia. Adres pliku i częstotliwość odświeżania są niepotwierdzone.
- C. Hybryda: pełny import z pliku, uzupełnianie przez WFS. Najlepsza jakościowo, dwa kody do utrzymania.

Rekomendacja: C. Wybór użytkownika czeka na wynik sprawdzenia adresu pliku (`curl -I`). Do tego czasu budujemy A, bo działa niezależnie od pliku i będzie potrzebne w C jako uzupełnianie. Porównanie z plikiem trafi do raportu jako opcja `--expect-count`.

## Decyzje projektowe importera (podejście A)

1. Stronicowanie kluczem. Każde zapytanie ma filtr `TERYT = X AND gid > ostatni_gid` oraz `sortBy=gid A`. Brak zależności od `startIndex`, więc nowe rekordy w trakcie pobierania nie przesuwają stron.
2. Koniec danych oznacza dopiero pusta strona. Strona krótsza niż `count` nie kończy pobierania.
3. Zapis i checkpoint w jednej transakcji SQLite. Przerwanie w dowolnym momencie nie psuje bazy, a wznowienie startuje od zapisanego `last_gid`.
4. Deduplikacja po kluczu głównym `gid` (zapis idempotentny). Dodatkowo raport liczy powtórzenia klucza naturalnego (`TRAN_LOKALNY_ID_IIP` plus identyfikator obiektu) jako sygnał wielu wersji transakcji. Nie usuwamy ich automatycznie.
5. Ponawianie żądań z rosnącym opóźnieniem. Odpowiedź HTTP 200 z `ExceptionReport` MapServera jest traktowana jak błąd.
6. Cena za m² tylko gdy cena transakcji, cena nieruchomości i cena obiektu są równe, cena i powierzchnia są dodatnie. Inaczej transakcja mogła obejmować kilka obiektów i pole zostaje puste.
7. Pełny rekord zapisujemy jako JSON (`raw_json`), a wybrane pola także jako kolumny. Schemat WFS może się zmienić (usługa jest tymczasowa), więc nic nie ginie.
8. Pola kupującego i sprzedającego nie trafiają do kolumn. Zostają tylko w `raw_json`, bo analiza ich nie wymaga.
9. Raport kończy się zawsze linią o statusie kompletności. Bez `--expect-count` status brzmi `NIEZWERYFIKOWANA`.

## Wyniki testów na prawdziwej usłudze

Raspberry Pi, 2026-10-28, `--teryt 2469 --layer lokale --page-size 200 --max-pages 3`:

- 15 testów jednostkowych przeszło także na Raspberry Pi (13,8 s).
- Stronicowanie `TERYT = 2469 AND gid > N` z `sortBy=gid A` działa: 3 strony po 200 rekordów, `last_gid` rosnące (47948939, 47949139, 47949339), bez błędów i bez ponowień. Ryzyko z sekcji „Ryzyka" (serwer nie obsługuje filtra `gid`) nie wystąpiło.
- Raport z 600 rekordów: zakres dat 2013-02-19 .. 2016-04-01 (rekordy rosnąco wg `gid` są też z grubsza rosnące wg daty), bez powierzchni 0, bez ceny obiektu 135 (22,5%), cena za m² policzona dla 445, powtórzonych kluczy naturalnych 0.
- Status kompletności: `NIEZWERYFIKOWANA`, zgodnie z założeniem.

Pełny import lokali, Raspberry Pi, 2026-10-28, `--teryt 2469 --layer lokale --page-size 200`:

- Przerwanie (Ctrl+C) i wznowienie działają: po przerwaniu pierwsza strona kończyła się na `last_gid` większym o 200 od zapisanego checkpointu. Przerwany przez `SIGINT` import kończy się kodem 130 z zapisanym checkpointem.
- Przez pomyłkę działały chwilowo dwa importy naraz na tej samej bazie. Oba zatrzymano. Zapis po `gid` jest idempotentny, więc dane nie ucierpiały, ale licznik stron w checkpoincie (`stron=210`) jest zawyżony i nie oznacza liczby unikalnych stron.
- Import zakończył się sam. Baza: 41 845 rekordów lokali, `last_gid=47990586`.
- Zakres dat 2012-08-23 .. 2026-09-14. Rozkład wg roku: 2012: 367, 2013: 982, 2014: 1090, 2015: 1149, 2016: 1294, 2017: 1571, 2018: 1792, 2019: 1770, 2020: 1548, 2021: 5409, 2022: 4611, 2023: 5243, 2024: 6740, 2025: 4698, 2026: 3581.
- Bez ceny obiektu: 4476 (10,7%). Bez powierzchni: 1. Cena za m² policzona dla 29 492 (70,5%). Pozostałe nie mają ceny lub powierzchni albo ceny transakcji, nieruchomości i lokalu się różnią (transakcje pakietowe). Podział tych przyczyn nie został jeszcze zmierzony.
- Powtórzone klucze naturalne (wiele wersji transakcji): 7.
- Status kompletności: `NIEZWERYFIKOWANA`.

Obserwacje do wyjaśnienia:

- Skok liczby rekordów z 1548 (2020) do 5409 (2021). Może odzwierciedlać rynek albo zmianę zakresu lub sposobu wprowadzania danych do rejestru. Nie wiadomo, bez sprawdzenia rozkładu miesięcznego.
- Migawka deweloperuch (2157 transakcji, 2338 lokali, wrzesień 2024 – wrzesień 2025) ma wyraźnie mniej lokali niż WFS w podobnym okresie (2024: 6740, 2025: 4698 rekordów w całych latach). Migawka jest więc najpewniej niepełna i nie nadaje się jako liczba referencyjna dla kompletności. Dokładne porównanie wymaga zliczenia WFS w tym samym oknie dat.

Otwarte pytania:

- Niezależne źródło liczby referencyjnej (plik GeoPackage dla powiatu 2469). Adres pliku (`curl -I`) nadal niesprawdzony.
- Test warstw `budynki` i `dzialki` (identyfikatory obiektów zgadnięte).

## Test akceptacyjny

Na Raspberry Pi: `python3 rcn/rcn_import.py --teryt 2469 --layer lokale --db rcn.sqlite`, przerwanie Ctrl+C w środku, ponowne uruchomienie, porównanie liczby rekordów z migawką deweloperuch (2157 transakcji, wrzesień 2024 – wrzesień 2025) w tym samym zakresie dat.

## Ryzyka

- Serwer może nie obsługiwać `And` z `PropertyIsGreaterThan` na `gid`. Importer rozpoznaje to przy pierwszym zapytaniu (błąd lub niemonotoniczne `gid`) i kończy z jasnym komunikatem.
- Limity i warunki użytkowania usługi są nieznane. Domyślnie 1 zapytanie naraz i krótka przerwa między stronami.
