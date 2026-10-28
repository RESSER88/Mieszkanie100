# Mieszkanie100: efekt końcowy narzędzia

Data: 2026-10-28. Status: propozycja do poprawienia przez użytkownika. Elementy oznaczone „propozycja" nie pochodzą od użytkownika, tylko od autora dokumentu, z uzasadnieniem.

## Po co

Rodzina (2 dorosłych, 2 dzieci) mieszka w małym mieszkaniu w Katowicach i szuka około 120 m², najlepiej z ogródkiem lub dużym tarasem, w budynku do 10 lat. Obecnie podoba im się mieszkanie przy ul. bp. Tadeusza Szurmana na Osiedlu Franciszkańskim. Interesuje ich też okolica ul. Braci Mniejszych i Osiedle Południe. Użytkownik od dawna śledzi rynek, ale ceny ofertowe są trudne do oceny bez porównania z cenami, za które mieszkania naprawdę się sprzedały. Budżet nie jest ustalony.

## Efekt końcowy (propozycja)

Przed obejrzeniem konkretnego mieszkania użytkownik w mniej niż minutę wie, czy cena ofertowa mieści się w cenach realnych transakcji z tej okolicy, i widzi, na jakich danych ta ocena stoi.

Narzędzie działa na Raspberry Pi. Wynik wygląda tak:

1. **Karta mieszkania.** Użytkownik podaje ulicę (lub adres), cenę ofertową i metraż. Dostaje kartę, na której są:
   - mediana i zakres typowych cen za m² z transakcji w promieniu około 500 m z ostatnich 24 miesięcy, osobno dla rynku wtórnego i pierwotnego,
   - miejsce ceny ofertowej na tle tych transakcji (poniżej, w środku, powyżej typowego zakresu),
   - liczba transakcji i okres, z którego pochodzą,
   - lista kilku najbliższych podobnych transakcji (ulica, powierzchnia, cena, cena za m², data dokumentu),
   - ostrzeżenie, gdy próba jest za mała, żeby ufać medianie.
2. **Przegląd obserwowanych okolic.** Okresowe zestawienie dla wybranych okolic (Osiedle Franciszkańskie i okolice ul. Szurmana, okolice ul. Braci Mniejszych, Osiedle Południe): jak zmieniają się ceny i ile było nowych transakcji.
3. **Otoczenie i inwestycje** (późniejszy etap): przedszkola, szkoły, komunikacja, planowane inwestycje.

Forma (propozycja): na początku polecenie w terminalu (`rcn/okolica.py`), potem prosta strona dostępna z telefonu w sieci domowej, serwowana z Raspberry Pi. Powiadomienia dopiero na końcu. Uzasadnienie: polecenie można sprawdzić od razu na danych, strona dodaje wygodę, ale nie zmienia liczb.

## Co oznacza sukces

- Karta mieszkania dla znanej ulicy powstaje w kilka sekund z lokalnej bazy, bez internetu.
- Każda liczba ma podaną próbkę i okres.
- Użytkownik potrafi na jej podstawie podjąć decyzję „oglądać, negocjować lub odpuścić", ale decyzję podejmuje sam.

## Cele i nie-cele

Cele: ceny z aktów notarialnych jako punkt odniesienia dla ofert, przejrzyste ograniczenia danych, działanie na Raspberry Pi bez płatnych usług.

Nie-cele: automatyczna wycena „wartości" mieszkania, rekomendacja zakupu, zastąpienie rzeczoznawcy, pobieranie ogłoszeń z portali bez sprawdzenia ich regulaminów, publikowanie danych osobowych stron transakcji.

Anty-cele (porażka, nawet jeśli program technicznie działa): liczba bez próbki i okresu, mylenie cen ofertowych z transakcyjnymi, traktowanie braku danych jako niskiej ceny, ukrywanie wartości odstających.

## Ograniczenia danych, z którymi trzeba żyć

- RCN nie ma roku budowy. Kryterium „do 10 lat" da się tylko przybliżyć (np. transakcje z rynku pierwotnego z ostatnich lat w okolicy) albo uzupełnić z innego źródła.
- Brak pola o ogrodzie i tarasie. Tekst `lok_inf` czasem wspomina o balkonie lub tarasie.
- Cena za m² dostępna dla około 70% rekordów.
- Data dokumentu to nie pewna data transakcji.
- Darmowe API mScanner daje agregaty (22 dzielnice Katowic), bez osiedli i bez współrzędnych. Ceny ofertowe nowych mieszkań (`mode=asking`) nie zostały jeszcze sprawdzone dla Katowic.

## Etapy

Zgodnie z `docs/superpowers/plans/2026-10-28-mieszkanie100-roadmap.md`. Najbliższy etap: zapytanie „okolica" (`docs/superpowers/plans/2026-10-28-okolica-query.md`), które jest częścią każdej wersji efektu końcowego.

## Otwarte pytania do użytkownika

1. Czy karta mieszkania ma przyjmować też adres z numerem, czy wystarczy sama ulica?
2. Czy interesują Państwa tylko mieszkania, czy także domy i segmenty z ogrodem?
3. Jak często ma przychodzić przegląd okolic i którędy (e-mail, komunikator, strona)?
