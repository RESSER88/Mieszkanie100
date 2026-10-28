# Mapa: wygląd i podobne oferty (2026-10-28)

Prośba użytkownika: czytelniejsza strona bez utraty szybkości, opisy podzielone na części, do tego do 5 ofert o podobnym metrażu w promieniu 500 m z dostępnych portali. Projekt powstał z pomocą skilli zainstalowanych w sesji chmurowej (w `~/.claude/skills`, nie w repozytorium): UI UX Pro Max, Taste Skill (`design-taste-frontend`), Impeccable, frontend-design (Anthropic), shadcn, oraz wbudowanego skilla dataviz. Awesome Design MD to zbiór plików DESIGN.md, nie skill; posłużył tylko jako materiał porównawczy.

## Decyzje

- **Rodzaj ekranu:** narzędzie do pracy (Impeccable: tryb Operate; Taste Skill: zasady ekranów aplikacji). Wniosek: spokojny wygląd, kolor tylko na danych, bez kart z cieniem, bez etykiet wersalikami, bez emoji jako ikon.
- **Czcionka:** systemowa, cyfry o stałej szerokości (`tabular-nums`). UI UX Pro Max zaproponował Cinzel i Josefin Sans (styl „luksusowe nieruchomości”), odrzucone: dodatkowe pobieranie czcionek spowalnia telefon, a krój ozdobny nie pasuje do narzędzia z liczbami.
- **Układ:** na komputerze mapa po lewej (przyklejona), po prawej części: cena na tle sprzedaży, oferta, budynek, podobne oferty, otoczenie, najbliższe sprzedaże, pełna karta tekstowa (zwinięta). Na telefonie wszystko jedno pod drugim, mapa na 56% wysokości ekranu.
- **Linijka cen** (jedyny wyróżniający się element): pas typowego zakresu (25.–75. percentyl), kreska mediany i pinezka oferty, osobno dla rynku wtórnego, pierwotnego i budynków do 10 lat, na wspólnej skali.
- **Kolory na mapie** (sprawdzone skryptem `validate_palette.js` ze skilla dataviz, tryb jasny i ciemny): cena poniżej typowej niebieska, typowa szara, powyżej czerwona; „na co dzień” (szkoły, przedszkola, przystanki) turkusowe romby. Pierwsza wersja miała pomarańczowe uciążliwości: walidator wykazał, że pomarańczowy i czerwony są nie do odróżnienia (ΔE 7,1 przy zwykłym widzeniu), więc uciążliwości są grafitowe (linia ciągła), a drogi w budowie i planowane mają linię przerywaną. Kolor nigdy nie jest jedynym nośnikiem znaczenia: kształty znaczników się różnią, a obok mapy są tabele.
- **Interakcje:** kliknięcie wiersza tabeli (podobna oferta, sprzedaż) przesuwa mapę i otwiera dymek. Adres strony zawiera zapytanie (`?link=…` albo `?ulica=…`), więc kartę można otworzyć ponownie albo przesłać na telefon.
- **Szybkość:** bez nowych bibliotek, jedna strona HTML (`rcn/mapa.html`, wczytywana raz przy starcie serwera), Leaflet jak dotąd.

## Podobne oferty (`rcn/podobne.py`)

- Źródło: zapisane wyniki wyszukiwań (`oferty.sqlite` z `rcn/olx.py szukaj` i `rcn/otodom.py szukaj`). Serwer niczego przy tym nie pobiera, więc oferta mogła już zniknąć; przy każdej jest data, kiedy była ostatnio widziana.
- Metraż ±15%, promień jak dla karty (domyślnie 500 m), do 5 najbliższych.
- Położenie: punkt z ogłoszenia (OLX oznacza je jako przybliżone), a gdy go nie ma (wyniki Otodom), środek ulicy z RCN. Strona pokazuje, które z nich.
- To samo mieszkanie na dwóch portalach (`portale.same_offer`) pokazane raz, z dopiskiem „także …”. Oferta z karty i jej kopie są pominięte.
- Środek ulicy liczony z indeksu ulic (`okolica.street_index`, sumy współrzędnych na ulicę), a nie przez przeglądanie 41 tys. rekordów dla każdej oferty.
