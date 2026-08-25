---
title: TASK-0251 rules creation response reconciliation
status: done
release: "0.7"
last_updated: 2026-08-21
---

# TASK-0251 — Uzgodnienie wyniku tworzenia reguł

## Status

`done`

## Goal

Zapewnić, że tworzenie pierwszej wersji reguł zawsze opuszcza stan ładowania,
a skuteczny zapis jest pokazany także po opóźnionej lub utraconej odpowiedzi
POST.

## Context

Właściciel kliknął `Utwórz reguły`, lecz UI pozostał w stanie ładowania i nie
pokazał wyniku. Kontrola API potwierdziła, że draft reguł v1 został faktycznie
utworzony. Obecna akcja nie ma ograniczonego czasu oczekiwania ani uzgodnienia
stanu z listą reguł po niejednoznacznym wyniku mutacji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- ograniczyć czas oczekiwania na żądania katalogu i zapisu reguł,
- po niejednoznacznym wyniku tworzenia odczytać reguły gry i rozpoznać
  utworzony draft po grze, statusie, wymiarach i koszcie spinu,
- bezwarunkowo zwalniać blokadę submitu po sukcesie i błędzie,
- pokazywać kontrolowany błąd zamiast nieskończonego loadingu,
- dodać regresję skutecznego POST z utraconą odpowiedzią oraz timeoutu.

## Out of scope

- zmiana wersjonowania reguł lub ograniczeń liczby draftów,
- zmiana endpointów i OpenAPI,
- publikacja, paylines, payouty i przeliczanie layoutów,
- globalna przebudowa wszystkich requestów Admina.

## Acceptance criteria

- [x] Skuteczna odpowiedź tworzy i pokazuje draft jak dotychczas.
- [x] Utracona odpowiedź po skutecznym zapisie jest uzgadniana przez GET i nie
      zachęca do utworzenia kolejnej wersji.
- [x] Brak odpowiedzi kończy loading w ograniczonym czasie i pokazuje błąd.
- [x] Stabilny błąd API nie jest maskowany przez uzgodnienie.
- [x] Blokada submitu jest zwalniana w `finally`.
- [x] Testy Admina, lint i typecheck przechodzą.

## Technical notes

Uzgodnienie może zaakceptować wyłącznie najnowszy draft tej samej gry z
dokładnie zgodnymi `rows`, `columns` i `spinCost`. Nie wolno uznać podobnej ani
opublikowanej wersji za wynik bieżącej komendy.

## Expected files

- `apps/admin/src/features/rules/rules-version-actions.ts`
- `apps/admin/src/features/rules/rules-version-catalog.tsx`
- `apps/admin/test/rules-version-actions.test.mjs`
- `apps/admin/test/rules-workspace-contract.test.mjs`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm.cmd test --workspace @game-predictor/admin
npm.cmd run lint --workspace @game-predictor/admin
npm.cmd run typecheck --workspace @game-predictor/admin
```

## Risks / open questions

- Timeout nie anuluje historycznego requestu w wygenerowanym kliencie. Wynik
  domenowy pozostaje bezpieczny dzięki read-only reconciliation przed
  umożliwieniem następnej próby.

## Outcome

### Changed

- Żądania listy i zapisu reguł mają ograniczenie 15 sekund.
- Niejednoznaczny create uzgadnia wynik przez listę reguł i akceptuje wyłącznie
  zgodny draft tej samej gry.
- Submit zawsze zwalnia blokadę mutacji oraz `isSubmitting` w `finally`.
- Stabilne błędy API nadal są pokazywane bez próby ich maskowania.

### Verification results

- Admin tests: `216 passed`.
- Admin typecheck: passed.
- Prettier dla zmienionych plików: passed.
- ESLint dla zmienionych plików: passed.
- Rzeczywisty lokalny odczyt pokazał bieżący draft v2 po zakończeniu loadingu.

### Not completed

- Pełny `npm run lint --workspace @game-predictor/admin` nie zwrócił wyniku
  przez 60 sekund i został przerwany; pozostawione procesy potomne zakończono.
  Celowany ESLint całego zmienionego pionu przeszedł.
- Nie usunięto dwóch istniejących draftów v1/v2. To dane domenowe wymagające
  osobnej decyzji właściciela.

### Documentation updates

- Zaktualizowano `CURRENT_STATE.md` i zarchiwizowano TASK-0251.

### Recommended next task

- Ustalić, czy historyczny pusty draft v1 ma pozostać do audytu, czy otrzymać
  osobną bezpieczną akcję porządkową.
