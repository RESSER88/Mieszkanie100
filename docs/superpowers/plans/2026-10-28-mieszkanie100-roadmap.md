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
| 5. Otoczenie | Przedszkola, szkoły, komunikacja, planowane inwestycje (plan miejscowy, pozwolenia na budowę). | Kandydat na źródło: OpenStreetMap (przedszkola, szkoły, przystanki, linie energetyczne), szczegóły w sekcji „Infrastruktura z OpenStreetMap". Niesprawdzony, szczegóły w sekcji „Mapy i dane przestrzenne". Darmowe API mScanner tego nie zawiera. Planowane inwestycje nadal bez źródła. |
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

## Zasięg: województwo śląskie na start (decyzja użytkownika, 2026-10-28)

Na dziś pracujemy tylko na województwie śląskim, ale konstrukcja ma pozwalać na dodanie kolejnych regionów bez przepisywania kodu.

- **Jednostka rozszerzenia to powiat (kod TERYT, 4 cyfry).** Importer (`rcn/rcn_import.py --teryt ...`) i zapytanie okolicy (`rcn/okolica.py --city ...`) już przyjmują powiat jako parametr, a checkpoint jest zapisywany osobno dla każdej pary warstwa i powiat. Dodanie regionu to uruchomienie importu dla jego powiatów.
- **Województwo śląskie to 36 powiatów** (kody 2401–2417 powiaty ziemskie i 2461–2479 miasta na prawach powiatu). Lista z oficjalnej wtyczki GUGiK: 2401 będziński, 2402 bielski, 2403 cieszyński, 2404 częstochowski, 2405 gliwicki, 2406 kłobucki, 2407 lubliniecki, 2408 mikołowski, 2409 myszkowski, 2410 pszczyński, 2411 raciborski, 2412 rybnicki, 2413 tarnogórski, 2414 bieruńsko-lędziński, 2415 wodzisławski, 2416 zawierciański, 2417 żywiecki, 2461 Bielsko-Biała, 2462 Bytom, 2463 Chorzów, 2464 Częstochowa, 2465 Dąbrowa Górnicza, 2466 Gliwice, 2467 Jastrzębie-Zdrój, 2468 Jaworzno, 2469 Katowice, 2470 Mysłowice, 2471 Piekary Śląskie, 2472 Ruda Śląska, 2473 Rybnik, 2474 Siemianowice Śląskie, 2475 Sosnowiec, 2476 Świętochłowice, 2477 Tychy, 2478 Zabrze, 2479 Żory.
- **Priorytet powiatów:** najpierw Katowice (2469, gotowe), potem sąsiednie miasta (Mysłowice 2470, Siemianowice Śląskie 2474, Chorzów 2463, Tychy 2477, Sosnowiec 2475, Ruda Śląska 2472) i powiat mikołowski (2408), bo mieszkania w pobliżu Katowic bywają porównywalną alternatywą. Dalsze powiaty na życzenie.
- **Skala (szacunek, niesprawdzony):** Katowice to 41 845 lokali i około 210 stron po 200 rekordów. Całe śląskie to prawdopodobnie kilka do kilkunastu razy więcej. SQLite wystarcza, import ma trwać godziny, a nie dni. Trzeba zmierzyć przy drugim powiecie.
- **Do sprawdzenia przy pierwszym dodatkowym powiecie:** czy filtr WFS po `TERYT` działa tak samo dla powiatów ziemskich (nazwy w adresach, gminy), oraz czy zapytanie okolicy nie miesza miejscowości o tej samej nazwie ulicy (parametr `--city` już rozdziela).

## Infrastruktura z OpenStreetMap: linie energetyczne, stacje, szkoły, przystanki (propozycja)

Źródło: wycinek województwa śląskiego z Geofabrik w formacie PBF (według znalezionego opisu około 177 MB, rozmiar i adres `https://download.geofabrik.de/europe/poland/slaskie.html` niezweryfikowane). Pełna Polska to osobny, znacznie większy plik, dla przyszłego rozszerzenia.

