---
title: TASK-0455 Selected image crop provenance and recalculation
status: done
last_updated: 2026-09-05
---

# TASK-0455 — Trwałość, ponowne przeliczenie i czytelny review

## Goal

Utrwalić dokładną proweniencję propozycji auto-cropa v4 i pozwolić
operatorowi jawnie przeliczyć wyłącznie bezpieczne, nieprzejrzane wyniki bez
naruszania ręcznych korekt ani historycznych sesji.

## Scope

- proweniencja policy, klasy, confidence, lokalnych granic, sygnałów i fallbacku
  w shardach wyników;
- jawna akcja przeliczenia nieprzejrzanych wyników nowym detektorem;
- ochrona wyników przejrzanych, poprawionych i zaznaczonych do poprawy;
- badge `Pewne`, `Zachowawcze`, `Szerokie — sprawdź`;
- filtr `Niepewne`;
- trwałe przypięcie polityki przygotowania sesji oraz kompatybilny odczyt
  starszych wyników bez proweniencji.

## Out of scope

- automatyczne przeliczanie istniejących plików `cut`;
- API, PostgreSQL, OCR, obrót i homografia;
- zmiana detektora v4 dostarczonego w TASK-0454.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- nowy wynik zapisuje pełną proweniencję propozycji w swoim shardzie;
- starszy wynik bez proweniencji pozostaje czytelny i nie jest zmieniany bez
  jawnej akcji operatora;
- przeliczenie weryfikuje źródło i bieżący wynik checksumą przez istniejący
  journal;
- ręczna korekta, review i zaznaczenie do poprawy chronią wynik;
- restart zachowuje przypiętą wersję polityki i klasy wyników;
- testy core/Admin, lint, typecheck i build zmienionego pionu są zielone.

## Outcome

- Rozszerzono wynik i journal o pełną proweniencję propozycji v4: klasę,
  confidence, lokalne granice obu rodzin sygnału, wykorzystane pasy, IoU,
  rozszerzenie granicy oraz reason code fallbacku.
- Nowe sesje przypinają v4, a historyczny brak wersji pozostaje jawnym stanem
  legacy. Brakujące wyniki nie są wtedy przygotowywane nową polityką bez
  działania operatora.
- Dodano checksum-bound przeliczenie wyłącznie wyników nieprzejrzanych,
  niepoprawionych i niezaznaczonych do poprawy; po przejściu na v4 przygotowane
  zostają również brakujące pliki.
- Dodano filtr `Niepewne` i badge klas propozycji. Historyczne wyniki bez
  proweniencji nadal są wyświetlane.

### Verification

- `npm run test --workspace @game-predictor/manual-image-selection-core` —
  47/47 passed.
- skoncentrowane testy Admina storage/workspace/atlas — 17/17 passed.
- typecheck core i Admin — passed.
- skoncentrowany ESLint zmienionych modułów Admina — passed.
- `npm run admin:build` — passed.
- Pełny lint Admina nadal wskazuje dwa wcześniejsze błędy
  `react-hooks/set-state-in-effect` w
  `geometry-guard-resolution-panel.tsx`; plik nie należy do zakresu TASK-0455.
