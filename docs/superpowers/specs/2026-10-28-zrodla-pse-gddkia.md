# Oficjalne źródła: PSE i GDDKiA (pozycja 7 kolejki, 2026-10-28)

Cel: sprawdzić, czy linie najwyższego napięcia (PSE) i drogi w budowie lub planowane (GDDKiA) są dostępne z oficjalnych źródeł w postaci, którą narzędzie może wczytać (usługa WFS, plik z geometrią), a nie tylko jako mapa do oglądania. Do czasu potwierdzenia na mapie zostają dane OpenStreetMap z oznaczeniem „OSM, orientacyjnie”.

## Co ustalono z chmury (wyszukiwarka; strony pse.pl, gddkia.gov.pl i geoportal są w tej sesji zablokowane)

### GDDKiA

- Sieć dróg krajowych jest publikowana jako usługa WMS na infrastrukturze GUGiK: `https://mapy.geoportal.gov.pl/wss/ext/GDDKiA/SiecDrogowa?SERVICE=WMS&REQUEST=GetCapabilities`. WMS zwraca obrazki, nie geometrię, więc nadaje się najwyżej jako podkład na mapie. Czy ta sama usługa ma WFS, nie wiadomo.
- Strona „Usługi WMS” GDDKiA (`https://www.gddkia.gov.pl/pl/1823/Uslugi-WMS`) wymienia według opisów mapy hałasu i emisji, również na serwerze geoportalu.
- Mapa Stanu Budowy Dróg: `https://www.gov.pl/web/gddkia/msbd` oraz portal mapowy `https://drogi.gddkia.gov.pl/mapy`. Odcinki mają stan (w przygotowaniu, w przetargu, w realizacji, w użytkowaniu), długość i termin zakończenia. Nie znaleziono opisu usługi WFS, API ani pliku do pobrania z geometrią.
- Zakres: tylko drogi zarządzane przez GDDKiA (autostrady, ekspresowe, krajowe). Inwestycje miasta Katowice i województwa to inne źródła.
- Mapy hałasu GDDKiA mogą być osobno przydatne dla uciążliwości (hałas drogowy); do sprawdzenia przy rozpoznaniu.

### PSE

- PSE publikuje plan sieci najwyższych napięć 220 i 400 kV na stronie `https://www.pse.pl/obszary-dzialalnosci/krajowy-system-elektroenergetyczny/plan-sieci-elektroenergetycznej-najwyzszych-napiec` jako dokument (według wyników wyszukiwania: z konwersją do PDF), czyli schemat, nie geometrię.
- Interaktywna mapa inwestycji `https://www.pse.pl/inwestycje/interaktywna-mapa-inwestycji` pokazuje linie i stacje w budowie i planowane, nie istniejącą sieć. Nie znaleziono opisu usługi z danymi.
- Nie znaleziono usługi WMS lub WFS z liniami PSE. Wzmianka z forum (stara) mówi, że dokładne przebiegi nie są udostępniane osobom postronnym.
- Wiki OSM ma społeczną listę linii 220 kV PSE z identyfikatorami relacji OSM (`https://wiki.openstreetmap.org/wiki/Power_networks/Poland/PSE`). To nie jest oficjalny zbiór PSE, ale pozwala sprawdzić kompletność linii w naszym wycinku OSM.

## Wniosek na dziś

- Linie najwyższego napięcia: zostajemy przy OSM. Linie 220–400 kV mają osobny rodzaj na mapie i dopisek „sieć przesyłowa PSE (wg tagu operatora w OSM)”, gdy operator w OSM to PSE (`operator:wikidata=Q1749435` albo nazwa).
- Drogi w budowie i planowane: zostajemy przy OSM. Mapa Stanu Budowy Dróg zostanie podłączona tylko wtedy, gdy rozpoznanie na Pi znajdzie usługę z geometrią lub plik do pobrania; nie przerysowujemy obrazków z mapy.

## Rozpoznanie na Raspberry Pi

```bash
cd /mnt/nas/projects/mieszkanie100 && git pull && bash scripts/zrodla_probe.sh
```

Skrypt pobiera każdą stronę raz (pauza 2 s), zapisuje ją w `ref/zrodla/` (poza repozytorium) i wypisuje: kod HTTP, nazwy warstw usług WMS i WFS oraz linki do usług map (WMS, WFS, ArcGIS) i plików z danymi. Strony zbudowane w JavaScripcie mogą nie mieć linków w kodzie; wtedy zostaje podgląd w przeglądarce (F12, zakładka Sieć), tak jak przy KMZB.

Kryteria przyjęcia źródła: geometria (nie obraz), stabilny adres, warunki korzystania pozwalające na prywatny użytek, data aktualizacji. Każde przyjęte źródło dostaje na karcie oznaczenie „oficjalnie” z nazwą i datą.
