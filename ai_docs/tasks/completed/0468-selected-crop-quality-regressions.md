# TASK-0468 — Selected crop quality regressions

## Status

done

## Goal

Odtworzyć trzy rzeczywiste błędy v10 i przygotować niezależne od detektora referencje dla v11.

## Relevant docs

- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-357)
- `ai_docs/quality/SELECTED_CROP_V11_REGRESSIONS.md`

## Dependencies

- TASK-0467; zaakceptowany plan v11, TASK-0468–0472.

## Scope / expected files

- Referencje siedmiu oryginałów: `packages/manual-image-selection-core/test/fixtures/selected-crop-quality.mjs`.
- Read-only runner `scripts/evaluate_selected_crop_quality.mjs`, evaluator i testy w core/test.
- Raport jakości i dokumentacja. Bez zmian detektora, katalogów cut, API i jobów.

## Acceptance criteria / DoD

- SHA-256, dziewięć obszarów plansz i numerów, kompletność i przedziały obu linii dla każdej referencji.
- Podział development/holdout po katalogach; historyczne próbki strojenia wyłącznie development.
- Testy trzech klas błędu i raport v10 na oryginałach.
- Brak oryginału drugiej gry jawnie ogranicza odbiór; nie zastępować go screenshotem.
- Testy, format i typecheck; osobny commit.

## Assumptions

- Limit do 120 nie oznacza minimum 120: początkowy corpus to 7 ręcznie obejrzanych zdjęć, 63 obszary plansz i 63 obszary numerów.
- Bboxy są zachowawczymi oznaczeniami wizualnymi do jakości poziomego pasa, nie subpikselową referencją narożników geometrii.
- Dwuzdjęciowy holdout nie wystarcza do deklaracji jakości całej populacji.

## Verification

- `node --experimental-strip-types --test packages/manual-image-selection-core/test/selected-crop-quality.test.mjs`
- `node --experimental-strip-types scripts/evaluate_selected_crop_quality.mjs "C:\Users\user\Documents\777"`
- Testy i typecheck core; Prettier dla nowych modułów.

## Outcome

- Dodano 7 referencji oryginałów, 63 bboxy plansz i 63 numerów, checksummy,
  przedziały obu linii oraz podział 5 development / 2 holdout po katalogach.
- Odtworzono wszystkie trzy rodzaje błędu v10; snapshoty są oddzielone od
  oczekiwanej geometrii. Testy bez źródeł nie udają wykonania detektora.
- Read-only runner: 7/7 źródeł zgodnych SHA i wymiarami, 7/7 wyników replay
  zgodnych z zapisanym baseline. Niczego nie zapisał w źródłach ani cut.
- Testy skupione 7/7, wszystkie testy core 61/61, typecheck i Prettier OK.
- Nie wdrażano detektora v11. Brak właściwego źródła gry literowej jawnie
  odnotowany; nie podstawiono gry owocowej o tym samym zakresie.
- Dokładna tożsamość drugiego załącznika niepotwierdzona; odnaleziony przez
  manifest oryginał 80074 odtwarza crop samej reklamy. Nie blokuje testu błędu.
- Mały holdout wymaga rozszerzenia przed oceną jakości w 0472. Zaktualizowano
  wymagania, architekturę, CURRENT_STATE, Decision Log i raport jakości.
- Następny task: 0469, dopiero po osobnym poleceniu.
