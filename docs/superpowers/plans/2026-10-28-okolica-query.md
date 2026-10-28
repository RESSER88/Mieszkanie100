# Okolica: ceny transakcyjne w promieniu. Plan wdrożenia

> **Dla wykonawców:** wymagany podskill: superpowers:subagent-driven-development (zalecany) albo superpowers:executing-plans. Kroki mają pola wyboru (`- [ ]`) do śledzenia.

**Cel:** polecenie, które dla wskazanej ulicy w Katowicach podaje statystyki cen transakcyjnych lokali w promieniu X metrów z ostatnich N miesięcy, zawsze z próbką i okresem.

**Architektura:** nowy moduł `rcn/okolica.py` czyta bazę SQLite z importera (tabela `lokale`). Środek okolicy to średnia współrzędnych rekordów z daną ulicą. Odległość liczymy płasko w układzie EPSG:2180 (metry). Statystyki liczą się tylko z rekordów, które mają cenę za m².

**Stos:** Python 3.8+, biblioteka standardowa (`sqlite3`, `statistics`, `dataclasses`, `argparse`), `unittest`.

**Dokument projektowy:** `docs/superpowers/specs/2026-10-28-rcn-importer-design.md` (schemat danych i ograniczenia). Zasady „próbka i okres" pochodzą z `docs/superpowers/plans/2026-10-28-mieszkanie100-roadmap.md`, sekcja „Zasady przekrojowe".

## Ograniczenia globalne

- Kolumny tabeli `lokale` (z `rcn/rcn_import.py`): `gid`, `teryt`, `tran_id`, `obj_id`, `dok_data` (tekst `RRRR-MM-DD`), `rodzaj_rynku`, `rodzaj_obiektu`, `liczba_izb`, `tran_cena`, `obj_cena`, `pow_m2`, `cena_m2`, `miejscowosc`, `ulica`, `nr`, `y_pl1992` (północ), `x_pl1992` (wschód).
- Współrzędne w EPSG:2180 w kolejności północ, wschód. Odległość w metrach: `sqrt((dy)^2 + (dx)^2)`.
- Każdy wynik zawiera: liczbę rekordów w próbce, datę najstarszego i najnowszego rekordu, promień i filtry.
- Brak rekordów lub za mała próba nie jest „niską ceną". Raport mówi wprost, że danych jest za mało.
- Rynku pierwotnego i wtórnego nie łączymy w jednej statystyce bez wyraźnego wyboru. Domyślnie raport pokazuje oba osobno.
- Nie wyświetlamy stron transakcji (kupujący, sprzedający).
- Komunikaty dla użytkownika po polsku.

## Przegląd uwag

- Ulica nie istnieje w bazie lub jest zapisana inaczej (`ul. Braci Mniejszych`, wielkość liter, polskie znaki): komunikat „nie znaleziono ulicy" zamiast pustej statystyki.
- Promień mniejszy lub równy 0, ujemna liczba miesięcy: błąd argumentu z komunikatem.
- Rekordy bez współrzędnych: pomijane, ale liczone w komunikacie „pominięto N bez współrzędnych".
- Rekordy z wieloma wersjami tej samej transakcji (para `tran_id`, `obj_id`): liczone raz, bierzemy wersję o największym `gid`.
- Wartości odstające (np. 1069 lub 32 532 zł/m² w danych mScanner): nie wycinamy po cichu, raport podaje percentyle 25 i 75 oraz minimum i maksimum.
- Okno czasowe, w którym nic nie ma: raport „brak danych w okresie", z podaniem okresu.

---

### Zadanie 1: Środek okolicy z nazwy ulicy

**Pliki:**
- Utwórz: `rcn/okolica.py`
- Test: `tests/test_okolica.py`

**Interfejsy:**
- Produkuje: `find_center(con: sqlite3.Connection, street: str, city: str = "Katowice") -> Optional[Tuple[float, float, int]]`. Zwraca `(y_pl1992, x_pl1992, n)`, czyli średnie współrzędne `n` rekordów z tą ulicą, albo `None`, gdy nie ma żadnego. Dopasowanie w Pythonie przez `str.casefold`, na podciąg po usunięciu prefiksu `ul.`.

