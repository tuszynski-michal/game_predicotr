---
title: TASK-0462 Board area registration acceptance
status: done
---

# TASK-0462 — Odbiór, ręczne korekty i dokumentacja

## Goal

Ocenić standardową i maskowaną rejestrację na ograniczonej próbce rzeczywistych,
source-disjoint ręcznych korekt oraz udokumentować bezpieczny sposób użycia.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/quality/V0_10_KEYPOINT_GEOMETRY_FALLBACK.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Dependencies

- TASK-0458–TASK-0461.

## Scope

- bounded porównanie do 50 ręcznie zweryfikowanych źródeł bez użycia ocenianego
  źródła lub jego duplikatu jako kotwicy;
- przypadek `seq_53119-53127.jpg` jako diagnostyka, dopóki nie ma referencji;
- raport pokrycia, błędu, odrzuceń oraz kosztu;
- kontrola ścieżki 36 narożników → kolejny preflight → kohorta geometrii;
- pełne kontrole zmienionego pionu i dokumentacja operatorska.

## Definition of Done

- raport nie deklaruje jakości bez wystarczającej referencji;
- wariant nie zostaje domyślny bez przejścia bramek;
- odbiór jest ograniczony, odtwarzalny i nie mutuje danych użytkownika;
- testy API, workera, Admina, OpenAPI i build są udokumentowane;
- outcome rozróżnia implementację od potwierdzenia jakości na danych.

## Outcome

- Dodano ograniczone, tylko do odczytu narzędzie porównujące standardową i
  maskowaną rejestrację. Każde oceniane źródło i jego dokładny duplikat są
  wykluczane z kotwic po SHA-256; limit 50 jest wymuszany przed otwarciem bazy.
- W bazie znaleziono 21 kompletnych źródeł / 189 plansz. Oceniono 19 źródeł;
  jedno nie miało pliku managed original, a jedno niezależnej kotwicy.
- Standard rozpoznał 14/19 przy medianie błędu 6,20 px. Maska rozpoznała 13/19
  przy 6,36 px. Łączny czas wzrósł z 27,52 s do 34,87 s (+26,67%).
- `seq_53119-53127.jpg` został sprawdzony z rzeczywistego JPEG-a i zgodnej
  checksummy. Oba warianty odrzuciły go kodem
  `PAGE_GEOMETRY_RED_EDGE_COVERAGE_INSUFFICIENT`; brak ręcznej referencji nie
  pozwala deklarować błędu narożników.
- Wariant nie przeszedł bramek jakości ani wydajności. Pozostaje opcjonalny,
  `standard_v0_10` jest nadal ustawieniem domyślnym.
- Potwierdzono istniejący kontrakt: pełne 36 narożników może zasilić następny
  preflight i kohortę geometrii, ale zapis korekty nie jest treningiem ani
  aktywacją profilu i nie tworzy etykiet symboli.
- Raport i instrukcja porównania oryginału z katalogiem `cut` znajdują się w
  `ai_docs/quality/BOARD_AREA_REGISTRATION_ACCEPTANCE.md`.

### Verification

- 39 testów odbioru rejestracji, preflightu i kohorty geometrii: passed.
- 48 testów kontraktu jobów i API importów: passed.
- 30 testów workera rejestracji i preflightu w końcowym przebiegu: passed.
- 408 testów Admina: passed.
- Ruff dla API, workera i skryptów: passed.
- Mypy dla nowego narzędzia odbiorczego: passed.
- Typecheck Admina: passed.
- OpenAPI i generowany klient: current/passed.
- Produkcyjny build Admina: passed.
- Globalny lint Admina nadal zgłasza dwa wcześniejsze, niezwiązane błędy
  `react-hooks/set-state-in-effect` w
  `geometry-guard-resolution-panel.tsx`. Plik nie został zmieniony w tym pionie;
  zgodnie z zakresem błędy pozostawiono poza commitem.
