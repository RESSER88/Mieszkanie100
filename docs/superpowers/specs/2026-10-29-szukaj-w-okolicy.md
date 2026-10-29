# Szukaj ofert w okolicy (2026-10-29)

Prośba użytkownika: wybrać miejsce (najlepiej pinezką) albo wziąć je z podanego linku, ustawić metraż od–do i dostać wszystkie oferty o tym metrażu; na mapie przy dużej liczbie punktów grupowanie, które rozdziela się przy przybliżaniu; pod mapą lista z linkami, ceną i informacjami. Uwaga na deweloperów: sprzedają wiele lokali w jednym budynku. Do tego pełny zestaw filtrów.

## Decyzje

- **Źródło ofert:** zapisane wyniki wyszukiwań (`oferty.sqlite` z `rcn/olx.py szukaj` i `rcn/otodom.py szukaj`). Wyszukiwanie w okolicy niczego nie pobiera z portali, więc jest szybkie i nie obciąża ich; świeżość podaje strona (liczba ofert i dzień ostatniego wyszukiwania na portal).
- **Położenie:** pinezka (klik na mapie, można ją przesunąć), ulica (środek ulicy z RCN) albo link (położenie z ogłoszenia). Przycisk „Pinezka w miejscu karty” bierze punkt z ostatniej karty.
- **Grupowanie:** lokale jednej inwestycji (nazwa z ogłoszenia) albo kilka ofert w jednym punkcie (z dokładnością około 10 m) to jedna pozycja: jeden znacznik z liczbą ofert i jeden wiersz z zakresem metrażu i cen, rozwijany do listy lokali. Przy oddaleniu mapy znaczniki łączą się w koła z liczbą (Leaflet.markercluster 1.5.3 z unpkg, stała wersja i skrót integralności).
- **Filtry** (`rcn/filtry.py`), tylko na polach, które zapisane oferty naprawdę mają: promień 500–3000 m, metraż, cena, cena za m², pokoje, piętro, bez parteru, rynek, deweloperzy (grupuj, ukryj, tylko oni), portale, zabudowa (tylko OLX podaje), nowe z ostatnich N dni, tylko widziane w ostatnim wyszukiwaniu, z dala od linii 110–400 kV, kolei, drogi głównej i przemysłu (OSM, od punktu oferty, który na OLX jest przybliżony), sortowanie. Ustawiony filtr odrzuca ofertę z nieznaną wartością; nieustawiony nigdy nie odrzuca.
- **Czego nie ma i dlaczego:** ogród, taras, balkon, winda i rok budowy nie są w wynikach wyszukiwania (są tylko na stronie ogłoszenia), więc nie da się ich uczciwie filtrować bez pobierania każdego ogłoszenia; wiek budynku z RCN wymaga dokładnego punktu, a OLX podaje przybliżony.
- **Kolory punktów:** cena za m² na tle sprzedaży wtórnych z RCN w tym samym promieniu i metrażu (niebieski poniżej typowego zakresu, szary w zakresie, czerwony powyżej), jak na karcie.
- **Link do wyszukiwania:** adres strony `?tryb=szukaj&lat=…&lon=…&metraz_od=…` odtwarza wyszukiwanie.

## Następne źródła (rozpoznanie)

- **Nieruchomosci-online:** projekt `marcmos/flatscraper` (Haskell, 2026-01) czyta strony wyników miasta (`https://krakow.nieruchomosci-online.pl/…`): kafelki `section.tiles div.tile`, tytuł i link `h2.name a`, cena i metraż w `div.tertiary__box--primary span`; inwestycje pomija po linku kończącym się na `?`; współrzędne są dopiero na stronie ogłoszenia (`var map… = {latitude, longitude}`). Do sprawdzenia na stronie wyników dla Katowic.
- **Morizon:** ten sam projekt: karty `data-cy="card"`, współrzędne w `window.__INITIAL_STATE__`.
- **OLX:** flatscraper używa w adresie wyszukiwania `search[filter_float_m:from]=60`, co potwierdza nazwę filtra metrażu dla przyspieszenia `rcn/olx.py`.
- **mScanner, nowe inwestycje:** znane API daje agregaty cen; czy jest lista inwestycji z położeniem, nie wiadomo (strona zablokowana w chmurze). Rozpoznanie na Pi.

