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

## Poprawka układu po dodaniu wyszukiwania (2026-10-29)

Zgłoszenie: „coś się rozjechało”. Pomiar w przeglądarce: w trybie wyszukiwania nagłówek miał 517 px na komputerze i 1160 px na telefonie (wszystkie filtry w nagłówku), mapa była poniżej ekranu, pary „od–do” rozrywały się między wierszami, 13 elementów miało mniej niż 32 px wysokości.

Poprawka (Impeccable: tryb Operate i progi z craft-floor; Taste Skill: zasady ekranów aplikacji, pierwszy ekran ma pokazać mapę i wynik; UI UX Pro Max: cele dotyku 44 px, widoczne etykiety, stopniowe odsłanianie):

- Nagłówek to tylko pole „gdzie” i przycisk. Filtry są osobnym panelem: na komputerze w prawej kolumnie nad wynikami, na telefonie jedna linia z podsumowaniem („1 km, 60–130 m², jeszcze 2”) nad mapą, rozwijana na dotknięcie i zwijana po wyszukaniu.
- Siatka dwóch kolumn; zakresy „od–do” zawsze w jednym wierszu pod jedną etykietą; pola i listy 44 px; portale, zabudowa i opcje jako przełączniki 40 px.
- „Więcej filtrów” z liczbą aktywnych ukrytych filtrów; „Wyczyść filtry”.
- Legenda zależy od trybu (w wyszukiwaniu: kolory cen, skupiska, inwestycje, pinezka).
- Wynik po poprawce: nagłówek 138 px (komputer), 211 px (telefon), brak przewijania w bok na 390, 820 i 1440 px, brak błędów JavaScript.

## Mapa mieści się w oknie (2026-10-29)

Zgłoszenie: mapa nie mieści się na stronie i jest poziomym paskiem zamiast prostokąta bliskiego kwadratowi. Przyczyny: na komputerze mapa miała wysokość okna, ale zaczynała się pod nagłówkiem (dół ucięty); na telefonie miała 56% wysokości ekranu, a w poziomie wychodził pasek 273 px; na dużym monitorze strona miała najwyżej 1440 px szerokości.

- Komputer (szerokość od 1024 px) i telefon w poziomie: układ aplikacji. Nagłówek, pod nim mapa dokładnie do dołu okna, przewija się tylko prawa kolumna (filtry najwyżej 55% wysokości, wyniki pod nimi). Na dużym monitorze mapa wypełnia całą szerokość.
- Telefon w poziomie: jedna linia nagłówka (zakładki i pole wyszukiwania obok siebie), bez nazwy i bez opcji karty (promień, okres, wpis ręczny są w widoku pionowym).
- Telefon i tablet w pionie: mapa kwadratowa o boku równym szerokości ekranu, najwyżej 70% jego wysokości.
- Zmierzone w przeglądarce: 1920×1080, 1280×720, 820×1180, 390×844 i 844×390; mapa w całości w oknie (poza widokiem pionowym telefonu z otwartym wpisem ręcznym), bez przewijania w bok.

## Mapbox: stonowany podkład i trasy (2026-10-29)

- Token: na Raspberry Pi w zmiennej `MAPBOX_ACCESS_TOKEN` (plik `~/.mieszkanie100.env`, prawa 600, wczytywany z `~/.bashrc`), nigdy w repozytorium ani w czacie. Serwer wstawia do strony tylko token publiczny (`pk.`, sprawdzany wyrażeniem regularnym); tajny (`sk.`) albo niepoprawny nie trafia do przeglądarki, a serwer wypisuje ostrzeżenie (zasady ze skilla mapbox-token-security). Bez tokenu mapa wraca do kafelków OpenStreetMap, a trasy są wyłączone.
- Podkład: Mapbox `light-v11` (w ciemnym motywie `dark-v11`) jako kafelki rastrowe przez Leaflet, z wymaganym podpisem Mapbox i OpenStreetMap oraz linkiem „Popraw tę mapę”. Odpowiada na zgłoszenie, że mapa jest nieczytelna: na stonowanym podkładzie dane się wyróżniają. OpenStreetMap jest do wyboru w menu warstw.
- Trasy (prośba użytkownika): w dymku szkoły, przedszkola, przystanku, podobnej oferty, oferty i inwestycji z wyszukiwania jest przycisk „Trasa stąd”. Początek: punkt oferty z karty albo pinezka w wyszukiwaniu. Najpierw trasa piesza z Mapbox Directions; gdy jest dłuższa niż 3 km, druga trasa samochodem, a podpis podaje oba czasy. Trasa piesza jest kropkowana, samochodowa ciągła, z podpisem na mapie i w linii stanu. Przy przybliżonym położeniu oferty trasa zaczyna się w przybliżonym punkcie.
- Sprawdzone w przeglądarce w chmurze z podstawionymi odpowiedziami Mapbox (serwery Mapbox są z chmury zablokowane): 950 m daje „pieszo 12 min”, 4,2 km daje drugie zapytanie i „samochodem … pieszo byłoby …”.
