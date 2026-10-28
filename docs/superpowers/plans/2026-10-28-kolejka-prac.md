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
| Mapa | MapLibre GL JS ładowana w przeglądarce telefonu | Darmowa. Mapbox GL JS jako alternatywa po sprawdzeniu limitów. Dostawca kafelków do wyboru (publiczne kafelki OSM mają zasady korzystania). |
| Uruchamianie | Najpierw ręcznie z terminala, potem usługa `systemd`, Docker na końcu (etap 6) | Najmniej elementów na początku. |
| Testy | `unittest` i `scripts/pi_check.sh` | Te same testy w chmurze i na Raspberry Pi. |

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
| 3 | OSM dla śląskiego: pobranie PBF, `osmium` do GeoJSON (linie energetyczne z napięciem, stacje, maszty, kolej, drogi główne, przemysł, drogi w budowie i planowane, przedszkola, szkoły, przystanki), moduł `rcn/otoczenie.py` (najbliższe obiekty wg rodzaju) | Kod gotowy 2026-10-28 (17 testów). Czeka na wycinek OSM i raport z Raspberry Pi. | 1 |
| 3b | Przybliżony wiek budynku z RCN: identyfikator budynku z `LOK_ID_LOKALU`, data pierwszej sprzedaży z rynku pierwotnego (od 2012 r.), filtr „budynek do 10 lat" w raporcie okolicy. Budynki bez sprzedaży pierwotnej od 2012 r. mają wiek „nieznany". | Propozycja, do akceptacji użytkownika | 2 |
| 4 | Mapa, pierwsza wersja: serwer na Raspberry Pi, formularz (ulica lub adres, cena, metraż), mapa z ofertą, transakcjami w promieniu i obiektami z OSM, karta z oceną ceny | Do zrobienia | 2, 3 |
| 5 | Wklejanie linku: jeden portal (wybiera użytkownik), odczyt jednej oferty na żądanie, ustalenie położenia oferty, formularz jako zapas | Do zrobienia | 4 |
| 6 | Kolejne powiaty śląskiego: 7 sąsiednich (2470, 2474, 2463, 2477, 2475, 2472, 2408) | Do zrobienia | 2 |
| 7 | Rozpoznanie źródeł oficjalnych, każde z wnioskiem w `docs/`: PSE, GDDKiA, KMZB, NMT GUGiK, mScanner `mode=asking`, regulamin pierwszego portalu | Do zrobienia | |
| 8 | Teren na karcie (wysokość, nachylenie) | Do zrobienia | 4, 7 |
| 9 | Bezpieczeństwo na karcie (KMZB), jeśli rozpoznanie pozwoli | Do zrobienia | 4, 7 |
| 10 | Kolejne portale, monitor ofert (alerty e-mail), przegląd okolic, Docker, uruchamianie cykliczne, powiadomienia | Później | 5 |

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
