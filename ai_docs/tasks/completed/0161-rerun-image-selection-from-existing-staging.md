---
title: TASK-0161 rerun image selection from existing staging
status: done
release: "0.4"
last_updated: 2026-08-04
---

# TASK-0161 — Ponowne uruchomienie selekcji z istniejącego stagingu

## Status

`done`

## Goal

Pozwolić użytkownikowi uruchomić aktualną wersję selektora dla wcześniej
załadowanego, niezmiennego zestawu zdjęć bez ponownego przesyłania plików.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`

## Scope

- dodać idempotentny endpoint rerunu na podstawie istniejącego runu,
- przed utworzeniem joba zweryfikować obecność i checksum manifestu stagingu,
- użyć aktualnego fingerprintu selektora i zachować historyczny run bez zmian,
- dodać w karcie runu akcję `Przelicz ponownie załadowane zdjęcia`,
- przełączyć widok i polling na nowy albo już istniejący run aktualnej wersji,
- zaktualizować OpenAPI, klienta, testy i dokumentację.

## Out of scope

- ponowny upload plików,
- automatyczne uruchomienie wielogodzinnego joba bez akcji użytkownika,
- usuwanie historycznych runów i ich decyzji,
- wymuszanie nowego runu dla identycznego manifestu i identycznego fingerprintu.

## Acceptance criteria

- [x] istniejący staging 32 079 zdjęć może utworzyć run v5 bez uploadu,
- [x] brakujący albo zmieniony staging kończy się czytelnym konfliktem przed jobem,
- [x] ponowne kliknięcie dla tej samej wersji jest idempotentne,
- [x] UI zapisuje nowy run dla aktywnej gry i uruchamia bounded polling,
- [x] testy API, klienta i kontraktu Admina przechodzą.

## Expected files

- `services/api/src/game_predictor_api/application/image_selections.py`
- `services/api/src/game_predictor_api/api/image_selections.py`
- `services/api/src/game_predictor_api/main.py`
- `services/api/tests/test_image_selections.py`
- `apps/admin/src/features/image-selection/image-selection-workspace.tsx`
- `apps/admin/test/image-selection-workspace-contract.test.mjs`
- `packages/admin-api-client/openapi/openapi.json`
- `packages/admin-api-client/src/generated/`
- `packages/admin-api-client/src/index.ts`
- `packages/admin-api-client/test/client.test.mjs`

## Outcome

Dodano `POST /api/v1/admin/image-selections/{run_id}/rerun`. Endpoint nie
przyjmuje ścieżki ani manifestu z UI: odczytuje historyczny run, sprawdza
`browser-selections/<sourceSelectionId>/_browser_manifest.json` i porównuje jego
SHA-256 przed utworzeniem idempotentnego runu aktualnego selektora.

Admin pokazuje akcję `Przelicz ponownie załadowane zdjęcia`, przełącza bieżący
run i lokalny kontekst gry na odpowiedź serwera oraz rozpoczyna istniejący
bounded polling. Szczegóły techniczne pokazują skrócony fingerprint selektora.

Rzeczywisty staging `a34c92da-87fd-4245-a0c9-29ee0f6c39c9` nadal zawiera
32 079 zdjęć i cztery pliki techniczne, zajmuje około 7,55 GB, a jego manifest
ma zgodny SHA-256
`15f38e6e0f1f7084ec6a6f51bd010747348f806844a04081ab52f203d98fef8e`.
Ponowny upload nie jest potrzebny. Wielogodzinny job nie został uruchomiony
automatycznie; pozostaje pod jawną akcją użytkownika.

Weryfikacja: 11 testów API, 31 testów klienta, 165 testów Admina, Ruff, ESLint,
TypeScript i kontrola aktualności OpenAPI przeszły. Pełny mypy API pozostaje
zablokowany przez trzy istniejące błędy w `local_admin.py` i `main.py`, niezwiązane
z tym pionem; zmienione zachowanie jest pokryte testami wykonawczymi i Ruff.