## Wszystkie portale z flatscraper (2026-10-29)

flatscraper obsługuje cztery portale: Otodom, OLX, Nieruchomosci-online i Morizon (w pliku Dockerfile także adres Gratki, bez czytnika w kodzie). Otodom i OLX już mamy. Dodane:

- `rcn/listy.py szukaj --portal nieruchomosci-online|morizon --url "STRONA_WYNIKÓW"`: czyta strony wyników (kafelki Nieruchomosci-online, karty Morizon, selektory z flatscraper), filtruje metraż i cenę, a dla pasujących ofert pobiera stronę ogłoszenia (domyślnie najwyżej 40, pauza 3 s), bo listy nie mają współrzędnych. Strona ogłoszenia jest czytana przez `rcn/portale.py`, więc oferta ma położenie, pokoje, rynek i wzmianki (ogród, taras). Strona ogłoszenia ma pierwszeństwo przed danymi z listy. Pierwsza odmowa kończy pobieranie.
- Inwestycje deweloperów na Nieruchomosci-online (link kończący się na „?”) są pomijane, jak u flatscraper; lokale inwestycji z Otodom są w bazie osobno.
- OLX: `--metraz-od` i `--metraz-do` idą teraz do OLX jako `filter_float_m:from` i `filter_float_m:to` (nazwa z adresu wyszukiwania OLX, potwierdzona u flatscraper). Gdyby OLX odrzucił filtr błędem, pierwsza strona jest raz pobierana bez niego; filtr lokalny działa zawsze.
- Selektory nie są sprawdzone na stronach dla Katowic. Najpierw `bash scripts/portale_probe.sh "STRONA_WYNIKÓW"`.

## Deweloperzy z nowymi mieszkaniami na wszystkich portalach (2026-10-29)

Prośba użytkownika: móc pominąć deweloperów albo znaleźć tylko ich; ich oferty są na każdym portalu.

- Rozpoznanie dewelopera (`filtry.is_developer`), wystarczy jeden sygnał: nazwa inwestycji (Otodom), numer inwestycji (Nieruchomosci-online, klucz `i<numer>_` w `tilesData`), rynek pierwotny, ogłoszeniodawca typu „DEVELOPER” w wynikach Otodom (czytany jest tylko typ, bez nazwy i kontaktów) albo słowa w tytule: „od dewelopera”, „nowe mieszkanie”, „0% prowizji”, „bez PCC” (podatek PCC nie dotyczy rynku pierwotnego), „inwestycja”, „oddanie w”, „stan deweloperski”, „rynek pierwotny”. Sygnał z tytułu działa od razu na zapisanych ofertach; typ ogłoszeniodawcy Otodom pojawi się po następnym `rcn/otodom.py szukaj`.
- Jedna inwestycja na kilku portalach: grupy deweloperskie w odległości do 150 m są łączone w jedną pozycję (jeden znacznik, jeden wiersz, lista portali); nazwa z ogłoszenia ma pierwszeństwo, a bez nazwy pozycja nazywa się „inwestycja deweloperska (bez nazwy w ogłoszeniach)”.
- Filtr „Deweloperzy” jest w głównych filtrach: „pokaż, zgrupowane w inwestycje”, „pomiń deweloperów”, „tylko deweloperzy (nowe mieszkania)”.
- Dymki ofert: przycisk „Otwórz ogłoszenie” obok „Trasa stąd”; dymek inwestycji ma listę lokali z linkami i przycisk „Wszystkie lokale w liście”.
- Czytelność mapy: podpisy przy najbliższym obiekcie każdego ważnego rodzaju z odległością (np. „110 kV, 1,5 km”, „Przedszkole nr 1, 330 m”), białe obwódki pod cienkimi liniami, legenda domyślnie zwinięta.
- Baza OSM jednym poleceniem: `bash scripts/osm_odswiez.sh` (z `--pobierz` także świeży plik z Geofabrik).
