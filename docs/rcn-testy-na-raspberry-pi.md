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

### Pierwszy wynik na prawdziwym wycinku (Raspberry Pi, 2026-10-28, kod `0b0182d`)

- Wycinek Geofabrik `slaskie-261027.osm.pbf`: 186 362 801 bajtów, pobranie 3 min 27 s. Po filtrze `osmium`: 6,2 MB PBF, 52 MB GeoJSON.
- Import: 82 798 obiektów zapisanych, 54 586 pominiętych (głównie słupy i węzły dołączone do linii), 0 błędnych.
- Raport dla ul. Braci Mniejszych, 3 km: linia 110 kV (Tauron, „Kopanina–Wirek, Brynów–Ligota") 1139 m, kolej 633 m, teren przemysłowy 226 m, oczyszczalnia ścieków Panewniki 2392 m, przedszkole 135 m, szkoła 83 m, przystanek 221 m („Kokociniec Płochy").

Znalezione problemy i poprawki (kod po `0b0182d`):

- Drogi w budowie i planowane to w większości chodniki (`footway`). Teraz liczą się tylko klasy `motorway`, `trunk`, `primary`, `secondary`, `tertiary` (z odmianami `_link`) oraz drogi bez podanej klasy.
- 94 „stacje energetyczne" to w większości małe stacje transformatorowe. Teraz tylko stacje z napięciem od 110 kV lub oznaczone `substation=transmission`.
- Liczniki dla linii i dróg liczyły odcinki w danych, a nie całe obiekty. Raport mówi teraz wprost „odcinków w danych". Przystanki liczone są wg różnych nazw (słupek i peron tego samego przystanku to jedna nazwa).
- Ponowny import czyści tabelę, żeby obiekty, które po zmianie reguł przestały się kwalifikować, nie zostały w bazie.

Do ponownego sprawdzenia przez użytkownika: czy najbliższe obiekty zgadzają się z tym, co zna z okolicy.

### Wynik po poprawkach (Raspberry Pi, 2026-10-28, kod `cfc4c43`)

