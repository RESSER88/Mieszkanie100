# mScanner a Mieszkanie100: porównanie część po części (2026-11-02)

Źródło: publiczne strony mscanner.pl odczytane z Raspberry Pi skryptem `scripts/mscanner_funkcje.py` (bez `/app/` i `/api/`, które blokuje ich `robots.txt`; deklarują `ai-train=no, use=reference`). Zapisujemy tylko nazwy funkcji jako odniesienie, bez ich tekstów i danych. Budujemy na publicznych źródłach.

Wnioski techniczne z ich stron: dojazdy liczą własnymi silnikami tras (Valhalla: samochód i rower; OTP lub R5: komunikacja), hałas biorą z mapy akustycznej miasta (LDWN), powódź z ISOK. Raport ma ocenę 0–100 według kryteriów użytkownika, wydruk do PDF i link do udostępnienia.

## Części raportu adresu

| Część (ich nazwa) | Co to jest | Źródło publiczne | Mieszkanie100 | Priorytet dla rodziny 2+2 w Katowicach |
|---|---|---|---|---|
| overview, criteria | ocena 0–100, mocne strony i ryzyka, kryteria użytkownika | nasze dane | brak | wysoki |
| property, site-facts | dane z ogłoszenia i rejestrów | ogłoszenie, RCN, ULDK | jest (karta, budynek, działka) | — |
| prices | cena na tle transakcji i ofert | RCN, zapisane oferty | jest | — |
| cost | koszty zakupu ponad cenę | obliczenia | jest | — |
| map | mapa z warstwami: plany, działki, hałas, tereny zalewowe | GUGiK (KIEG, MPZP), LDWN, ISOK | częściowo (OSM, Mapbox) | wysoki |
| nearby | sklepy, szkoły, przychodnie, parki w zasięgu spaceru | OSM | jest | — |
| transport | czasy dojazdu komunikacją i samochodem | Mapbox (auto, pieszo, rower); komunikacja: GTFS GZM + własny silnik lub link | częściowo (trasa z jednego punktu) | wysoki |
| plans, planning | plan miejscowy lub ogólny, dokumenty gminy | KI MPZP (GUGiK) | brak, sonda | wysoki |
| parcels | numer, granice, powierzchnia działki | ULDK, KIEG | numer i obręb (granice brak) | średni |
| construction | pozwolenia na budowę w sąsiedztwie | RWDZ GUNB, warstwa Geoportalu | brak, źródło nieustalone | wysoki |
| road-investments | drogi planowane i budowane | OSM, GDDKiA | jest (OSM) | — |
| zones | strefy ochronne i przyrodnicze, strefa czystego transportu, płatne parkowanie | GDOŚ (formy ochrony przyrody), miasto | brak | średni |
| nuisances | uciążliwości | OSM | jest | — |
| groundwater | powódź i wody gruntowe | ISOK, PIG | brak, sonda | średni |
| mining | teren górniczy, kopalina, kto odpowiada za szkody | MIDAS (PIG) | jest (do sprawdzenia na Pi) | wysoki (Śląsk) |
| landslides, terrain | osuwiska, ukształtowanie terenu | SOPO (PIG), NMT | brak (teren: użytkownik zrezygnował) | niski |
| air | jakość powietrza | GIOŚ | brak, sonda | średni |
| noise | hałas drogowy, kolejowy, lotniczy | mapa akustyczna Katowic, GDDKiA | brak, źródło do ustalenia | wysoki |
| greenery | zieleń wokół | OSM | jest (udział w 500 m) | — |
| building | gęstość zabudowy | OSM budynki lub BDOT10k | brak | niski |
| solar | nasłonecznienie | obliczenia z położenia i zabudowy | brak | niski |
| map-3d | model 3D zabudowy | Mapbox GL (limit konta demo) | brak | niski |
| archival-ortho | zdjęcia lotnicze z lat ubiegłych | ortofotomapy GUGiK (WMS) | brak, sonda | niski |
| street-view | zdjęcia z ulicy | Mapillary (token) | brak | niski |
| mobile-network | zasięg internetu | UKE | brak | niski |
| short-term-rental | najem na doby w okolicy | brak publicznego źródła | pomijamy | — |
| public-registries | wpisy w rejestrach (np. zabytki) | NID (zabytki) | brak | niski |
| ground | rodzaj gruntu | PIG | brak | niski (mieszkanie) |
| wz | warunki zabudowy | gmina | pomijamy (mieszkanie) | — |
| demographics | mieszkańcy i zmiany | GUS BDL | brak | niski |

## Poza raportem

| Funkcja | Mieszkanie100 |
|---|---|
| City Heatmap: które okolice pasują | brak; plan: siatka na Katowice z oceną wg kryteriów |
| Nowe inwestycje na mapie, oferty zgrupowane po projekcie, cena za m², metraż, liczba lokali | jest (wyszukiwanie, „tylko deweloperzy”, scalanie między portalami); ceny z dane.gov.pl brak |
| Porównywarka zapisanych mieszkań | brak |
| Ceny transakcyjne miasta: dzielnice, 12 miesięcy, liczba transakcji, rozkład, „ile trzeba zarabiać” | brak (dane RCN są) |
| PDF i link do raportu | link jest (adres strony); wydruk brak |
| Wklejenie linku, adresu albo numeru działki | link i adres są; numer działki brak |

## Kolejność prac (propozycja)

1. Ocena 0–100 według kryteriów rodziny (cena wobec RCN, wiek budynku, szkoła, przedszkole, przystanek, zieleń, uciążliwości, górnictwo), wagi do zmiany na stronie; wydruk karty do PDF.
2. Warstwy mapy: działki (KIEG), plan miejscowy (KI MPZP), powódź (ISOK), hałas; odpowiedź o punkt na karcie tam, gdzie usługa ją daje (po sondzie).
3. Moje miejsca i dojazdy: praca, szkoły, rodzina; czasy pieszo, rowerem, samochodem z Mapbox; komunikacja: link do Jakdojade z ustawionymi punktami (własny silnik OTP z GTFS GZM jest za ciężki na Pi).
4. Porównywarka zapisanych mieszkań.
5. Mapa dopasowania (siatka na Katowice) i strona cen dzielnic z RCN.
6. Jakość powietrza, strefy przyrodnicze, pozwolenia na budowę, ceny deweloperów z dane.gov.pl.
7. Niski priorytet: ortofotomapy archiwalne, gęstość zabudowy, nasłonecznienie, 3D, zasięg internetu, zabytki, demografia.
