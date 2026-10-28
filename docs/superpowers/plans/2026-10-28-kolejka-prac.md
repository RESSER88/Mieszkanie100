# Mieszkanie100: kolejka prac

> **Dla wykonawców:** każda pozycja kolejki dostaje własny szczegółowy plan w `docs/superpowers/plans/`, zanim zacznie się kod (superpowers:writing-plans), a wykonanie idzie przez superpowers:executing-plans lub superpowers:subagent-driven-development. Pola wyboru (`- [ ]`) służą do śledzenia.

**Cel:** wklejam link do ogłoszenia (albo wpisuję adres, cenę i metraż), a na mapie widzę ofertę, ceny sprzedanych mieszkań w okolicy oraz wiedzę o lokalizacji: uciążliwości, drogi w budowie, przedszkola, szkoły, przystanki, teren i bezpieczeństwo.

**Dokumenty:** efekt końcowy `docs/superpowers/specs/2026-10-28-mieszkanie100-vision.md`, roadmapa ze źródłami danych `docs/superpowers/plans/2026-10-28-mieszkanie100-roadmap.md`, importer `docs/superpowers/specs/2026-10-28-rcn-importer-design.md`.

Ustalona kolejność: 2026-10-28, zaakceptowana przez użytkownika jako spójna z jego celami. Zmiana kolejności tylko na prośbę użytkownika.

## Technologia (propozycja, do potwierdzenia)

| Warstwa | Wybór | Dlaczego |
|---|---|---|
| Język | Python 3.8+ (na Raspberry Pi jest 3.13), tylko biblioteka standardowa | Działa od razu po `git pull`, bez instalowania pakietów. |
| Dane | SQLite (ceny RCN, oferty, bufor wyników), GeoJSON (obiekty z OSM) | Jeden plik na zbiór danych, kopia zapasowa to kopia pliku. |
| Przetwarzanie OSM | `osmium-tool` z pakietów systemowych (`apt`) | Szybko filtruje plik PBF do GeoJSON. Python czyta tylko wynik. |
| Strona | Serwer HTTP z biblioteki standardowej Pythona: odpowiedzi JSON plus jedna strona HTML z JavaScriptem | Zero zależności. Telefon otwiera adres Raspberry Pi w sieci domowej. |
| Mapa | Leaflet 1.9.4 z unpkg (stała wersja, skrót integralności) i kafelki rastrowe OpenStreetMap z podpisem źródła (decyzja 2026-10-28) | Bez tokenu i konta. MapLibre GL JS wymaga dostawcy kafelków wektorowych, więc odłożona; Mapbox GL JS po sprawdzeniu limitów. Kafelki OSM tylko do podglądu przez jedną osobę, bez pobierania na zapas. |
| Uruchamianie | Najpierw ręcznie z terminala, potem usługa `systemd`, Docker na końcu (etap 6) | Najmniej elementów na początku. |
| Testy | `unittest` i `scripts/pi_check.sh` | Te same testy w chmurze i na Raspberry Pi. |
| Czytanie opisu ogłoszenia | defuddle (Node.js, `npm install -g defuddle`), opcjonalnie | Wyciąga czytelną treść z zapisanej strony bez menu i reklam. Jeśli go nie ma, kod używa prostego wyciągania tekstu z HTML. To jedyna zależność spoza Pythona i pakietów systemowych. |

Rozważone dla strony: Flask lub FastAPI (wygodniejsze, ale wymagają środowiska `venv` i pakietów) oraz statyczny plik HTML generowany poleceniem (najprostszy, ale nie pozwala wkleić linku i dostać odpowiedzi). Zalecenie: serwer z biblioteki standardowej, bo działa bez instalacji i wystarcza dla jednego użytkownika w sieci domowej.

## Zasada „repozytorium zawsze gotowe do testów na Raspberry Pi"

- Gałąź `main` zawsze przechodzi `python3 -m unittest discover -s tests`. Nic nie trafia na GitHub bez przejścia testów.
- Po każdym `git pull` na Raspberry Pi wystarcza `bash scripts/pi_check.sh`: testy jednostkowe, raport bazy, wartości `rodzaj_rynku`, raport okolicy dla ul. Braci Mniejszych.
- Dane (bazy SQLite, pliki GeoPackage, PBF, logi) nie trafiają do repozytorium (`.gitignore`).
- Każda nowa funkcja dopisuje swój krok do `scripts/pi_check.sh` i do `docs/rcn-testy-na-raspberry-pi.md`.