- **Obiekty:** linie wysokiego napięcia (`power=line`, tag `voltage` w woltach, np. 110000, 220000, 400000), stacje i transformatory, przedszkola (`amenity=kindergarten`), szkoły (`amenity=school`), przystanki autobusowe i tramwajowe.
- **Wskaźniki dla oferty lub transakcji:** odległość w linii prostej do najbliższej linii energetycznej (z napięciem, jeśli jest w danych), do szkoły, przedszkola i przystanku. To dodatkowe informacje do analizy, a nie ocena atrakcyjności. Odległość od linii nie przesądza o wpływie na wartość mieszkania.
- **Zastrzeżenie o danych:** OSM nie jest kompletnym rejestrem. Brak linii na mapie nie oznacza jej braku w terenie, a tag napięcia bywa niepełny, wielokrotny (np. `110000;220000`) lub nieaktualny. Raport zawsze mówi „brak w danych OSM", nigdy „nie ma".
- **Jak przetwarzać (propozycja):** na Raspberry Pi użyć narzędzia `osmium` (pakiet systemowy `osmium-tool`) do wyfiltrowania tych obiektów z pliku PBF i zapisu do GeoJSON. Nasz kod w Pythonie czyta potem tylko GeoJSON, więc nie dochodzi zewnętrzny pakiet Pythona. Plik PBF odświeżany rzadko (np. raz w miesiącu), bez odpytywania publicznych serwerów dla każdej nieruchomości.
- **Szybki test przed budową:** Overpass Turbo dla jednego obszaru pozwala obejrzeć, czy dane o liniach i szkołach w Katowicach są sensowne. Publiczny Overpass ma limity, więc tylko do oglądania.
- **Mapa:** MapLibre GL JS lub Mapbox GL JS. Przy wyświetlaniu obowiązuje podanie źródła „© autorzy OpenStreetMap" i licencja ODbL. Publiczne kafelki OSM nie służą do masowego pobierania na zapas.

### Zadania

1. Na Raspberry Pi pobrać plik PBF śląskiego, sprawdzić rozmiar i zainstalować `osmium-tool`. Wynik zapisać w `docs/`.
2. Wyfiltrować linie energetyczne, stacje, szkoły, przedszkola i przystanki do GeoJSON, policzyć obiekty w Katowicach.
3. Moduł `rcn/otoczenie.py`: najbliższy obiekt danego rodzaju od punktu (odległość w EPSG:2180 po przeliczeniu z WGS84) z testami na małym zestawie GeoJSON.
4. Dodać wskaźniki do karty okolicy.

## Wiedza o lokalizacji: uciążliwości w okolicy i planowane drogi (życzenie użytkownika, 2026-10-28)

Użytkownik chce, żeby karta lokalizacji (etap 2 i 4) dawała też wiedzę o samej okolicy, nie tylko o cenach. Opisy poniżej to zakres funkcji, a stan źródeł jest oznaczony wprost. Wszystko to są informacje pomocnicze, a nie ocena atrakcyjności ani wpływu na wartość.

### Blok A: uciążliwości w okolicy

Co pokazujemy dla punktu (oferta, transakcja, ulica): najbliższe obiekty z odległością w metrach i rodzajem.

