---
title: TASK-0371 — Pełna korekta strony i podgląd cięć symboli
status: done
release: "0.10"
last_updated: 2026-09-01
---

# TASK-0371 — Pełna korekta strony i podgląd cięć symboli

## Goal

Ułatwić ręczną korektę geometrii strony przez pokazanie wszystkich oczekiwanych
plansz oraz orientacyjnego podziału każdej planszy na komórki 5 × 3, bez
zasłaniania zdjęcia propozycją automatu podczas ponownego wskazywania punktów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/quality/V0_10_VIRTUAL_GEOMETRY_CUTOVER.md`

## Scope

- Zachować dokładnie `expectedBoardCount` edytowalnych propozycji plansz;
  nierozpoznane źródło dostaje pełną siatkę roboczą wyprowadzoną z obrysu
  strony, a nie częściowy wynik.
- Rysować wewnątrz każdego kompletnego quada cztery pionowe i dwie poziome
  linie odpowiadające potencjalnemu podziałowi 5 × 3 po rektyfikacji.
- Ukrywać propozycję automatu po rozpoczęciu trybu `Wyznacz 4 narożniki` albo
  `Wyznacz N plansz osobno`; pokazywać tylko geometrię utworzoną w bieżącym
  trybie ręcznym.
- Zachować obsługę końcowych stron zawierających 1–8 plansz zgodnie z nazwą
  `seq_<start>-<end>`.

## Out of scope

- Promocja `structured_default` lub `virtual_default`.
- Zmiana progów Structured OpenCV, croppera albo inferencji symboli.
- Zmiana schematu bazy lub kontraktu API.

## Acceptance criteria

- [x] Źródło oczekujące na korektę pokazuje 1–9 aktywnych propozycji zgodnie z
  `expectedBoardCount` i pozwala zapisać komplet.
- [x] Każdy widoczny kompletny quad pokazuje projektowany podział 5 × 3.
- [x] Rozpoczęcie obu trybów ręcznego wskazywania ukrywa poprzednią propozycję.
- [x] Ukończone ręcznie quady mogą pokazywać własny podział 5 × 3 przed
  zapisaniem całej strony.
- [x] Testy funkcji geometrii, lint i typecheck zmienionego panelu przechodzą.

## Outcome

Panel zachowuje częściowo wczytane quady i uzupełnia brakujące pozycje z
roboczej siatki strony, dzięki czemu operator zawsze może skorygować komplet
wynikający z `expectedBoardCount`. Dodano projektowe granice 5 × 3 liczone
przez odwzorowanie perspektywiczne tego samego quada, który zostanie zapisany.

Tryby ponownego wskazywania ukrywają poprzednie poligony oraz ich linie.
W `Wyznacz N plansz osobno` ukończone w bieżącej operacji plansze pokazują już
własny podział 5 × 3. Nie zmieniono API, bazy, progów ani rolloutu v0.10.

Weryfikacja:

- 15 skoncentrowanych testów panelu i geometrii — PASS,
- targeted ESLint zmienionych plików — PASS,
- Admin TypeScript typecheck — PASS,
- Admin production build — PASS,
- Prettier dla zmienionych plików i dokumentacji — PASS.

Pełny lint aplikacji nadal wykrywa wcześniejszy, niezwiązany błąd
`react-hooks/set-state-in-effect` w
`unreadable-board-review-workspace.tsx`; plik nie należy do tego zadania i nie
został zmieniony.
