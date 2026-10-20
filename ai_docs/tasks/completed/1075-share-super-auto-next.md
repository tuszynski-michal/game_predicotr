---
title: Restore shared super game series advance after save
status: done
last_updated: 2026-10-20
---

# TASK-1075 — Automatyczne przejście po zapisie super symbolu w udostępnianiu

## Status

`done`

## Goal

Przywrócić automatyczne otwieranie następnej serii bez super symbolu po udanym zapisie super symbolu odbiorcy linku.

## Context

Operator 2026-10-20 polecił przywrócić zachowanie wyłączone przez TASK-1062. Obecnie modal przekazuje `advanceAfterSave={false}`, mimo że wspólny panel domyślnie przechodzi dalej.

## Dependencies / entry conditions

- Zmiana na gałęzi `codex/share-super-auto-next`, od `main` v1.7.448.
- Numery 1072–1074 zajmuje równoległa gałąź `codex/777a2-symbol-quality`.
- Brak pytań blokujących. „Następna plansza” oznacza przywrócenie istniejącego przejścia do wyzwalacza następnej serii bez super symbolu.

## Recommended execution

Wykonanie w bieżącej sesji Codex. Mała zmiana konfiguracji wspólnego komponentu i test interakcji; bez osobnego planu i audytu krzyżowego. Rozszerzenie API albo zmiana reguł wyboru następnej serii wymaga ponownej oceny zakresu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — widok serii supergry odbiorcy.
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` — granica zdalnego Reviewera.
- `ai_docs/architecture/CODE_MAP.md`

## Scope

- Włączyć istniejące automatyczne przejście w modalu udostępniania.
- Zaktualizować regresję interakcji i wymagania.

## Out of scope

- Zmiany API, danych, migracje, restart usług, scalenie i push.
- Zmiana nawigacji Admina oraz algorytmu wyboru następnej serii.

## Acceptance criteria

- [x] Po udanym zapisie symbolu modal otwiera następną serię bez symbolu i pokazuje potwierdzenie zapisu.
- [x] W trakcie zapisu ani po błędzie nie przechodzi dalej; brak kolejnej serii zachowuje dotychczasową obsługę.
- [x] Zamknięcie modalu po zapisie odświeża wyniki wyszukiwania.
- [x] Testy zmienionego pionu, lint, typecheck, format, docs:check i code-map:check przechodzą.

## Technical notes

Usunąć nadpisanie `advanceAfterSave={false}` w `SuperGameSeriesModal`. Wspólny `SuperGameSeriesPanel` zachowuje domyślną wartość `true`, opcjonalne wyłączenie i dotychczasowe zabezpieczenia zapisu. Udostępnianie jednej i wielu gier używa tego samego modalu. To jawna zmiana wymagania TASK-1062 na polecenie operatora, bez zmiany domeny lub architektury.

## Expected files

- `packages/board-search-ui/src/super-game-series/super-game-series-modal.tsx` — `SuperGameSeriesModal`.
- `packages/board-search-ui/src/super-game-series/super-game-series-panel.tsx` — komentarz `advanceAfterSave`.
- `packages/board-search-ui/test-interactions/super-game-series-modal.test.mjs` — zapis i automatyczne przejście.
- `ai_docs/requirements/ADMIN_APP.md` — aktualna reguła zapisu odbiorcy.
- Dokumentacja zamknięcia taska i wygenerowana mapa kodu, jeśli zmieniona.

## Test cases

- Zapis symbolu na serii #100 otwiera wyzwalacz #200 bez naciskania N; potwierdzenie pozostaje widoczne.
- Oczekujący zapis nie otwiera kolejnej serii.
- Regresje panelu: konflikt rewizji, brak następnej serii, ręczne N, wyczyszczenie symbolu.
- Zamknięcie po zapisie ponawia wyszukiwanie dokładnie raz.

## Verification

Uruchomić z katalogu głównego repozytorium w nowych procesach, każda komenda z timeoutem 120 s:

```powershell
node node_modules/tsx/dist/cli.mjs --tsconfig packages/board-search-ui/tsconfig.json --test packages/board-search-ui/test-interactions/super-game-series-modal.test.mjs packages/board-search-ui/test-interactions/super-game-series-panel.test.mjs
npm run typecheck --workspace @game-predictor/board-search-ui
Push-Location packages/board-search-ui
node ../../node_modules/eslint/bin/eslint.js src/super-game-series/super-game-series-modal.tsx src/super-game-series/super-game-series-panel.tsx test-interactions/super-game-series-modal.test.mjs
Pop-Location
node node_modules/prettier/bin/prettier.cjs --check packages/board-search-ui/src/super-game-series/super-game-series-modal.tsx packages/board-search-ui/src/super-game-series/super-game-series-panel.tsx packages/board-search-ui/test-interactions/super-game-series-modal.test.mjs
npm run docs:check
npm run code-map:check
```

## Risks / open questions

- Ręczny odbiór na Androidzie i restart produkcyjnego Reviewera pozostają po stronie operatora.

## Outcome

Commit: v1.7.449 (hash dopisuje kolejny commit).

### Changed

- Modal udostępniania ponownie korzysta z domyślnego `advanceAfterSave=true`; po sukcesie przechodzi do następnej serii bez symbolu.
- Trzy istniejące scenariusze interakcji sprawdzają automatyczne przejście: wejście z wyniku, wejście z wiersza zakresu i opóźnioną odpowiedź zapisu.
- Zachowano potwierdzenie zapisu, blokadę zamknięcia podczas zapisu, obsługę braku kolejnej serii, konfliktu rewizji i odświeżenie po zamknięciu.

### Verification results

- Testy interakcji modalu i panelu: **15/15 PASS**, nowy proces, 28,5 s, timeout 120 s.
- TypeScript `tsc --noEmit` pakietu: **PASS**, nowy proces, timeout 120 s.
- ESLint trzech zmienionych plików: **PASS**, uruchomiony z katalogu pakietu, timeout 60 s. Pierwsze wywołanie z katalogu głównego nie znalazło konfiguracji; poprawiono katalog wykonania.
- Prettier trzech zmienionych plików: **PASS**, timeout 60 s.
- Mapa kodu zregenerowana; bez różnic treści. `generate_code_map.py --check`: **PASS**, timeout 120 s.
- `npm run docs:check`: **PASS**, wszystkie cztery kontrole, timeout 120 s. Dry-run i zamknięcie `close_task.py`: **PASS**; zapis kopii kontrolnej w katalogu tymczasowym wymagał eskalacji poza sandbox.
- Porównanie z DoD: zachowanie i regresje pokryte, zakres bez zmian API/danych/architektury; test urządzenia opisany poniżej. Osobny plan ani audyt nie były wymagane.

### Not completed

- Bez ręcznego odbioru na Androidzie, pełnego builda i szerokiego quality; zmiana ogranicza się do konfiguracji istniejącego modalu i komentarza panelu.
- Bez restartu usług, scalenia, pushu i zmian danych operatora.

### Documentation updates

- `ADMIN_APP.md` opisuje przywrócone zachowanie zamiast reguły TASK-1062.
- `CURRENT_STATE.md` i archiwum aktualizuje `scripts/close_task.py`.

### Recommended next task

- Odbiór operatora i osobna zgoda na scalenie; produkcyjny Reviewer wymaga aktualnego builda i restartu przez operatora.
