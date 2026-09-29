---
title: TASK-0741 — T2 — ślepa ocena operatora dla biblioteki wzorców
status: blocked
last_updated: 2026-09-29
---

# TASK-0741 — T2 — ślepa ocena operatora dla biblioteki wzorców

## Status

`blocked` — narzędzia gotowe i zaudytowane; czeka na oceny operatora.

## Goal

Operator ocenia 200 oczekujących komórek bez widocznej propozycji, a narzędzie
porównuje jego oceny z zamrożonymi wcześniej propozycjami biblioteki i
rozstrzyga bramkę etapu A.

## Context

Pomiar T1 opiera się na komórkach już poprawionych przez operatora, czyli na
próbie wybiórczej. Bramka etapu wymaga oceny na komórkach, których operator
jeszcze nie widział z propozycją.

## Dependencies / entry conditions

- TASK-0740 ukończone: moduł, skrypt i biblioteka.
- Wymagany udział operatora. Bez jego ocen task pozostaje `blocked`.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo; model sesji zmienił się z
`claude-fable-5-1`). Niezależny review `claude-opus-5-5`, `high`, osobny agent. Eskalacja: wynik poniżej bramki wymaga analizy
pomyłek per symbol przed propozycją zmian.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SYMBOL_REFERENCE_LIBRARY_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-464)

## Scope

- Podkomenda zamrażająca 200 komórek (25 na przewidziany symbol) wraz z
  propozycjami i sumami pikseli.
- Lokalny plik HTML bez serwera i bez połączeń sieciowych: wycinek, kontekst
  planszy, wybór symbolu albo stanu `nieczytelny`, `zasłonięty`, `zła siatka`,
  eksport ocen do pliku JSON.
- Podkomenda porównująca oceny z propozycjami.

## Out of scope

- Zapis ocen do bazy. Oceny z tego taska nie są weryfikacją komórek w
  aplikacji.
- Publikowanie zdjęć poza lokalny komputer.

## Acceptance criteria

- [x] Plik oceny nie zawiera propozycji biblioteki ani predykcji modelu.
- [x] Zamrożone propozycje mają sumę kontrolną; porównanie odrzuca plik ocen
  dla innego zamrożenia.
- [ ] Raport: zgodność pewnych propozycji ogółem i per symbol, pokrycie,
  osobno komórki oznaczone jako zasłonięte, nieczytelne i zła siatka.
- [ ] Bramka: co najmniej 98% ogółem i co najmniej 95% dla każdego symbolu
  z co najmniej 10 pewnymi propozycjami; symbole z mniejszą liczbą są
  raportowane jako niepotwierdzone.
- [ ] Niezależny audyt bez otwartych P0–P2; osobny commit, Outcome,
  CURRENT_STATE.

## Technical notes

- Kolejność komórek w pliku oceny jest losowa względem symbolu (stałe ziarno),
  aby kolejność nie zdradzała predykcji.
- Oceny `nieczytelny`, `zasłonięty` i `zła siatka` nie liczą się jako błąd
  propozycji; są raportowane osobno.
- Komórki z próbki, które operator w międzyczasie zweryfikuje w Adminie, są
  porównywane także z decyzją z bazy i raportowane osobno.

## Expected files

- Istniejące po T1: `scripts/evaluate_symbol_reference_library.py`
  (nowe podkomendy `blind-sample`, `compare`).
- Nowe (proponowane): sekcja T2 w
  `ai_docs/quality/SYMBOL_REFERENCE_LIBRARY_STAGE_A.md`.

## Test cases

- Plik ocen dla innego zamrożenia → błąd.
- Ocena `zasłonięty` przy pewnej propozycji → poza mianownikiem zgodności.
- Brak oceny części komórek → raport podaje liczbę ocenionych; bramka wymaga
  kompletu.

## Verification

Komendy powstają w T1 i są zapisywane w raporcie jakości po ich uruchomieniu.

## Risks / open questions

- 25 komórek na symbol daje szerokie przedziały niepewności per symbol.
- Pytanie O1 planu wpływa na interpretację ocen zasłoniętych komórek.

## Outcome

Stan częściowy: narzędzia i próbka gotowe, brak ocen operatora. Task nie
jest ukończony i nie trafia do `completed/`.

### Changed

- `scripts/evaluate_symbol_reference_library.py`: podkomendy `blind-sample`
  (zamrożenie próbki, lokalna strona oceny) i `compare` (porównanie ocen,
  bramka etapu A, opcjonalny odczyt późniejszych decyzji z Admina).
  Wspólny odczyt bazy i budowa biblioteki wydzielone z `evaluate` bez zmiany
  jego wyników.
- `scripts/symbol_reference_blind_review.html`: szablon strony offline
  (CSP bez sieci, postęp w `localStorage`, eksport pliku ocen, klawisze
  1–8 oraz N/Z/S, bez identyfikatorów komórek na ekranie).
- Testy porównania, strony i wykluczeń w
  `services/worker/tests/test_evaluate_symbol_reference_library_script.py`.

### Verification results

- 27 testów PASS; Ruff check/format i mypy `--strict` PASS.
- Próbka: 200 komórek, po 25 na przewidziany symbol z pasma 60–80%, z 24
  importów; 0 komórek wspólnych z 400 komórkami raportu T1 i z 50 komórkami
  pokazanymi w rozmowie. `blind-frozen.json` SHA
  `0bc381166236d40259f62f61aabfcde101fcfa60444c3d540e2ead1d8d384582`,
  identyczny w dwóch uruchomieniach; kolejne uruchomienie z innymi
  parametrami w tym samym katalogu kończy się błędem
  `SYMBOL_REFERENCE_BLIND_FROZEN_EXISTS`.
- Strona sprawdzona w przeglądarce przez lokalny serwer: ocena klawiszem,
  ignorowanie Ctrl+0 i przytrzymania, brak UUID na ekranie; testowe oceny
  usunięte z pamięci przeglądarki.
- `compare` sprawdzony mechanicznie na sztucznym pliku 20 ocen (nie są to
  dane operatora ani wynik bramki).
- Niezależny audyt `claude-opus-5-5`: PASS bez P0–P2. Poprawiono P3:
  klawiatura, ochrona przed nadpisaniem zamrożenia, faktyczna liczność
  próbki, lista dozwolonych kodów z modelu, ukrycie UUID. Pozostaje P3:
  bramka przechodzi, gdy żaden symbol nie ma 10 pewnych propozycji —
  raport musi to wtedy nazwać wprost.

### Not completed

- Oceny operatora i wynik bramki etapu A.

### Recommended next task

- Operator ocenia `blind-review.html` i przekazuje plik ocen; potem
  `compare --with-database` i domknięcie TASK-0741.
