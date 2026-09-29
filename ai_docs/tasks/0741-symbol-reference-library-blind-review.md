---
title: TASK-0741 — T2 — ślepa ocena operatora dla biblioteki wzorców
status: todo
last_updated: 2026-09-29
---

# TASK-0741 — T2 — ślepa ocena operatora dla biblioteki wzorców

## Status

`todo`

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

`claude-fable-5-1`, reasoning `high` (warunkowo). Niezależny review
`claude-opus-5-5`, `high`. Eskalacja: wynik poniżej bramki wymaga analizy
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

- [ ] Plik oceny nie zawiera propozycji biblioteki ani predykcji modelu.
- [ ] Zamrożone propozycje mają sumę kontrolną; porównanie odrzuca plik ocen
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

Wypełnia agent po pracy.
