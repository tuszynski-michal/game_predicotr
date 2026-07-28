---
title: TASK-0048 Manual import administration UI
status: done
last_updated: 2026-07-28
---

# TASK-0048 — Manual import administration UI

## Status

`done`

## Goal

Udostępnić w lokalnym panelu administracyjnym kompletny, typowany przepływ
przeglądu raportu integralności ręcznego importu oraz jawnego odrzucenia jego
nieopublikowanego stagingu.

## Context

TASK-0047 udostępnił dokładny raport integralności i stronicowany podgląd
znormalizowanych wierszy. M4.3 wymaga teraz interfejsu, który pozwoli operatorowi
rozpoznać blokady i ostrzeżenia, filtrować błędy, sprawdzić kolejność row-major
oraz bezpiecznie odrzucić wskazany import.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_04_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- ekran ręcznego importu korzystający wyłącznie z generowanego klienta API,
- wybór zakończonej walidacji importu i odczyt raportu integralności,
- czytelne statystyki, blokady i ostrzeżenia niewyrażone wyłącznie kolorem,
- filtry statusu i kodu błędu oraz stronicowany podgląd wierszy,
- podgląd poprawnego layoutu w kolejności row-major,
- jawne odrzucenie dokładnie wskazanego nieopublikowanego stagingu po
  potwierdzeniu,
- stabilne stany loading, empty, error i success,
- testy API, klienta i panelu oraz aktualizacja dokumentacji.

## Out of scope

- publikacja dataset version,
- ręczna naprawa pojedynczych rekordów,
- OCR, import obrazów i edycja SQL,
- zmiana semantyki raportu integralności z TASK-0047.

## Acceptance criteria

- [ ] Operator może wskazać zakończoną walidację importu i zobaczyć dokładne
      statystyki, blokady oraz ostrzeżenia.
- [ ] Luki i duplikaty numerów są opisane jako blokujące, a duplikaty sygnatur
      jako dozwolone ostrzeżenie.
- [ ] Wiersze można filtrować po poprawności i kodzie błędu oraz pobierać
      kolejnymi stronami bez numerowanej paginacji offsetowej.
- [ ] Poprawny layout można obejrzeć jako planszę odpowiadającą wymiarom reguł i
      kolejności row-major.
- [ ] Odrzucenie wymaga wskazania celu i osobnego potwierdzenia, nie usuwa
      opublikowanego datasetu i nie może zostać wykonane podwójnie.
- [ ] UI ma jawne loading, empty, error i success oraz działa przy szerokości
      mobilnej panelu.
- [ ] OpenAPI i generowany klient pozostają źródłem typów odpowiedzi.
- [ ] Testy, lint, typecheck i produkcyjny build przechodzą.

## Technical notes

- Odrzucenie dotyczy wyłącznie surowego i znormalizowanego stagingu wskazanego
  łańcucha import → walidacja. Joby pozostają trwałym audytem.
- Usunięcie jest kontrolowaną operacją domenową; endpoint przyjmuje identyfikator
  walidacji, a backend sam rozstrzyga powiązany import.
- Lista wierszy używa istniejącego kursora `after_line_number`.

## Expected files

- `apps/admin/src/**`
- `services/api/src/game_predictor_api/**`
- `services/api/tests/**`
- `packages/admin-api-client/**`
- `ai_docs/**`

## Verification

```powershell
npm run quality
npm --workspace @game-predictor/admin run build
```

## Risks / open questions

- Fizyczne benchmarki Android i formalna bramka G3 pozostają odroczone na mocy
  D-041 i nie blokują tego pionu.

## Outcome

Wypełni agent po pracy.

### Changed

- Dodano sekcję `Import layoutów` z tworzeniem typowanych jobów importu i
  walidacji, wyborem ukończonego raportu oraz stabilnymi stanami loading, empty,
  error i success.
- Raport pokazuje dokładne statystyki, wszystkie tekstowe checki, ograniczone
  próbki luk i grup duplikatów, filtry statusu/kodu błędu oraz keyset pagination
  po `line_number`.
- Poprawny wiersz jest prezentowany jako plansza row-major o wymiarach reguł i
  z etykietami katalogu symboli.
- Dodano `DELETE /layout-import-validations/{validationJobId}/staging`,
  typowany kontrakt OpenAPI i metodę generowanego klienta.
- Odrzucenie wymaga przepisania pełnego `importJobId`, usuwa wszystkie
  znormalizowane wiersze powiązanego importu przed surowymi, zachowuje joby i
  blokuje staging używany przez aktywną walidację albo dataset.

### Verification results

- `336 passed, 12 skipped` w pełnym standardowym zestawie Python; skipy to 11
  testów wymagających jawnego włączenia PostgreSQL oraz 1 ograniczenie symlinka
  Windows.
- `11 passed` w pełnej fizycznej macierzy integracji PostgreSQL, w tym raport i
  odrzucenie stagingu; ponowienie użyło lokalnego `--basetemp` z powodu
  niezależnego błędu uprawnień globalnego katalogu tymczasowego Windows.
- Ruff: bez błędów.
- mypy: bez błędów w 109 plikach źródłowych.
- OpenAPI export i kontrola driftu generowanego klienta: aktualne.
- klient API: 12/12 testów; panel: 64/64 testy.
- TypeScript typecheck klienta i panelu oraz produkcyjny build Next.js: zaliczone.
- Browser smoke lokalnego panelu: sekcja i empty state renderują się bez błędów
  konsoli; przy override 390 px dokument miał `clientWidth = scrollWidth = 375`
  i responsywne formularze w jednej kolumnie.

### Not completed

- Nie uruchamiano publikacji datasetu; to zakres TASK-0049.
- Nie wykonywano fizycznych benchmarków Android ani formalnej bramki G3,
  odroczonych na mocy D-041.

### Documentation updates

- Zaktualizowano wymagania panelu i importu, kontrakt API, architekturę,
  strategię testów, plan M4, Decision Log (D-047) oraz `CURRENT_STATE.md`.
- Zaliczono G4.3.

### Recommended next task

- `TASK-0049 — Transactional dataset publication from staging`.
