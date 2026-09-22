---
title: V1.2 Mumie geometry diagnosis
status: done
---

# TASK-0612 — Diagnoza geometrii V1.2 dla Mumii

## Status

`done`

## Goal

Utrwalić odtwarzalną diagnozę czterech zdjęć Mumii, która rozdziela wykrycie
zewnętrznych plansz od siatki 3 × 5 symboli i określa minimalny kontrakt V1.2.

## Context

Obecny wariant V1.1 korzysta z czerwonego wsparcia krawędzi po rejestracji do
kotwicy. Mumie mogą przejść przez ręczną kotwicę, ale jej zapis zawiera tylko
jeden quad na planszę. Nie ma więc danych do uczenia niezależnych odstępów
między ramką planszy a siatką symboli.

## Dependencies / entry conditions

- Dostępne są cztery lokalne źródła `C:\Users\tuszy\Documents\mumie\seq_*.jpg`.
- Bieżący manifest preflightu Mumii i jego ręczna korekta są dostępne lokalnie.
- Nie zmieniamy istniejących wariantów ani ich danych.

## Recommended execution

gpt-5.6-terra / high. Zadanie jest diagnozą rzeczywistych źródeł i istniejących
kontraktów. Przed commitem niezależny review wykonuje gpt-6-astra / medium;
eskalacja jest konieczna tylko, gdy raport proponuje zmianę istniejącego
kontraktu zamiast opisania brakującego V1.2.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Odtworzyć wynik klasycznego detektora, manifestu preflightu i ręcznej korekty
  dla czterech zdjęć Mumii.
- Udokumentować granicę obecnego pojedynczego quada i wymagany rozdział
  `boardFrameQuad` / `symbolGridQuad` w V1.2.
- Zapisać raport jakościowy wraz z zakresem materiału i ograniczeniami.

## Out of scope

- Zmiana zachowania istniejących wariantów, danych gry, importów lub plików
  źródłowych.
- Modyfikacja niezwiązanych modułów geometrii.

## Acceptance criteria

- [x] Raport wskazuje wynik detekcji wszystkich czterech źródeł Mumii.
- [x] Raport rozdziela dane automatycznej rejestracji od ręcznego quada.
- [x] Raport wskazuje, dlaczego obecny zapis nie może nauczyć czterech
      niezależnych marginesów.
- [x] Audyt potwierdza brak zmian poza dokumentacją T01.

## Technical notes

`ImagePageGeometryOverride.final_quads` jest dziś pojedynczą geometrią
wykorzystywaną do rysowania planszy i równych linii symboli. V1.2 nie może
interpretować jej niejawnie jako równocześnie ramki i siatki. Przykłady
treningowe V1.2 muszą zawierać dwie jawne, ręcznie zatwierdzone geometrie.

## Expected files

- Nowy: `ai_docs/quality/V1_2_MUMIE_GEOMETRY_DIAGNOSIS.md`.
- Nowy: ten task, po ukończeniu przeniesiony do `ai_docs/tasks/completed/`.
- Istniejący: `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Cztery zdjęcia Mumii → wynik klasycznego detektora i manifestu zapisany
  oddzielnie dla każdego źródła.
- Ręczna korekta jednego źródła → potwierdzenie, że zapis ma jeden quad na
  planszę i nie zawiera niezależnej siatki symboli.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr
git diff --check
git diff --name-only
```

## Risks / open questions

- Cztery zdjęcia wystarczają do diagnozy, ale nie stanowią odbioru jakości
  przyszłego silnika.

## Outcome

### Changed

- Dodano odtwarzalny raport czterech zdjęć Mumii, przypięty do manifestu,
  źródeł i ręcznej decyzji.
- Udokumentowano, że obecny override ma tylko jeden quad planszy i nie daje
  danych do niezależnego uczenia ramki oraz siatki symboli.

### Verification results

- Klasyczny detektor z domyślną maską czerwieni: 0 / 4 stron z automatycznie
  wykrytymi planszami.
- Manifest V1.1 po jednej ręcznej kotwicy: 4 / 4 strony mają 9 quadów;
  trzy automatyczne wpisy zachowują mierzone wsparcie czerwonych krawędzi.
- `git diff --check` przeszedł.
- Audyt Astra Medium: pierwsze P2 dotyczące braku identyfikacji dowodów
  poprawiono; końcowy re-audyt nie wykazał P0–P3.

### Not completed

- Nie ustalono progów V1.2 ani nie zmieniono wykonywania importu; to T02.

### Documentation updates

- Dodano `ai_docs/quality/V1_2_MUMIE_GEOMETRY_DIAGNOSIS.md`.
- Zaktualizowano `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- T02: wersjonowany wariant V1.2 z kontrastowym obrysem oraz dwoma quadami
  zatwierdzanymi per gra.
