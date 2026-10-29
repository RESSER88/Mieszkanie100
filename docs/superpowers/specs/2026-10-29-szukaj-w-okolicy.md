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