- [ ] **Krok 1: Test.** W `tests/test_okolica.py` pomocnik `make_db(rows) -> sqlite3.Connection` tworzy tabelę `lokale` w pamięci o kolumnach z „Ograniczeń globalnych" i wstawia rekordy. Testy: `test_find_center_averages_street_records` (dwa rekordy z `ul. Braci Mniejszych` o `y` 262000 i 262100 dają `y` 262050 i `n == 2`), `test_find_center_ignores_case_and_prefix` (zapytanie `"braci mniejszych"` znajduje `"ul. Braci Mniejszych"`), `test_find_center_none_when_street_missing`, `test_find_center_skips_rows_without_coordinates`.
- [ ] **Krok 2: Uruchom, ma się nie udać.** `python3 -m unittest tests.test_okolica -v`, oczekiwane: `ImportError` lub `AttributeError`.
- [ ] **Krok 3: Zaimplementuj `find_center`** w `rcn/okolica.py`.
- [ ] **Krok 4: Uruchom, ma przejść.** Te same polecenie, oczekiwane: `OK`.
- [ ] **Krok 5: Commit.** `git add rcn/okolica.py tests/test_okolica.py && git commit -m "feat(okolica): find street center from RCN coordinates"`.

### Zadanie 2: Transakcje w promieniu

**Pliki:**
- Zmodyfikuj: `rcn/okolica.py`
- Test: `tests/test_okolica.py`

**Interfejsy:**
- Zużywa: `find_center` z zadania 1.
- Produkuje: `transactions_in_radius(con, center: Tuple[float, float], radius_m: float, date_from: str, date_to: str, area_min: Optional[float] = None, area_max: Optional[float] = None) -> List[dict]`. Zwraca rekordy z `dok_data` w `[date_from, date_to]`, w promieniu, z powierzchnią w zakresie (jeśli podany), z `cena_m2` różną od `NULL`, każdą transakcję raz (`tran_id` + `obj_id`, wersja o największym `gid`). Dodaje do każdego rekordu klucz `odleglosc_m`. Zwraca też licznik pominiętych bez współrzędnych jako drugą wartość: typ zwrotny `Tuple[List[dict], int]`.

- [ ] **Krok 1: Test.** `test_radius_includes_and_excludes_by_distance` (rekord 300 m i 800 m od środka przy promieniu 500 daje jeden), `test_radius_filters_by_date_inclusive`, `test_radius_filters_by_area_range` (np. 100–140 m²), `test_radius_counts_each_transaction_once` (dwie wersje z tym samym `tran_id` i `obj_id` dają rekord o większym `gid`), `test_radius_excludes_rows_without_price_per_m2`, `test_radius_reports_skipped_without_coordinates`.
- [ ] **Krok 2: Uruchom, ma się nie udać.** `python3 -m unittest tests.test_okolica -v`.
- [ ] **Krok 3: Zaimplementuj `transactions_in_radius`.** Filtr w SQL po prostokącie otaczającym promień, dokładny dystans w Pythonie.
- [ ] **Krok 4: Uruchom, ma przejść.**
- [ ] **Krok 5: Commit.** `git commit -m "feat(okolica): transactions within radius"`.

### Zadanie 3: Statystyki z próbką i okresem

**Pliki:**
- Zmodyfikuj: `rcn/okolica.py`
- Test: `tests/test_okolica.py`

**Interfejsy:**
- Zużywa: listę rekordów z zadania 2 (klucze `cena_m2`, `obj_cena`, `dok_data`).
- Produkuje: `@dataclass Summary` z polami `n: int`, `period_from: Optional[str]`, `period_to: Optional[str]`, `median_m2: Optional[float]`, `p25_m2`, `p75_m2`, `min_m2`, `max_m2`, `median_price: Optional[float]`, `status: str` (`"ok"`, `"za_mala_proba"` lub `"brak_danych"`); oraz `summarize(rows: List[dict], min_sample: int = 10) -> Summary`. Percentyle metodą interpolacji liniowej. Przy `status != "ok"` liczby nadal są wypełnione (jeśli są), ale raport musi ostrzec.