- Import: 73 529 zapisanych (wcześniej 82 798), 63 855 pominiętych, 0 błędnych.
- Stacje energetyczne WN: najbliższa 1233 m („GPZ Ligota", 110/20 kV), 10 w promieniu 3 km (wcześniej 94 z kioskami transformatorowymi).
- Drogi w budowie: najbliższa 993 m (Kłodnicka, klasa `tertiary`), 3 odcinki. Planowane: 671 m, klasa `tertiary`, 15 odcinków. Chodniki zniknęły.
- Przystanki: 75 różnych nazw w promieniu 3 km.
- Bez zmian: linia 110 kV 1139 m, kolej 633 m, teren przemysłowy 226 m, maszt 198 m, przedszkole 135 m, szkoła 83 m.

Weryfikacja z wiedzą użytkownika o okolicy: jeszcze nie.

## Odczyt ogłoszenia z linku (pozycja 4a kolejki)

`rcn/oferta.py probe URL` pobiera jedną stronę ogłoszenia na żądanie użytkownika (bez przeszukiwania portalu), usuwa z adresu parametry reklamowe (`utm_*`, `gclid`, `gad_*`), zapisuje HTML w `ref/oferty/` (poza repozytorium) i wypisuje pola z danych strukturalnych: JSON-LD, `__NEXT_DATA__`, znaczniki `og:`. Nie wypisuje telefonów, e-maili, nazwisk ani adresów biur pośredników. Przy odmowie portalu (np. HTTP 403) kończy się bez ponawiania.

Pierwsze przypadki: ogłoszenie z Gratki przy ul. bp. Szurmana oraz ogłoszenie z Nieruchomosci-online.pl.

### Opis ogłoszenia przez defuddle (opcjonalnie)

defuddle czyta zapisany plik HTML (sprawdzone na wersji 0.19.6: usuwa menu i stopkę, zostawia treść ogłoszenia). Opis często zawiera telefon pośrednika, dlatego polecenie poniżej zastępuje numery telefonów i adresy e-mail znacznikami przed wyświetleniem.

```bash
node --version && (defuddle --version || sudo npm install -g defuddle)
```

```bash
cd /mnt/nas/projects/mieszkanie100 && for f in ref/oferty/*.html; do echo "== $f"; defuddle parse "$f" --md | sed -E 's/(\+?48[ -]?)?[0-9]{3}[ -]?[0-9]{3}[ -]?[0-9]{3}/[telefon]/g; s/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}/[email]/g' | head -60; done
```

### Wynik rozpoznania i karta mieszkania (2026-10-28)

Obie strony odpowiedziały HTTP 200. Nieruchomosci-online.pl ma pełne dane w JSON-LD (blok z ogłoszeniem, nie pierwszy blok, który jest adresem portalu w Olsztynie) i oznacza lokalizację jako przybliżoną. Gratka trzyma dane w `__NUXT_DATA__` w formacie devalue (liczby to odnośniki do innych pozycji tablicy). Na stronie Gratki jest też polecane drugie ogłoszenie, więc główne to pierwszy obiekt z metrażem, ceną i liczbą pokoi. Oba linki to to samo mieszkanie: 65,08 m², 4 pokoje, 839 000 zł, rok 2020, balkon około 7 m².

Karta mieszkania z zapisanych stron (bez ponownego pobierania):

```bash
cd /mnt/nas/projects/mieszkanie100 && python3 rcn/karta.py "https://gratka.pl/nieruchomosci/mieszkanie-katowice-ligota-biskupa-tadeusza-szurmana/ob/48453361" --file ref/oferty/gratka_pl_48453361.html
```

```bash
cd /mnt/nas/projects/mieszkanie100 && python3 rcn/karta.py "https://katowice.nieruchomosci-online.pl/mieszkanie,z-aneksem-kuchennym/26868680.html" --file ref/oferty/katowice_nieruchomosci-online_pl_26868680_html.html
```

### Pierwsze karty na prawdziwych stronach (Raspberry Pi, 2026-10-28, kod `6492a2c`)

Obie karty (Gratka i Nieruchomosci-online.pl, to samo mieszkanie) dały ten sam wynik porównania:

- Rynek wtórny, 500 m, 24 miesiące, lokale 46–85 m²: próbka 54, mediana 10 913 zł/m², typowy zakres 9 919–11 770 zł/m².
- Rynek pierwotny: próbka 9 (za mała), mediana 9 668 zł/m².
- Oferta 12 892 zł/m²: powyżej typowego zakresu, tańszych sprzedaży 88,9%.
- Najbliższe sprzedaże w tych samych budynkach są droższe niż mediana okolicy: Szurmana 18 (11 984 zł/m², 2025-10), Szurmana 10 (11 523, 2026-05), Książęca 22 (12 930 i 13 241, 2025-09 i 2026-07), Szurmana 2 (12 103, 2025-08). Promień 500 m miesza nowe osiedle ze starszą zabudową, co uzasadnia pozycję 3b (wiek budynku).

Błędy i poprawki:

- Gratka: wzmianki „ogród 72 m², taras 28 m²" pochodziły z ogłoszeń polecanych na tej samej stronie. Wzmianki są teraz brane tylko z opisu ogłoszenia, a gdy portal nie daje opisu, z całej strony z oznaczeniem „mniej pewne".
- Gratka: „brak miejscowości", bo lokalizacja jest listą miejsc. Teraz miasto i dzielnica są odczytywane z listy (pomijając województwo).

### OLX odmawia pobrania (2026-10-28)

`oferta.py probe` dla ogłoszenia z OLX dostał HTTP 403. Decyzja: nie obchodzimy blokady (np. podszywaniem się pod przeglądarkę). Są dwie drogi:

1. Strona zapisana w zwykłej przeglądarce (Ctrl+S, „Strona internetowa, tylko HTML") i skopiowana na Raspberry Pi do `ref/oferty/`. Potem rozpoznanie i karta z pliku, bez pobierania:

```bash
cd /mnt/nas/projects/mieszkanie100 && ls -l ref/oferty/
```

```bash
cd /mnt/nas/projects/mieszkanie100 && python3 rcn/oferta.py probe "https://www.olx.pl/d/oferta/3-pokoje-duze-okna-park-kosciuszki-CID3-ID1cOp4L.html" --file ref/oferty/olx.html
```

```bash
cd /mnt/nas/projects/mieszkanie100 && python3 rcn/karta.py "https://www.olx.pl/d/oferta/3-pokoje-duze-okna-park-kosciuszki-CID3-ID1cOp4L.html" --file ref/oferty/olx.html
```

2. Karta z danych wpisanych ręcznie. Położenie to środek ulicy wyliczony z rekordów RCN (przybliżenie, karta to zaznacza):

```bash
cd /mnt/nas/projects/mieszkanie100 && python3 rcn/karta.py --cena 839000 --metraz 65.08 --ulica "Szurmana"
```

## Ogłoszenia z OLX (pozycja 10a kolejki)

Jedno zapytanie testowe do wyszukiwania GraphQL OLX z Raspberry Pi (2026-10-28) zwróciło HTTP 200 i 986 ofert sprzedaży mieszkań w Katowicach (`city_id=7691`, `region_id=6`, kategoria 14), z dzielnicą, współrzędnymi i parametrami. Strony pojedynczych ogłoszeń OLX nadal zwracają 403. To nieoficjalny interfejs OLX: może zostać zmieniony lub zamknięty, a regulamin OLX może zabraniać automatycznego pobierania. Używamy go rzadko (zalecane raz dziennie), jedno zapytanie naraz, z przerwą 3 s, z uczciwym identyfikatorem i bez ponawiania po odmowie.

```bash
cd /mnt/nas/projects/mieszkanie100 && python3 rcn/olx.py szukaj --dzielnica "Ligota-Panewniki" --metraz-od 100
```

Karta dla oferty z OLX (z zapamiętanych wyników, bez pobierania strony ogłoszenia):

```bash
cd /mnt/nas/projects/mieszkanie100 && python3 rcn/karta.py "LINK_DO_OFERTY_OLX_Z_WYNIKU_SZUKANIA"
```

## Otodom (2026-10-28)

Odczyt ogłoszeń Otodom w `rcn/portale.py` napisany na podstawie pól używanych przez `ncola/otodom_scraper` (projekt dla Katowic i śląskiego, 2026-07): `props.pageProps.ad` w `__NEXT_DATA__`, w tym `target.Price`, `Price_per_m`, `Area`, `Rooms_num`, `Floor_no`, `Build_year`, `market`, ulica, dzielnica z `reverseGeocoding`, nazwa inwestycji `developmentTitle` i lista cech `Extras_types` (balkon, ogród, taras, garaż). Tamten projekt podszywa się pod przeglądarkę; my najpierw sprawdzamy, czy Otodom odpowiada na uczciwy identyfikator. Nie sprawdzone na prawdziwej stronie.

Jedno zapytanie testowe (strona wyników dla Katowic):

```bash
cd /mnt/nas/projects/mieszkanie100 && python3 rcn/oferta.py probe "https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/slaskie/katowice/katowice/katowice" | head -15
```

### Pierwsze uruchomienia na prawdziwych danych (Raspberry Pi, 2026-10-28)

- `rcn/olx.py szukaj --dzielnica "Ligota-Panewniki" --metraz-od 100` (kod `bb567e9`): pobrano 986 z 986 ofert (wszystkie strony bez odmowy), pasuje 1: „Ville Garden | mieszkanie 4-pok. | A.33", 110,72 m², 1 815 808 zł, 16 400 zł/m², rynek pierwotny, powyżej typowego zakresu, ale porównanie z rynkiem pierwotnym ma tylko 3 sprzedaże w promieniu 500 m (za mała próba). Drugie uruchomienie: nowych 0, więc zapamiętywanie działa.
- Wniosek: mieszkań od 100 m² w samej dzielnicy Ligota-Panewniki jest na OLX bardzo mało, a granice dzielnic OLX są umowne. Propozycja: filtr „w promieniu X km od ulicy" liczony ze współrzędnych ofert.
- `rcn/oferta.py probe` dla strony wyników Otodom dla Katowic (kod `fcb3a3d`): HTTP 200 z uczciwym identyfikatorem, `next_data=1`, `ld_json=2`, 3172 pola kandydujące. Otodom nie blokuje naszego narzędzia.

### Karta z linku Otodom i przeglądanie Otodom (2026-10-28)

Karta dla prawdziwego ogłoszenia Otodom (ul. Widok, Dąb, 72,67 m², 828 438 zł, 11 400 zł/m², rynek pierwotny, rok 2025) zadziałała: odczyt, porównanie z RCN (wtórny próbka 10, pierwotny próbka 2) i otoczenie (linia 110 kV 132 m, GPZ Dąb 107 m, teren przemysłowy 126 m, przystanek 161 m). Wzmianki pochodziły z całej strony, czyli opis i lista cech nie zostały znalezione w `props.pageProps.ad`; do sprawdzenia, gdzie Otodom je teraz trzyma.

Wyniki wyszukiwania Otodom (32 oferty na stronę) mają ulicę, dzielnicę, cenę, metraż, inwestycję, ale bez współrzędnych (`mapDetails.radius = 0`). `rcn/otodom.py szukaj` porównuje je z RCN od środka ulicy wyliczonego z rekordów RCN, z tą informacją przy każdej ofercie.

```bash
cd /mnt/nas/projects/mieszkanie100 && python3 rcn/otodom.py szukaj --dzielnica "Ligota-Panewniki" --metraz-od 100
```

### Wynik przeglądania Otodom i diagnoza wzmianek (2026-10-28, kod `41b7588`)

- `rcn/otodom.py szukaj --dzielnica "Ligota-Panewniki" --metraz-od 100`: Otodom ma 79 stron wyników dla Katowic (po 72 oferty), pobrano 10 najnowszych (727 ofert), pasuje 0. Poprawka: filtr metrażu przekazywany do Otodom w adresie (`areaMin`), a ostrzeżenie, gdy stron jest więcej niż `--max-stron`.
- Ogłoszenie z ul. Widok ma `ad.description` (3656 znaków) i `target.Extras_types = ['balcony', 'lift', 'garage', 'garden']`. Wzmianki były więc poprawne (z opisu i listy cech); błędny był tylko napis „z całej strony" w karcie. Poprawione.

### Powtórzone oferty i ta sama oferta na dwóch portalach (2026-10-28)

- Problem z Pi: Otodom pokazał tę samą ofertę dwa razy (promowana na górze i na liście), a mieszkanie z OLX było też na Otodom bez żadnej informacji.
- Poprawka: oferta o tym samym identyfikatorze wypisywana raz (`unique_by_id`); oferta podobna do zapamiętanej z innego portalu (metraż w granicach 0,5 m², cena w granicach 1%, ewentualnie odległość poniżej 500 m) ma dopisek „ta sama oferta także na: olx" (`also_on`).

## Wiek budynku z RCN: czy to działa (pozycja 3b kolejki, 2026-10-28)

Pomysł: identyfikator lokalu w RCN zawiera identyfikator budynku (`..._BUD.1_LOK`). Rejestr ma dane od 2012 r., więc:

- pierwsza sprzedaż w budynku to rynek pierwotny w roku 2016 lub później: budynek „do 10 lat (szacunek)", rok przybliżony, bo deweloper często sprzedaje przed oddaniem;
- pierwsza sprzedaż to rynek pierwotny w latach 2014–2015: „granica około 10 lat";
- pierwsza sprzedaż przed 2016 r. i nie z rynku pierwotnego: „ponad 10 lat" (budynek już stał);
- reszta: „nieznany", nigdy „stary" tylko dlatego, że brakuje danych.

Najpierw sprawdzenie na prawdziwej bazie, zanim filtr trafi do raportu okolicy i karty:

```bash
cd /mnt/nas/projects/mieszkanie100 && git pull && python3 rcn/wiek.py diag --db rcn_test.sqlite --ulica "Szurmana" --ulica "Braci Mniejszych"
```

Do oceny przez użytkownika: czy budynki przy Szurmana (Osiedle Franciszkańskie, budowane mniej więcej 2016–2020) dostały „do 10 lat" z sensownym rokiem, a starsze bloki „ponad 10 lat". Liczy się też udział rekordów z identyfikatorem budynku i liczba budynków „nieznany".

Drugie źródło: ewidencja budynków (EGiB) w Geoportalu. Sprawdzenie, czy warstwa budynków ma pole z rokiem budowy (z chmury Geoportal jest zablokowany, więc tylko z Pi):

```bash
curl -sS -m 60 "https://mapy.geoportal.gov.pl/wss/service/PZGIK/EGIB/WFS/UslugaZbiorcza?SERVICE=WFS&VERSION=2.0.0&REQUEST=DescribeFeatureType&TYPENAMES=ms:budynki" | grep -o 'name="[^"]*"' | head -60
```

### Wynik sprawdzenia wieku budynku (Raspberry Pi, 2026-10-28, kod `f7568c2`)

- Wszystkie 41 845 rekordów lokali mają identyfikator z częścią `_BUD.`, ale wyszło 33 312 „budynków", czyli prawie jeden budynek na sprzedaż. Przy Szurmana 10 jest 12 różnych identyfikatorów budynku. Grupowanie po identyfikatorze w obecnej postaci nie działa; przyczyna do sprawdzenia na surowych identyfikatorach.
- Tam, gdzie sprzedaż pierwotna jest, wynik pasuje do rzeczywistości: Szurmana 2–18 pierwsza sprzedaż pierwotna 2021 (Osiedle Franciszkańskie). Braci Mniejszych 1–7B prawie same sprzedaże wtórne od 2017–2019, więc „nieznany" (budynek stał już w 2017 r., ale nie wiadomo od kiedy).
- EGiB WFS `ms:budynki` ma tylko pola `geom`, `ID_BUDYNKU`, `RODZAJ`, `KONDYGNACJE_NADZIEMNE`, `KONDYGNACJE_PODZIEMNE`. Brak roku budowy, więc to źródło odpada.
- Przyczyna (surowe identyfikatory z Pi): dla Szurmana 10 wszystkie lokale mają tę samą działkę `246901_1.0003.AR_45.14/15.5`, a numer po `BUD.` jest różny dla każdego lokalu (`BUD.13` do `BUD.74`; ten sam `BUD.70` sprzedany trzy razy). To numer lokalu, nie budynku. Poprawka: budynek to działka (część przed `_BUD`) razem z adresem (ulica i numer); lokal bez adresu grupowany po samej działce.
- Rekord lokalu w RCN nie ma pola z rokiem budowy (pola: `DOK_*`, `LOK_*`, `NIER_*`, `TRAN_*`, `TERYT`, `SERWIS_RCN`).
