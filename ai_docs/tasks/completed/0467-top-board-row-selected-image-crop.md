---
title: Top-board-row guided selected image crop
status: done
task_id: TASK-0467
---

# TASK-0467 — Top-board-row guided selected image crop

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/CURRENT_STATE.md`

## Cel

Wyznaczać górną granicę lokalnego cropa z trzech niezależnych plansz
pierwszego rzędu, zamiast polegać wyłącznie na szerokim kolorze panelu.

## Zakres

- wersjonowana polityka v10;
- detekcja trzech zgodnych ramek górnego rzędu na istniejącym podglądzie;
- bezpieczny bufor i fail-safe do polityki szerokiego panelu;
- wznawialne narzędzie operatorskie do przygotowania kolejnych katalogów;
- testy domenowe i ograniczona weryfikacja na rzeczywistych zdjęciach;
- aktualizacja dokumentacji.

## Poza zakresem

- zmiana dolnej bramki;
- OCR, geometria dziewięciu plansz i klasyfikacja symboli;
- automatyczne usuwanie istniejących katalogów użytkownika.

## Testy

- zgodny górny rząd z mylącym panelem wypłat;
- brak trzech ramek zachowuje bezpieczny wynik bazowy;
- pochylenie i nierówne rozmiary w dopuszczalnym zakresie;
- testy, typecheck i format zmienionego pakietu;
- dwie rzeczywiste próbki przed uruchomieniem katalogów.

## Definition of Done

- wynik v10 jest fingerprintowany i odtwarzalny;
- słaby dowód nie zaciska cropa;
- źródła i ręczne decyzje nie są modyfikowane;
- operator może wznowić przerwany przebieg katalogu;
- Outcome zawiera pomiary i dokładne wykonane operacje.

## Outcome

- Dodano fingerprintowaną politykę v10 z detekcją trzech plansz pierwszego
  rzędu i bezpiecznym fallbackiem v9.
- Dodano test mylącego panelu wypłat oraz zachowano wszystkie testy regresyjne.
- Dwie rzeczywiste próbki 1080×1920 uzyskały `topY=589` i `topY=454`; oba
  wyniki zachowały komplet dziewięciu plansz i zostały zaakceptowane do
  kontrolowanego ponownego przebiegu.
- Dodano wznawialne narzędzie katalogowe ze stanem shardowanym po 64 wyniki.
- `npm run test --workspace @game-predictor/manual-image-selection-core` — 54/54.
- `npm run typecheck --workspace @game-predictor/manual-image-selection-core` — OK.
- Smoke test narzędzia — 2/2 pliki, zgodny manifest i fingerprint v10.
