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
| 4. Monitor ofert zakupu | Pobieranie ofert kupna z portali: Otodom, Gratka, OLX Nieruchomości, Morizon, Nieruchomosci-online.pl, Domiporta, Adresowo, RynekPierwotny. Szczegóły w sekcji „Etap 4" poniżej. | Zażądany przez użytkownika 2026-10-28. Wymaga rozpoznania każdego portalu (regulamin, dostęp techniczny) przed budową. Nie zaczęty. |
| 5. Otoczenie | Przedszkola, szkoły, komunikacja, planowane inwestycje (plan miejscowy, pozwolenia na budowę). | Wstrzymany: nie ma wybranych źródeł. Darmowe API mScanner tego nie zawiera. |
| 6. Uruchomienie | Docker, uruchamianie cykliczne, powiadomienia, odświeżanie danych (WFS od ostatniej daty). | Po etapach 2–3. |

## Etap 4: monitor ofert zakupu (szczegóły)

Cel: oferty kupna z ośmiu portali (Otodom, Gratka, OLX Nieruchomości, Morizon, Nieruchomosci-online.pl, Domiporta, Adresowo, RynekPierwotny) trafiają do jednej bazy na Raspberry Pi. Dla każdej oferty z wybranych okolic narzędzie podaje kartę z etapu 2: gdzie cena ofertowa leży na tle cen transakcyjnych w promieniu.

### Czego nie wiadomo (do rozpoznania przed budową)

- Które portale pozwalają w regulaminie na automatyczne pobieranie ofert i na jakich warunkach. To trzeba sprawdzić osobno dla każdego portalu i zapisać w `docs/` (data sprawdzenia, link do regulaminu, wniosek). Duże portale zwykle zabraniają automatycznego pobierania w regulaminie, stosują ochronę przed botami i mogą zablokować adres IP. Decyzję o ryzyku podejmuje użytkownik, a nie narzędzie.
- Czy portal udostępnia legalną, mniej kruchą drogę: powiadomienia e-mail z zapisanych wyszukiwań (alerty), kanały RSS, oficjalne API lub dane strukturalne na stronie ogłoszenia.
- Czy portal w ogóle odpowiada na zwykłe zapytania HTTP z Raspberry Pi, czy wymaga przeglądarki. To środowisko chmurowe nie ma dostępu do tych domen, więc wszystkie rozpoznania i testy z prawdziwymi stronami wykonuje się na Raspberry Pi.

### Propozycja podejścia (do zatwierdzenia)

1. **Najpierw alerty e-mail, potem pobieranie stron.** Najmniej kruchy wariant to zapisane wyszukiwania w portalach, które wysyłają powiadomienia na skrzynkę, i odczytywanie tych wiadomości przez IMAP. Nie obchodzi żadnych zabezpieczeń i działa dla portali, które oferują alerty. Dla portali bez alertów rozważyć pobieranie publicznych stron z ograniczeniem szybkości.
2. **Jeden portal na raz.** Adapter na portal, wspólny format oferty, wspólna deduplikacja. Zaczynamy od jednego portalu wybranego przez użytkownika, kolejne dodajemy po zatwierdzeniu pierwszego.
3. **Zasady grzeczności.** Zgodność z `robots.txt`, rozsądne odstępy między żądaniami (rzędu kilku sekund), pamięć podręczna, rozpoznawalny `User-Agent`, brak obchodzenia captcha i logowania. Awaria jednego portalu nie zatrzymuje pozostałych, a raport mówi, których portali nie udało się odczytać.
4. **Testy na zapisanych stronach.** Z Raspberry Pi zapisujemy po kilka prawdziwych stron wyników i ogłoszeń na portal (bez danych osobowych) i na nich piszemy testy parsera. Dzięki temu testy działają w chmurze bez dostępu do portali.

### Wspólny format oferty (propozycja)

`portal`, `id_w_portalu`, `url`, `tytul`, `cena_ofertowa`, `powierzchnia_m2`, `liczba_pokoi`, `pietro`, `rynek` (pierwotny lub wtórny), `adres` lub `ulica` i `dzielnica`, współrzędne (jeśli portal je podaje), `rok_budowy` (ogłoszenia często go zawierają, co częściowo wypełnia lukę, której nie ma w RCN), wzmianki o ogrodzie, tarasie i balkonie z opisu, `data_dodania`, historia zmian ceny, `status` (aktywna, zdjęta).

### Zasady jakości

- Oferty to ceny ofertowe. Nigdy nie mieszamy ich z cenami transakcyjnymi (zasada przekrojowa z początku dokumentu).
- Ta sama oferta na kilku portalach liczy się raz (klucz: adres lub współrzędne, powierzchnia, cena z tolerancją).
- Oferta bez ceny, powierzchni lub adresu jest zapisywana, ale oznaczona jako niekompletna i nie wchodzi do kart.
- Cena ofertowa za m² bez podanej próbki transakcji z okolicy nie jest oceniana.

### Zadania etapu 4 (kolejność)

1. Rozpoznanie jednego wybranego portalu: regulamin, `robots.txt`, alerty e-mail, odpowiedź na zwykłe zapytanie HTTP. Wynik w `docs/`.
2. Wspólny format oferty i baza ofert (SQLite, osobna od bazy transakcji) z testami.
3. Adapter pierwszego portalu na zapisanych stronach.
4. Połączenie z kartą z etapu 2.
5. Kolejne portale, po jednym.

## Decyzje, które musi podjąć użytkownik

1. Zakres typu nieruchomości: tylko mieszkania, czy także domy i segmenty z ogrodem (warstwa `budynki`). Ma wpływ na etap 1 i 2.
2. Od którego portalu zaczynamy etap 4 (zalecenie: od jednego, najczęściej używanego przez użytkownika) oraz zgoda na ryzyko wynikające z regulaminów portali (patrz etap 4).
3. Kanał powiadomień do etapu 6 (np. e-mail lub komunikator).
4. Źródła danych o otoczeniu do etapu 5.

## Znane ograniczenia danych

- RCN nie ma roku budowy. Kryterium „do 10 lat" wymaga innego źródła lub przybliżenia (np. transakcje z rynku pierwotnego z ostatnich lat).
- Brak pola o ogrodzie i tarasie. Może być wzmianka w tekście `lok_inf`.
- Cena za m² jest policzona dla około 70% rekordów.
- Data dokumentu to nie pewna data transakcji.