## Kolejka

| Nr | Praca | Stan | Zależy od |
|---|---|---|---|
| 0 | Importer cen RCN dla Katowic, zapytanie okolicy (kod) | Zrobione | |
| 1 | Repozytorium gotowe do testów na Raspberry Pi: skrypt `scripts/pi_check.sh`, instrukcja pierwszego pobrania i aktualizacji w `README.md` | Zrobione 2026-10-28 | 0 |
| 2 | Test okolicy na prawdziwej bazie, sprawdzenie wartości `rodzaj_rynku`, wyjaśnienie 2 rekordów różniących WFS i GeoPackage | Zrobione 2026-10-28: raport wiarygodny po odfiltrowaniu garaży, udziałów i sprzedaży poza wolnym rynkiem. Otwarte: 2 rekordy różniące WFS i GeoPackage (niski priorytet). | 1 |
| 3 | OSM dla śląskiego: pobranie PBF, `osmium` do GeoJSON (linie energetyczne z napięciem, stacje, maszty, kolej, drogi główne, przemysł, drogi w budowie i planowane, przedszkola, szkoły, przystanki), moduł `rcn/otoczenie.py` (najbliższe obiekty wg rodzaju) | Zrobione 2026-10-28: wycinek śląskiego na Raspberry Pi, 73 529 obiektów, raport dla ul. Braci Mniejszych po poprawkach (chodniki, kioski, liczniki). Otwarte: weryfikacja z wiedzą użytkownika. | 1 |
| 3b | Przybliżony wiek budynku z RCN: identyfikator budynku z `LOK_ID_LOKALU`, data pierwszej sprzedaży z rynku pierwotnego (od 2012 r.), filtr „budynek do 10 lat" w raporcie okolicy. Budynki bez sprzedaży pierwotnej od 2012 r. mają wiek „nieznany". | Wykonalność sprawdzona na Pi 2026-10-28 (`rcn/wiek.py diag`, budynek = działka + adres): działa dla budynków ze sprzedażą pierwotną; dla samych wtórnych tylko „stał już w roku X”. Następnie: filtr w raporcie okolicy i wiek budynku w karcie | 2 |
| 4a | Odczyt ogłoszenia z linku, krok rozpoznawczy: `rcn/oferta.py probe URL` na Raspberry Pi pobiera jedną stronę na żądanie, zapisuje ją w `ref/oferty/` i wypisuje dane strukturalne bez kontaktów. Pierwsze portale (wybór użytkownika 2026-10-28): Gratka i Nieruchomosci-online.pl. Przypadek testowy: ogłoszenie przy ul. bp. Szurmana. | Zrobione 2026-10-28: obie strony pobrane na Raspberry Pi (HTTP 200), dane strukturalne odczytane. Oba ogłoszenia to to samo mieszkanie (65,08 m², 839 000 zł). | 3 |
| 4b | Odczyt dla Gratki i Nieruchomosci-online.pl na podstawie wyniku 4a (cena, metraż, pokoje, piętro, rok budowy, rynek, adres, współrzędne), z testami na zapisanych polach | Kod gotowy 2026-10-28: `rcn/portale.py` (Gratka przez rozwinięcie `__NUXT_DATA__`, Nieruchomosci-online.pl przez JSON-LD, inne portale przez ogólny JSON-LD), wzmianki z treści bez zapisu tekstu, rozpoznanie tej samej oferty z dwóch portali, oraz karta w terminalu `rcn/karta.py`. Na razie tekst strony czyta prosty parser HTML; defuddle zostaje opcją (na Nieruchomosci-online.pl zwrócił głównie menu i dane pośrednika). Czeka na sprawdzenie na Raspberry Pi. | 4a |
| 4 | Mapa, pierwsza wersja (zmiana 2026-10-28: wejściem jest link do ogłoszenia, formularz tylko jako zapas): serwer na Raspberry Pi, formularz (ulica lub adres, cena, metraż), mapa z ofertą, transakcjami w promieniu i obiektami z OSM, karta z oceną ceny | Pierwsza wersja 2026-10-28: `rcn/mapa.py` (serwer z biblioteki standardowej, port 8100), wklejenie linku lub wpis ręczny, mapa z ofertą, sprzedażami RCN w promieniu (kolor wg ceny, obwódka dla budynków do 10 lat) i obiektami OSM (warstwy do włączania), karta pod mapą. Sprawdzona w przeglądarce w chmurze na danych testowych; czeka na Raspberry Pi | 2, 3 |
| 5 | Wklejanie linku: jeden portal (wybiera użytkownik), odczyt jednej oferty na żądanie, ustalenie położenia oferty, formularz jako zapas | Do zrobienia | 4 |
| 6 | Kolejne powiaty śląskiego: 7 sąsiednich (2470, 2474, 2463, 2477, 2475, 2472, 2408) | Do zrobienia | 2 |
| 7 | Rozpoznanie źródeł oficjalnych, każde z wnioskiem w `docs/`: PSE, GDDKiA, KMZB, NMT GUGiK, mScanner `mode=asking`, regulamin pierwszego portalu | PSE i GDDKiA rozpoznane wstępnie 2026-10-28 (`docs/superpowers/specs/2026-10-28-zrodla-pse-gddkia.md`): brak znanej usługi z geometrią, na razie OSM; rozpoznanie na Pi `bash scripts/zrodla_probe.sh`. Pozostałe (KMZB, NMT, mScanner, regulamin portalu) do zrobienia | |
| 8 | Teren na karcie (wysokość, nachylenie) | Do zrobienia | 4, 7 |
| 9 | Bezpieczeństwo na karcie (KMZB), jeśli rozpoznanie pozwoli | Do zrobienia | 4, 7 |
| 10a | Ogłoszenia OLX dla Katowic: `rcn/olx.py szukaj` (wyszukiwanie GraphQL OLX, które 2026-10-28 odpowiedziało HTTP 200 na nasz uczciwy identyfikator: 986 ofert sprzedaży), filtr dzielnicy, metrażu, ceny i rynku, zapamiętywanie nowych ofert, porównanie każdej z RCN, karta z linku OLX z zapamiętanych wyników | Kod gotowy (14 testów), czeka na pierwsze uruchomienie na Raspberry Pi | 4b |
| 10b | Ogłoszenia Otodom dla Katowic: `rcn/otodom.py szukaj` (strony wyników, 2026-10-28 HTTP 200 dla uczciwego identyfikatora), rozwijanie lokali z inwestycji deweloperów, porównanie z RCN po środku ulicy (wyniki nie mają współrzędnych), pełna karta z linku Otodom działa na prawdziwym ogłoszeniu | Kod gotowy (9 testów), czeka na pierwsze uruchomienie na Raspberry Pi | 4b |
| 10 | Przeglądanie inwestycji deweloperów i ogłoszeń z rynku wtórnego dla wybranych okolic (życzenie użytkownika 2026-10-28), kolejne portale, monitor ofert (alerty e-mail), przegląd okolic, Docker, uruchamianie cykliczne, powiadomienia | Później | 5 |

