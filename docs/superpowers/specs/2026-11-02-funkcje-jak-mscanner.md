# Funkcje wzorowane na mScanner: rozpoznanie i plan (2026-11-02)

Rozpoznanie wykonał użytkownik (sondy z Raspberry Pi i wyszukiwanie), 2026-11-02. Zasada: mScanner w `robots.txt` blokuje `/app/` i `/api/` oraz deklaruje `ai-train=no, use=reference`. Budujemy te same funkcje na tych samych publicznych źródłach; nie kopiujemy danych ani tekstów mScanner. Konta, płatności, bloga i innych języków nie przenosimy (narzędzie dla jednej rodziny).

Punkt testowy: ul. Szurmana, EPSG:2180 (northing 262720.44, easting 497795.80), WGS84 50.23168, 18.96909.

## Stan źródeł

| Nr | Funkcja | Źródło | Stan rozpoznania |
|---|---|---|---|
| 1 | Tereny i obszary górnicze | PIG-PIB MIDAS, ArcGIS REST `https://cbdgmapa.pgi.gov.pl/arcgis/rest/services/midas/MapServer`, warstwy 1 (obszary górnicze) i 2 (tereny górnicze) | Odpowiada z Pi. Pola atrybutów niesprawdzone. |
| 2 | Plan miejscowy (MPZP) | Krajowa integracja MPZP, WMS GUGiK `https://mapy.geoportal.gov.pl/wss/ext/KrajowaIntegracjaMiejscowychPlanowZagospodarowaniaPrzestrzennego`; warstwy `plany`, `plany_granice`, `raster`, `wektor-pow`/`-lin`/`-pkt`/`-str`/`-lzb`, `granice`; GetFeatureInfo w text/html, gml, text/plain | Usługa odpowiada; zapytanie o punkt niesprawdzone. Plan ogólny gminy: adres nieznany. |
| 3 | Działka pod adresem | ULDK `https://uldk.gugik.gov.pl/?request=GetParcelByXY&xy=EASTING,NORTHING,2180` | Działa. Kolejność: easting, northing (odwrotnie niż nasze krotki). Szurmana: `246901_1.0003.AR_45.14/15`, obręb Ligota. |
| 4 | Powódź | ISOK, Wody Polskie, podgląd `wody.isok.gov.pl/imap_kzgw` (gpMZP, gpMRP) | Adres usługi z odpowiedzią o punkt nieznany (F12 lub GetCapabilities). |
| 5 | Osuwiska | SOPO, PIG, folder `geozagrozenia` na serwerze ArcGIS PIG | Warstwy nieprzejrzane. |
| 6 | Hałas | kandydaci: WMS map akustycznych aglomeracji (ekoportal, 2017–2018), GDDKiA „Strategiczne mapy hałasu 2022”, MSIP Katowice | Źródło dla Katowic nieustalone. |
| 7 | Ceny ofertowe deweloperów | dane.gov.pl (obowiązek od 11.07.2025), API `https://api.dane.gov.pl/1.4/datasets`; szukać po tytule „Ceny ofertowe mieszkań dewelopera”, filtrować Katowice; pliki CSV/XML u deweloperów | API odpowiada, wyszukiwanie wymaga filtrowania. |
| 8 | Pozwolenia na budowę w promieniu | RWDZ GUNB (`wyszukiwarka.gunb.gov.pl`), warstwa w Geoportalu (moduł Planowanie przestrzenne) | Masowego pobierania brak; zapytanie o punkt do sprawdzenia. |
| 9 | Jakość powietrza | API GIOŚ `https://api.gios.gov.pl/pjp-api/v1/rest/station/findAll` | Działa; najbliższa stacja. |
| 10 | Kalkulator kosztów zakupu | obliczenia: PCC 2% tylko rynek wtórny, taksa notarialna (część stawki maksymalnej) + VAT, opłaty sądowe 200/100 zł, wypisy, hipoteka 200 + 19 zł PCC, prowizja, wykończenie zł/m², rata kredytu, opłaty miesięczne | Bez źródeł zewnętrznych. |
| 11 | Moje miejsca i dojazdy | Mapbox (pieszo, rower, samochód); komunikacja: GTFS GZM lub link do Jakdojade | Do zaprojektowania. |
| 12 | Więcej w otoczeniu z OSM | sklepy, apteki, przychodnie, parki, lasy i udział zieleni, place zabaw | Rozszerzenie filtra `osmium` i `scripts/osm_odswiez.sh`. |
| 13 | Porównywarka zapisanych mieszkań | notatki, wydruk do PDF z przeglądarki | Do zaprojektowania. |
| 14 | Mapa dopasowania | siatka na Katowice, ocena wg kryteriów (cena RCN, dojazdy, zieleń, usługi, uciążliwości) | Po 11 i 12. |
| 15 | Mapa 3D ze słońcem i cieniem | Mapbox GL JS v3, budynki 3D, światło kierunkowe | Limit konta demo Mapbox. |
| 16 | Strona cen dzielnic i ulic z RCN, checklista przed zakupem | RCN | Mniej ważne. |

## Kolejność (od 2026-11-02)

1. Kod na źródłach potwierdzonych z Pi: 1 (MIDAS), 3 (ULDK), 10 (kalkulator), 12 (OSM). Zapytania o punkt tylko przy budowie karty, z buforem w SQLite (ten sam punkt nie jest pytany ponownie przez 30 dni).
2. Jedna sonda na Pi dla 2, 4, 5, 6, 8, 9 (`scripts/sondy_listopad.sh`), potem kod dla tych, które odpowiedzą o punkt.
3. 7 (ceny deweloperów z dane.gov.pl), 11 (moje miejsca), 13 (porównywarka), 14 (mapa dopasowania), 15 i 16.

Źródła z wyszukiwania (podane przez użytkownika): [mapy zagrożenia i ryzyka powodziowego, Wody Polskie](https://www.gov.pl/web/wody-polskie-wroclaw/mapy-zagrozenia-i-mapy-ryzyka-powodziowego), [mapy zagrożenia powodziowego, Wody Polskie Warszawa](https://www.gov.pl/web/wody-polskie-warszawa/mzpimrp), [strategiczne mapy hałasu 2022, GDDKiA](https://www.gov.pl/web/gddkia/strategiczne-mapy-halasu-2022), [usługa WMS map akustycznych, INSPIRE](https://inspire-geoportal.ec.europa.eu/srv/api/records/d1dbcc00-6d69-44c4-994c-82d52fbe946c), [jawne ceny deweloperów, Interia](https://biznes.interia.pl/nieruchomosci/news-deweloperzy-nie-ukryja-juz-stawek-rusza-rzadowy-rejestr-ofer,nId,7998898), [ceny mieszkań bez tajemnic, Otodom](https://media.otodom.pl/ceny-mieszkan-bez-tajemnic-rewolucja-czy-tylko-kosmetyka), [przykładowy zbiór dewelopera, dane.gov.pl](https://api.dane.gov.pl/media/resources/20251209/malczew_8accbd9c.xml), [wyszukiwarka publiczna RWDZ](https://inzynierbudownictwa.pl/?p=9536), [Geoportal: warstwa GUNB](https://www.geoportal.gov.pl/aktualnosci/dzien-budowlanca/).