| Obiekt | Źródło | Stan |
|---|---|---|
| Linie wysokiego napięcia (110 kV i więcej), słupy, stacje | OpenStreetMap, tag `power`, `voltage` | Do sprawdzenia na pliku PBF. Dane społeczności, mogą być niepełne. |
| Linie najwyższego napięcia (220 i 400 kV) | OpenStreetMap (sieć PSE jest naniesiona, `power=line`, `voltage=220000` lub `400000`) oraz ewentualnie rządowe dane PSE | Według wiki OSM (strona „Power networks/Poland") sieć 220 i 400 kV to szkielet prowadzony przez PSE. Nazwa operatora w tagach jest niejednolita („Polskie Sieci Elektroenergetyczne S.A.", „PSE Operator"), więc filtrujemy po `operator:wikidata=Q1749435` albo po samym napięciu. Strona „Power networks/Poland/PSE" nieprzeczytana (zablokowana w chmurze). Dane do pobrania od PSE niesprawdzone. |
| Maszty i wieże telekomunikacyjne | OpenStreetMap (`man_made=mast`, `tower:type=communication`) | Do sprawdzenia. |
| Kolej | OpenStreetMap (`railway=rail`; czynna czy zlikwidowana wynika z tagów) | Do sprawdzenia. |
| Drogi główne | OpenStreetMap (`highway=motorway/trunk/primary`) | Do sprawdzenia. |
| Przemysł | OpenStreetMap (`landuse=industrial`) | Do sprawdzenia. Etykieta „przemysł" bywa szeroka, nie oznacza uciążliwości. |
| Inne (propozycja autora: składowiska, kamieniołomy, lotnisko) | OpenStreetMap | Do uzgodnienia z użytkownikiem. |

Reguły: promienie są parametrami konfiguracji (domyślne wartości ustala użytkownik po obejrzeniu pierwszych wyników), brak obiektu w danych to „brak w danych OSM", a nie „nie ma", każda pozycja ma podane źródło i jego wiarygodność.

### Blok B: planowane i budowane drogi

Zakres podany przez użytkownika: drogi w budowie i w planach w promieniu 3 km od nieruchomości. Przy każdej odległość, docelowa klasa drogi i rok otwarcia, jeśli jest znany.

- **OpenStreetMap (społeczność):** drogi w budowie i projektowane (`highway=construction`, `highway=proposed`, tagi `construction`, `opening_date`). Dane orientacyjne, nie oficjalne stanowisko GDDKiA, często niepełne i bez roku otwarcia.
- **GDDKiA, Mapa Stanu Budowy Dróg:** oficjalne źródło dla dróg krajowych, autostrad i ekspresowych, według GDDKiA. Dotyczy tylko dróg zarządzanych przez GDDKiA, więc nie obejmuje dróg miejskich i powiatowych (np. inwestycje miasta Katowice). Dla nas właściwe jest województwo śląskie. Czy GDDKiA udostępnia te dane w formie do pobrania (API, plik), a nie tylko jako mapę w przeglądarce, nie zostało sprawdzone.
- **Stan źródeł:** w opisie tej funkcji u mScanner dane o planowanych drogach są „chwilowo niedostępne" (wg wklejonego tekstu), więc nie zakładamy, że gotowe źródło istnieje. Plany drogowe miejskie (np. zarządca dróg Katowic, plan miejscowy, studium) to osobne źródła, jeszcze nierozpoznane.
- **Zasada prezentacji:** każdą pozycję oznaczamy „OSM, orientacyjnie" albo „GDDKiA, oficjalnie". Rok otwarcia podajemy tylko, gdy jest w źródle. Brak roku to „rok nieznany", nie zgadujemy.

### Blok C: ukształtowanie terenu (pytanie użytkownika, 2026-10-28)

Pomysł: do karty lokalizacji dodać wysokość n.p.m. punktu oraz proste wskaźniki rzeźby terenu w otoczeniu (nachylenie w promieniu około 100 m, położenie względem okolicy: wzniesienie, zbocze lub obniżenie). Wskaźnik pomocniczy, nie ocena i nie analiza ryzyka powodziowego.

| Źródło | Co wiadomo (z pamięci i opisu użytkownika, niezweryfikowane ze środowiska chmurowego) | Za | Przeciw |
|---|---|---|---|
| Open-Meteo Elevation API (`https://api.open-meteo.com/v1/elevation`) | Wysokość dla podanych współrzędnych geograficznych, według dokumentacji oparta na globalnym modelu terenu o rozdzielczości około 90 m. Bez klucza, z limitami dziennymi i ograniczeniem do użytku niekomercyjnego. | Proste, jedno zapytanie, dobre do szybkiego testu. | Rozdzielczość około 90 m jest zgrubna dla jednej działki lub budynku. Wymaga współrzędnych WGS84, a nasze są w EPSG:2180, więc potrzebne jest przeliczenie. Zapytania zewnętrzne dla każdej nieruchomości (buforujemy wyniki). |
| GUGiK, Numeryczny Model Terenu (NMT) | Oficjalny model terenu dla Polski o znacznie większej rozdzielczości, dostępny przez geoportal (pliki do pobrania oraz usługi). Dokładny adres usługi punktowej i warunki licencji nie zostały sprawdzone. | Dokładniejszy. Prawdopodobnie przyjmuje współrzędne w EPSG:2180, więc bez przeliczania. Spójny z resztą danych GUGiK. | Usługa i format niesprawdzone. Duże pliki, jeśli pobierać siatkę zamiast pojedynczych punktów. |

Rekomendacja: sprawdzić najpierw usługę punktową NMT z GUGiK na Raspberry Pi, bo pasuje do naszego układu współrzędnych i jest dokładniejsza. Open-Meteo zostaje planem zapasowym lub szybkim testem. Wybór zapada po spike'u na Raspberry Pi: wysokość dla 10 znanych punktów w Katowicach porównana z tym, co użytkownik wie o terenie.

Zadania: spike obu źródeł na kilku punktach (wynik w `docs/`), moduł pobierania wysokości z buforem w SQLite (ten sam punkt nie jest pytany dwa razy), wskaźnik nachylenia z kilku punktów wokół, prezentacja na karcie z oznaczeniem źródła i rozdzielczości.

### Blok D: bezpieczeństwo, Krajowa Mapa Zagrożeń Bezpieczeństwa (propozycja użytkownika, 2026-10-28)

Oficjalna mapa: `https://mapy.geoportal.gov.pl/iMapLite/KMZBPublic.html`. Pozwala przeglądać zgłoszenia i filtrować je wg kategorii (np. nielegalne parkowanie, przekraczanie prędkości, akty wandalizmu, spożywanie alkoholu w miejscach zabronionych, zła infrastruktura drogowa), statusu i daty. Według źródeł policyjnych mapa łączy dane z systemów Policji, zgłoszenia mieszkańców przez internet i informacje z bezpośrednich kontaktów.

- **Stan źródła:** w oficjalnych materiałach nie znaleziono dokumentacji publicznego API ani zbioru na dane.gov.pl. Nie wiadomo, czy dane są dostępne inaczej niż przez aplikację mapową.
- **Rozpoznanie (wykonuje użytkownik na komputerze):** otworzyć mapę, narzędzia programisty (F12), zakładka Sieć, filtr Fetch/XHR, odświeżyć i przesunąć mapę. Zapisać adresy żądań zwracających JSON, GeoJSON, WFS lub usługę ArcGIS. Dopiero potem ocena, czy korzystanie z takiej usługi jest dozwolone i stabilne. Bez potwierdzonej, oficjalnej usługi blok D nie powstaje.
- **Wygląd na karcie (z propozycji użytkownika):** promień 500 m, 1 km lub 2 km, kategorie i daty, liczba zgłoszeń w okolicy, odległość od nieruchomości, data ostatniej aktualizacji danych, link do oficjalnej mapy.
- **Zasady:** odróżniać zgłoszenia mieszkańców od zagrożeń potwierdzonych przez Policję. Liczba zgłoszeń nie jest liczbą przestępstw. Brak zgłoszeń to brak zgłoszeń, a nie dowód bezpieczeństwa.

### Zadania

1. Spike na Raspberry Pi: z pliku PBF śląskiego wyfiltrować obiekty z bloku A i B, policzyć je w promieniu 3 km od ul. Braci Mniejszych, obejrzeć wyniki z użytkownikiem.
2. Rozpoznanie źródeł oficjalnych: PSE (linie najwyższego napięcia), GDDKiA (stan budowy dróg), zarządca dróg w Katowicach. Dla każdego: czy są dane do pobrania, format, licencja, data sprawdzenia. Wynik w `docs/`.
3. Moduł `rcn/otoczenie.py` (wspólny z infrastrukturą z OSM, zadanie 3 w sekcji o OSM): najbliższe obiekty wg rodzaju z odległością, z testami na małym zestawie GeoJSON.
4. Dodać bloki A i B do karty okolicy, z oznaczeniem źródła i wiarygodności.

## Mapy i dane przestrzenne: Mapbox i OpenStreetMap (propozycja, 2026-10-28)

Użytkownik chce użyć darmowej wersji Mapbox (repozytorium `mapbox/mapbox-agent-skills`) oraz OpenStreetMap (przewodnik wiki OSM dla biznesu). Poniżej to, co ustalono, i to, czego jeszcze nie sprawdzono. Wiki OSM i strony Mapbox są niedostępne ze środowiska chmurowego, więc zasady licencji i limity trzeba potwierdzić na Raspberry Pi lub po odblokowaniu domen.

### Do czego który element

- **Skille Mapbox** to instrukcje dla agenta (jak poprawnie budować mapy, wyszukiwanie adresów, ochrona tokenów), a nie usługa. Zainstalowano sześć istotnych: geospatial-operations, search-patterns, search-integration, token-security, web-integration-patterns, data-visualization-patterns. Same usługi Mapbox (mapa, geokodowanie, czasy dojazdu) wymagają darmowego konta i tokenu dostępu.
- **Mapa transakcji** na stronie z Raspberry Pi (etap 6): punkty transakcji z kolorem wg ceny za m². Kandydaci: Mapbox GL JS (token publiczny z ograniczeniem adresu URL) albo MapLibre z kafelkami OSM. Wybór po sprawdzeniu limitów darmowego planu.
- **Geokodowanie adresów ofert** (etap 4): oferty często mają tylko adres. Kolejność prób (propozycja): (1) współrzędne z własnej bazy RCN dla tej samej ulicy i numeru, (2) Nominatim z buforowaniem wyników, (3) Mapbox tylko po sprawdzeniu warunków.
- **Otoczenie** (etap 5): przedszkola (`amenity=kindergarten`), szkoły (`amenity=school`) i przystanki (`highway=bus_stop`, `railway=tram_stop`) z OpenStreetMap, odległość od współrzędnych oferty. Zalecane: pobrać wycinek danych dla województwa śląskiego i odświeżać go rzadko, zamiast odpytywać publiczne serwery przy każdej karcie.

### Ograniczenia i ryzyka (do potwierdzenia przed użyciem)

- Mapbox: według skilla `mapbox-search-integration` wyniki geokodowania przeznaczone do przechowywania w bazie wymagają trybu „permanent" Geocoding API. Czy mieści się to w darmowym planie, trzeba sprawdzić w cenniku. Nie przechowujemy w bazie wyników geokodowania w trybie tymczasowym, dopóki warunki tego nie potwierdzą. Limity darmowego planu (mapy, geokodowanie, czasy dojazdu) nie zostały sprawdzone.
- Token Mapbox: nigdy w repozytorium ani w czacie. Na Raspberry Pi w zmiennej środowiskowej `MAPBOX_ACCESS_TOKEN`. Token publiczny z ograniczeniem adresów URL, bez uprawnień zapisu (zasady ze skilla `mapbox-token-security`).
- OpenStreetMap: dane na licencji ODbL wymagają podania źródła („© autorzy OpenStreetMap") przy wyświetlaniu. Warunki dla baz pochodnych (Share-Alike) i pełne zasady z przewodnika dla biznesu nie zostały jeszcze przeczytane.
- Publiczny Nominatim: według oficjalnej polityki działa na ograniczonych, donowanych serwerach, wymaga rozpoznawalnego `User-Agent`, zaleca buforowanie, odradza zapytania masowe i zakazuje przesyłania danych osobowych. Dopuszczalne dla małej aplikacji z buforowaniem, nie dla pętli po tysiącach adresów.
- Overpass API ma własne limity korzystania. Zasady nie zostały sprawdzone.

### Zadania

1. Odblokować domeny w ustawieniach sieci środowiska albo sprawdzić zasady na Raspberry Pi: wiki OSM, osmfoundation.org, mapbox.com (cennik i warunki).
2. Zapisać w `docs/` wniosek o licencji ODbL, warunkach Mapbox i dozwolonym przechowywaniu wyników.
3. Spike na Raspberry Pi: pobrać wycinek OSM dla woj. śląskiego, policzyć przedszkola i szkoły w promieniu 1 km od ul. Braci Mniejszych i porównać z tym, co użytkownik wie o okolicy.
4. Dopiero potem wybrać Mapbox GL JS lub MapLibre dla mapy transakcji.

## OLX i Otodom: rozpoznanie istniejących projektów (2026-10-28)

Strona ogłoszenia OLX odpowiada naszemu narzędziu HTTP 403. Nie obchodzimy tej blokady. Przejrzane projekty open source:

- `DEENUU1/property-aggregator` (ostatnia zmiana 2024-06): OLX przez JSON `https://www.olx.pl/api/v1/offers/?offset=0&limit=40&category_id=14` (pola `params`: `price`, `m`, `price_per_m`, `rooms`, `floor_select`, `builttype`; `location.city.name`, `location.region.name`). Otodom przez strony wyników z klasami CSS z 2024 roku i podszywanie się pod przeglądarkę, cała Polska. Architektura (FastAPI, Postgres, MongoDB, Celery) za ciężka na Raspberry Pi. Otodom stamtąd nie bierzemy.
- `kromylodd/Polish-Housing-Market-Intelligence-Platform` (aktywny do 2026-08): OLX przez GraphQL `https://www.olx.pl/apigateway/graphql`, zapytanie `ListingSearchQuery` (`clientCompatibleListings`), pola `id`, `url`, `title`, `created_time`, `location.city.name`, `location.district.name`, `map.lat`, `map.lon`, `params` (`GenericParam` z `key` i `label`, `PriceParam` z `value`). Katowice: `city_id=7691`, `region_id=6`. Kategoria 14 to sprzedaż mieszkań, 15 wynajem. 40 ofert na stronę. Zasady autora: tylko wyniki wyszukiwania (bez stron ogłoszeń), globalny limit tempa 1,5–3 s, najwyżej 4 zapytania naraz, ponawianie z rosnącym opóźnieniem. Autor przedstawia się jako przeglądarka Chrome; my używamy uczciwego identyfikatora.

Propozycja (do decyzji użytkownika, ryzyko regulaminu OLX dla nieoficjalnego API): pozycja 10 kolejki „przeglądanie ogłoszeń z rynku wtórnego" przez wyszukiwanie GraphQL dla Katowic raz dziennie, z filtrem dzielnicy i metrażu po naszej stronie, z przerwą kilku sekund między stronami i jednym zapytaniem naraz. Każda oferta ma współrzędne, więc od razu dostaje kartę. Pierwszy krok: jedno zapytanie testowe z Raspberry Pi (czy API odpowiada na nasz identyfikator).

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
