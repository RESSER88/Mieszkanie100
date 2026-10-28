# Mieszkanie100: plan całego projektu

Data: 2026-10-28. Dokument jest mapą etapów. Szczegółowe plany zadań powstają osobno, po jednym na etap, dopiero gdy wymagania danego etapu są zatwierdzone. Dokument projektowy importera: `docs/superpowers/specs/2026-10-28-rcn-importer-design.md`.

## Cel projektu

Narzędzie na Raspberry Pi, które pomaga rodzinie (2 dorosłych, 2 dzieci) wybrać mieszkanie w Katowicach: około 120 m², najlepiej z ogródkiem lub dużym tarasem, budynek do 10 lat, okolica ul. bp. Szurmana, Osiedla Franciszkańskiego, ul. Braci Mniejszych i Osiedla Południe. Narzędzie ma pokazywać, ile naprawdę kosztują podobne mieszkania w okolicy (ceny transakcyjne z aktów notarialnych), jaki jest rynek ofertowy nowych mieszkań, co jest w pobliżu (przedszkola, szkoły, komunikacja) i jakie inwestycje powstają w okolicy. Budżet nie jest ustalony. Użytkownik śledzi rynek od dawna, więc narzędzie ma dawać liczby z podaną próbką i okresem, a nie rekomendacje.

## Zasady przekrojowe

- Każda liczba ma próbkę i okres. Brak danych nie oznacza niskiej ceny. Ceny transakcyjne i ofertowe nigdy nie są mieszane.
- Każda decyzja i jej uzasadnienie trafia do `docs/`, żeby dało się odtworzyć tok myślenia.
- Kod w Pythonie 3.8+, bez zewnętrznych pakietów, dopóki nie ma silnego powodu. Testy automatyczne przed kodem. Zmiany w repozytorium na GitHubie: `RESSER88/Mieszkanie100`.
- Dane osobowe stron transakcji (kupujący, sprzedający) nie są nigdzie wyświetlane.

## Etapy

| Etap | Zakres | Stan |
|---|---|---|
| 0. Importer cen z RCN | Pobieranie lokali dla powiatu 2469 przez WFS, wznawianie, raport. | Zrobiony. 41 845 lokali, zgodność z oficjalnym eksportem w granicach 2 rekordów. |
| 1. Utwardzenie danych | Wyjaśnienie 2 rozbieżnych rekordów. Test warstw `budynki` i `dzialki` (domy i segmenty z ogrodem). Rozkład brakujących cen. Sprawdzenie wartości `tran_rodzaj_rynku`. | Do zrobienia. |
| 2. Okolica: ceny w promieniu | Zapytanie: transakcje w promieniu X metrów od ulicy, z ostatnich N miesięcy, mediana zł/m² z próbką i okresem. Plan: `docs/superpowers/plans/2026-10-28-okolica-query.md`. | Zaimplementowany (`rcn/okolica.py`, 22 testy na danych sztucznych). Czeka na test na prawdziwej bazie na Raspberry Pi, w tym sprawdzenie wartości `rodzaj_rynku`. |
| 3. Ceny ofertowe nowych mieszkań | Klient mScanner (`mode=asking`), sprawdzenie pokrycia Katowic, cytowanie źródła. | Do zrobienia. Pokrycie niesprawdzone. |
| 4. Monitor ogłoszeń | Obserwowanie ofert w wybranych okolicach. | Wstrzymany: nie ma wybranego źródła ani oceny, czy regulaminy portali pozwalają na automatyczne pobieranie. |
| 5. Otoczenie | Przedszkola, szkoły, komunikacja, planowane inwestycje (plan miejscowy, pozwolenia na budowę). | Wstrzymany: nie ma wybranych źródeł. Darmowe API mScanner tego nie zawiera. |
| 6. Uruchomienie | Docker, uruchamianie cykliczne, powiadomienia, odświeżanie danych (WFS od ostatniej daty). | Po etapach 2–3. |

## Decyzje, które musi podjąć użytkownik

1. Zakres typu nieruchomości: tylko mieszkania, czy także domy i segmenty z ogrodem (warstwa `budynki`). Ma wpływ na etap 1 i 2.
2. Źródło ogłoszeń do etapu 4 i zgoda na ryzyko wynikające z regulaminów portali.
3. Kanał powiadomień do etapu 6 (np. e-mail lub komunikator).
4. Źródła danych o otoczeniu do etapu 5.

## Znane ograniczenia danych

- RCN nie ma roku budowy. Kryterium „do 10 lat" wymaga innego źródła lub przybliżenia (np. transakcje z rynku pierwotnego z ostatnich lat).
- Brak pola o ogrodzie i tarasie. Może być wzmianka w tekście `lok_inf`.
- Cena za m² jest policzona dla około 70% rekordów.
- Data dokumentu to nie pewna data transakcji.