- [ ] **Krok 1: Test.** `test_summary_median_and_percentiles` (dla `cena_m2` 1..11 mediana 6, p25 3.5, p75 8.5), `test_summary_period_is_min_max_of_dok_data`, `test_summary_status_brak_danych_for_empty`, `test_summary_status_za_mala_proba_below_min_sample`, `test_summary_keeps_outliers_in_min_max`.
- [ ] **Krok 2: Uruchom, ma się nie udać.**
- [ ] **Krok 3: Zaimplementuj `Summary` i `summarize`.**
- [ ] **Krok 4: Uruchom, ma przejść.**
- [ ] **Krok 5: Commit.** `git commit -m "feat(okolica): summary stats with sample and period"`.

### Zadanie 4: Polecenie w terminalu

**Pliki:**
- Zmodyfikuj: `rcn/okolica.py` (dodaj `main(argv=None) -> int`)
- Test: `tests/test_okolica.py`

**Interfejsy:**
- Zużywa: `find_center`, `transactions_in_radius`, `summarize`.
- Produkuje: `format_report(street, radius_m, date_from, date_to, area_range, summaries_by_market: Dict[str, Summary], skipped: int) -> str` oraz `main`. Argumenty: `--db`, `--street` (wymagany), `--radius` (domyślnie 500), `--months` (domyślnie 24), `--area-min`, `--area-max`, `--teryt` (domyślnie `2469`, służy tylko do pominięcia innych powiatów w bazie). Raport pokazuje osobno rynek wtórny i pierwotny; każdy z liczbą próby, okresem, medianą, percentylami 25 i 75, minimum i maksimum; ostrzeżenie przy `za_mala_proba` i `brak_danych`; wiersz o rekordach bez współrzędnych; zdanie, że daty to daty dokumentów, a nie pewne daty transakcji.

- [ ] **Krok 1: Test.** `test_report_contains_sample_and_period`, `test_report_warns_on_small_sample`, `test_report_says_no_data_instead_of_zero_price`, `test_main_returns_2_when_street_missing` (komunikat „nie znaleziono ulicy"), `test_main_rejects_nonpositive_radius_and_months`.
- [ ] **Krok 2: Uruchom, ma się nie udać.**
- [ ] **Krok 3: Zaimplementuj `format_report` i `main`.** Okno dat: od `dzisiaj minus N miesięcy` do dzisiaj, z możliwością wstrzyknięcia „dzisiaj" w testach.
- [ ] **Krok 4: Uruchom całość, ma przejść.** `python3 -m unittest discover -s tests -v`, oczekiwane: `OK` i brak błędów w poprzednich 15 testach.
- [ ] **Krok 5: Test na Raspberry Pi i commit.** `python3 rcn/okolica.py --db rcn_test.sqlite --street "Braci Mniejszych" --radius 500 --months 24`, a potem `git commit -m "feat(okolica): CLI report for street radius"`. Wynik z Raspberry Pi zapisać w dokumencie projektowym.

## Samokontrola planu

- Pokrycie wymagań: środek okolicy (zadanie 1), promień, daty, powierzchnia, deduplikacja (zadanie 2), próbka i okres, brak danych (zadanie 3), raport i argumenty (zadanie 4).
- Spójność nazw: `find_center`, `transactions_in_radius`, `Summary`, `summarize`, `format_report`, `main` występują w jednej postaci we wszystkich zadaniach.
- Uwagi z „Przeglądu uwag" mają testy: brak ulicy (zadanie 1 i 4), promień i miesiące (zadanie 4), brak współrzędnych (zadanie 2), wersje transakcji (zadanie 2), odstające (zadanie 3), pusty okres (zadanie 3 i 4).
