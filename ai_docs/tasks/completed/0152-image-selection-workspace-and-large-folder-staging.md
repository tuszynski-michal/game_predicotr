---
title: TASK-0152 image selection workspace and large folder staging
status: done
release: "0.4"
last_updated: 2026-08-02
---

# TASK-0152 — Image selection workspace and large folder staging

## Status

`done`

## Goal

Dodać czwarty workspace `Selekcja zdjęć` i bezpiecznie stagingować do 30 000
JPEG-ów bez blokowania UI ani przenoszenia stanu pomiędzy grami.

## Context

Istniejący browser-native folder input jest właściwą granicą bezpieczeństwa,
ale selekcja wymaga większego limitu, resumable uploadu i osobnego purpose bez
duplikowania całej implementacji importu layoutów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_07_0_EXECUTION_PLAN.md`
- `ai_docs/tasks/0151-image-selection-domain-contract-and-storage.md`

## Scope

- dodać czwarty workspace i deterministyczne odtwarzanie z URL,
- zachować aktywną grę bez dodatkowego rozbieżnego selecta,
- uogólnić istniejący upload folderu o poświadczony purpose
  `photo_selection`, zachowując zgodność `layout_import`,
- przesyłać pliki w bounded concurrency z licznikami plików i bajtów,
- obsłużyć anulowanie, odświeżenie UI oraz wznowienie nieskończonego uploadu,
- przenieść własność sfinalizowanego stagingu do runu selekcji,
- izolować upload, token i komunikaty per gra/run.

## Out of scope

- analiza obrazu,
- automatyczne grupowanie,
- manualny wybór zdjęcia,
- handoff do pełnego importu.

## Acceptance criteria

- [x] Admin pokazuje cztery workspace'y bez poziomego overflow przy 1366×768.
- [x] URL odtwarza `Selekcja zdjęć` i aktywną grę po odświeżeniu.
- [x] Folder picker jest wywoływany synchronicznie z gestu użytkownika.
- [x] UI nie wczytuje wszystkich bajtów folderu jednocześnie do pamięci.
- [x] Postęp rozróżnia liczbę plików i bajty, a błąd jednego uploadu można
      ponowić bez wybierania folderu od początku w tej samej sesji.
- [x] Purpose tokenu blokuje użycie stagingu selekcji jako zwykłego importu
      przed ukończeniem handoff.
- [x] Zmiana gry nie przenosi aktywnego uploadu ani błędu.
- [x] Źródłowy folder nie jest modyfikowany.

## Technical notes

Nie przywracać backendowego dialogu Windows. Standardowy `<input directory>` i
kontrolowany loopback upload pozostają obowiązującą granicą D-118.

## Expected files

- `apps/admin/src/`
- `apps/admin/test/`
- `services/api/src/game_predictor_api/application/image_imports.py`
- `services/api/src/game_predictor_api/api/`
- `services/api/tests/test_image_imports_api.py`
- `packages/admin-api-client/`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm.cmd test --workspace @game-predictor/admin
npm.cmd run typecheck --workspace @game-predictor/admin
npm.cmd run lint --workspace @game-predictor/admin
.venv\Scripts\python.exe -m pytest services/api/tests/test_image_imports_api.py -q
npm.cmd run openapi:check
```

## Risks / open questions

- Limit 30 000 musi być wsparty limitem łącznych bajtów i wolnego miejsca, a
  nie samym zwiększeniem stałej liczby plików.

## Outcome

Ukończono 2026-08-03.

- Czwarty workspace zachowuje aktywną grę w URL, odtwarza ostatni run per gra i
  używa standardowego browser-native directory inputu.
- Upload porządkuje ścieżki naturalnie, przesyła najwyżej cztery JPEG-i
  równolegle, raportuje pliki i bajty, wykonuje trzy ograniczone próby oraz
  wznawia tylko brakujące indeksy w tej samej sesji.
- Backend utrwala checkpoint stagingu na 24 godziny, egzekwuje osobne limity
  30 000 plików, łącznych bajtów i wolnego miejsca oraz wiąże token z
  `photo_selection` i konkretną grą. Token nie może uruchomić zwykłego importu.
- Responsywny kontrakt ma cztery kolumny na desktopie, dwie poniżej 980 px i
  jedną poniżej 760 px; produkcyjny build potwierdził poprawną kompilację.
- Weryfikacja: Admin 148/148, API 14/14, typecheck i lint Admina, Ruff,
  `openapi:check` oraz produkcyjny build. Interaktywny serwer testowy był
  sprzątany po kontrolowanych próbach runnera; nie pozostawiono procesów.