Pozycje 6 i 7 mogą iść równolegle z 3–5, bo nie zmieniają tego samego kodu.

## Pozycja 1: szczegóły (wykonane)

**Pliki:** `scripts/pi_check.sh` (nowy), `README.md` (sekcja o Raspberry Pi).

- [x] Skrypt uruchamia testy jednostkowe i kończy się błędem, gdy któryś nie przejdzie (`set -euo pipefail`).
- [x] Bez bazy skrypt mówi „Brak bazy … pomijam" i kończy się kodem 0.
- [x] Z bazą (domyślnie `rcn_test.sqlite`, albo zmienna `RCN_DB`) skrypt pokazuje raport importu, rozkład `rodzaj_rynku` i raport okolicy.
- [x] Sprawdzone w chmurze w obu wariantach (bez bazy i z bazą testową), 37 testów przechodzi.
- [x] Instrukcja w `README.md`: pierwsze podłączenie istniejącego folderu na Raspberry Pi do repozytorium, aktualizacja i uruchomienie skryptu.

## Przegląd uwag

- Folder na Raspberry Pi (`/mnt/nas/projects/mieszkanie100`) powstał z paczki, a nie z `git clone`. Podłączenie do repozytorium nadpisuje pliki śledzone przez git, ale nie rusza bazy, plików w `ref/` ani logów (są w `.gitignore`).
- Jeśli repozytorium na GitHubie jest prywatne, `git fetch` na Raspberry Pi poprosi o logowanie. Potrzebny jest wtedy token GitHub lub `gh auth login`, ustawiony przez użytkownika, nigdy wklejany do czatu.
- Długie importy (pozycja 6) uruchamiamy w tle przez `nohup` i zawsze jako jeden proces na bazę.
