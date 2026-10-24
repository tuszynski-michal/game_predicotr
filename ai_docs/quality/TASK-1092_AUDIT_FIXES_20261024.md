---
title: TASK-1092 — poprawki po audycie Claude Code
status: active
---

# Poprawki po audycie TASK-1092

Źródło: [audyt Claude Code, runda 1](TASK-1092_AUDIT_R1_claude-opus-5-5.md), werdykt REVISE, jedna uwaga P1 i trzy P2. Oryginalnego raportu audytora nie zmieniano. Poniższy zapis wykonawcy nie jest nowym niezależnym werdyktem.

| Uwaga | Działanie i weryfikacja wykonawcy |
|---|---|
| P1-1 — zakres replay przyklejony do ręcznych wyszukiwań | Usunięto stan queryScope. Ręczne search bez jawnego scope zawsze używa all_searchable. Replay, restore i odświeżenie konkretnego wyniku przekazują scope jednorazowo w zapytaniu. Test obejmuje approved_only → Nowe szukanie → all_searchable oraz restore approved_only → edycja → all_searchable. |
| P2-1 — zmiana limitu wysyła brudny draft / gubi odświeżenie podczas busy | Zmiana limitu ponawia widoczny snapshot z nowym limitem, bez wysyłania draftu. Kolejka czeka na wszystkie kalkulacje, zachowuje wybrany start i nie czyści draftu. Podczas trwającego search pole limitu pozostaje zablokowane. Osobny test potwierdza dane żądania i oczekiwanie na kalkulator. |
| P2-2 — błąd starego draftu zamiast replay | Dla jawnego options.patterns komunikat pochodzi wyłącznie z walidacji przekazanego snapshotu. Test nieaktywnego symbolu potwierdza właściwy komunikat i brak żądania. |
| P2-3 — zmiana tożsamości resultClient może powodować dodatkowe odczyty modalu | Pozostawiono jako P2. Stan wyszukiwania musi natychmiast usuwać porty korekty z otwartego okna; stabilizacja klienta wymagałaby szerszej zmiany kontraktu wspólnych modalów. Publiczny detailCache ogranicza dodatkowe wywołania, a natywny modal blokuje normalne wywołanie przycisku wyszukiwania w tle. Ryzyko dotyczy dodatkowego odczytu/limitu, nie złego context korekty. Nie deklarowano akceptacji operatora. |

Dodatkowo wykonawca poprawił ostrzeżenie o nierozpoznanych symbolach: w ciągu korzysta z łącznego score, więc obejmuje także wcześniejsze plansze. Osobny test odtwarza trzy wildcardy we wcześniejszej pozycji.

Po poprawkach dedykowane interakcje: 19 PASS, pełny pakiet interakcji 113 PASS (21,55 s), typecheck board-search-ui i lint zmienionych plików UI PASS. Mapa zregenerowana; końcowe docs/mapa/diff sprawdzone przed przekazaniem do operatora.

Wykorzystano oba pierwotne audyty implementacji: A high zakończony timeoutem 480 s, B medium zakończony REVISE. 2026-10-24 operator zatwierdził dodatkową kontrolę poprawek B i jej koszt: medium, maksymalnie 480 s, po PASS zamknięcie i commit. [Runda 2 B zakończyła się PASS](TASK-1092_AUDIT_claude-opus-5-5.md), bez P0/P1; niezależnie potwierdzono poprawki. Jest to trzeci audyt implementacji, nie czwarty audyt planu. Dalszych audytów nie uruchamiano.

Otwarte P2 po R2: P2-3 (dodatkowe odczyty modalu, pozostawienie uznane przez audytora za uzasadnione) oraz P2-4 (statycznie wskazana możliwość drugiego kliknięcia Szukaj po blur nowego limitu przy brudnym wzorze). P2-4 nie zostało odtworzone testem; nie powoduje utraty draftu ani zmiany kontekstu korekty. Obie uwagi odnotowano w Outcome jako znane ograniczenia, bez dalszych zmian kodu po PASS.
