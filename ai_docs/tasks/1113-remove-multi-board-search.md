---
title: Usunięcie wyszukiwania wielu układów
status: todo
last_updated: 2026-10-30
---

# TASK-1113 — Usunięcie wyszukiwania wielu układów

## Status

`todo` — implementacja czeka na akceptację planu i kosztu.

## Goal

W Adminie i obu rodzajach linków działa wyłącznie wyszukiwanie jednej planszy,
z zachowaną nawigacją zdjęć ±15 i bez drogi wykonania rankingu wielu wzorów.

## Context

Użytkownik rezygnuje z wyszukiwania 2–4 układów. Zgłasza obciążenie i timeouty,
ale nie ustalono pomiarem, czy wszystkie pochodzą z tej funkcji. Jednowzorowe
GET już jest odrębną ścieżką. Wielowzorowe zapytania mogą obecnie wracać
automatycznie ze storage oraz z odtwarzania historii.

## Dependencies / entry conditions

- TASK-1112: ograniczona diagnoza i plan. Plan ma status `proposed`.
- Wyraźna akceptacja zakresu oraz szacunku 1–2 godzin; obecna prośba dotyczy
  wyłącznie przygotowania planu, więc nie uruchamia tego taska.
- Sprawdzić HEAD, dostępność modelu, zależności i brudny worktree przed zmianą.
  Numery 1112/1113 sprawdzono w lokalnych gałęziach 2026-10-30; przed nowymi
  numerami wersji i decyzji wykonać ponowną kontrolę kolizji.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`, zgodnie z końcową tabelą planu. Jeden
wykonawca bez automatycznej delegacji; osobny audyt nie jest wymagany.
Nowa konieczność zmiany modelu danych lub uprawnień oznacza zatrzymanie
i korektę planu. Nie rozszerzać taska o inne źródła timeoutów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- [D-573](../process/decisions/DECISION_LOG_2026.md#d-573--wyszukiwanie-po-kolejnych-układach)
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/BOARD_SEARCH_SINGLE_BOARD_REMOVAL_PLAN_20261030.md`
- `ai_docs/requirements/ADMIN_APP.md` — wyszukiwanie plansz z niepełnym wzorem
- `ai_docs/architecture/API_CONTRACT.md` — wyszukiwanie plansz częściowym układem
- `ai_docs/architecture/DATA_MODEL.md` — korekty udostępnionej wyszukiwarki
- `ai_docs/architecture/CODE_MAP.md`, `ai_docs/architecture/CODE_MAP_SYMBOLS.md`
- `ai_docs/DOC_INDEX.md`
- `.agents/skills/task-close/SKILL.md`

## Scope

- Usunięcie UI, wykonawczego stanu i API wielu wzorów we wszystkich hostach.
- Usunięcie algorytmu rankingu ciągów, dedykowanego middleware, adapterów,
  cache, typów i eksportów, które nie są potrzebne do odczytu historii.
- Zachowanie pojedynczego GET i dotychczasowych zabezpieczeń interakcji.
- Nawigacja ±15 niezależna od usuwanej capability; powiązanie korekty z
  oglądaną planszą i wygranych ze znalezioną planszą.
- Zgodny odczyt pojedynczych zapisów i jawna odmowa odtwarzania wielu wzorów.
- OpenAPI, klient, regresje, dokumentacja, mapa kodu i zamknięcie taska.

## Out of scope

Optymalizacja wielu wzorów; inne przyczyny timeoutów; zmiany reguł punktacji;
usuwanie plansz, zdjęć lub historii; migracje i downgrade; przebudowa indeksów;
benchmarki; usługi i ich restart; merge, push i wdrożenie.

## Acceptance criteria

- [ ] Jeden edytor i jedno GET, brak dodawania wzorów we wszystkich trzech hostach.
- [ ] Dawne POST odrzucone przed rankingiem; operacje usunięte z OpenAPI i klienta.
- [ ] Brak produkcyjnego kodu wykonującego ranking wielu wzorów i cache ciągów.
- [ ] Nawigacja ±1/±2/±15, granica 1, błędy i późne odpowiedzi przechodzą regresje.
- [ ] Nawigacja/korekta nie zmienia rankingu ani kotwicy kalkulatora.
- [ ] Ponowne otwarcie starego wielowzorowego zapisu i replay historii nie wysyła zapytań.
- [ ] Historia i snapshoty korekt pozostają czytelne; pojedynczy replay działa.
- [ ] Limit 40, zachowanie korekt, kolejkowania obliczeń i panelu zarządzania zachowane.
- [ ] Testy, lint, typy, generacja, buildy i dokumentacja sprawdzone; ograniczenia opisane.
- [ ] Outcome, `task-close` i commit, bez merge/push.

## Technical notes

Obowiązują rozstrzygnięcia 1–7 planu. Usunąć trasy POST, a nie blokować ich
wyłącznie flagą UI. Zachować parsery historii v2 i snapshotów oraz migrację
0169. Backend i oba proxy mają odmówić staremu POST bez wywołania usługi;
typy generować z OpenAPI, nie poprawiać ręcznie.

Uprościć obecny hook do pojedynczego wzoru, zachowując ochronę przed
spóźnioną odpowiedzią, priorytet replay, blokadę kalkulatora, odświeżenie po
korekcie i zmianę limitu. Samo wyłączenie `sequenceEnabled` przywróciłoby
inny legacy workflow i ukryło nawigację — to niedozwolony skrót.

Wielowzorowy stan pozostaje pod dawnym kluczem, ale nowy kod go nie wykonuje.
Jednowzorowy poprawny zapis można przenieść do nowej wersji. Historia z
2–4 wzorami daje komunikat zamiast obcięcia wzoru, także gdy replay dotyczy
powiązanego wykresu lub planszy. Korekty historyczne nadal są do odczytu.

## Expected files

Istniejące ścieżki i symbole potwierdzone w diagnozie:

- `packages/board-search-ui/src/board-search-workspace.tsx` (`BoardSearchWorkspace`),
  `use-board-search-sequence.ts`, `board-search-sequence-state.ts`,
  `board-search-data-source.ts`, `board-search-results.tsx`,
  `board-search-photo-navigation.tsx`, eksporty/styl usuniętych kontrolek.
- `apps/admin/src/features/board-search/board-search-replay-state.ts`
  (`boardSearchReplayPlan`), prezentacja odtwarzania historii.
- `apps/reviewer/src/features/board-search-share/board-search-share-data-source.ts`
  (`createBoardSearchShareDataSource`), `apps/reviewer/src/security/board-search-share-proxy.ts`
  i `board-search-panel-proxy.ts`.
- `services/api/src/game_predictor_api/api/board_search.py`,
  `api/board_search_share_public.py`, `api/board_search_sequence_body.py`,
  `application/board_search.py`, `storage/board_search_projection_repository.py`,
  `storage/board_search_sequence.py`, `domain/board_search_sequence.py`,
  `schemas/board_search_sequence.py`, `main.py`; usunąć niepotrzebne moduły
  i rejestrację middleware. `domain/board_search_share_queries.py`: usunąć
  wyłącznie nieużywany zapis nowych zapytań wielu wzorów, zachować odczyt.
- `packages/admin-api-client/src/index.ts`, wygenerowane pliki klienta i
  kontrakt wskazany przez `scripts/export_admin_openapi.py`.
- Testy wyszukiwania w API, `packages/board-search-ui`, Adminie, Reviewerze
  i kliencie; właściwe wymagania, kontrakt, decyzja, CURRENT_STATE i mapa kodu.

Proponowane nowe nazwy: `use-board-search.ts` i `board-search-local-state.ts`
zamiast modułów wykonawczych wielu wzorów; nazwy dopasować do istniejących
eksportów bez dublowania logiki.

## Test cases

Macierz odbioru w planie jest listą obowiązkową. Bazą są istniejące:

- `services/api/tests/test_board_search_api.py`,
  `test_board_search_share_public_api.py`, `test_board_search_sequence_api.py`,
  `test_board_search_sequence_public.py`, `test_board_search_share_query_log.py`.
- `packages/board-search-ui/test-interactions/board-search-sequence.test.mjs`:
  zachować przypadki jednego wzoru, zdjęć, korekt i odtwarzania; przypadki
  2–4 wzorów zastąpić testami usuniętego kontraktu. Dodatkowo istniejące testy
  limitu, replay, klawiatury, kalkulatora i saved-selection.
- `apps/admin/test/board-search-sequence-history.test.mjs`,
  `board-search-replay-state.test.mjs`.
- `apps/reviewer/test/board-search-sequence-data-source.test.mjs`,
  `board-search-sequence-proxy.test.mjs`, testy proxy linku/panelu,
  korekt i security-gate; interakcje `board-search-panel.test.mjs`.
- `packages/admin-api-client/test/board-search-sequence.test.mjs`:
  zastąpić testem pojedynczego żądania i braku starej metody/operacji.

## Verification

Polecenia uruchamiać w katalogu głównym worktree, z jawnym timeoutem.
Przykład wrappera PowerShell (używa dostępnego Pythona):

```powershell
function Invoke-Checked120([string[]] $Command) {
    python -c 'import subprocess,sys; subprocess.run(sys.argv[1:], timeout=120, check=True)' @Command
    if ($LASTEXITCODE -ne 0) { throw 'Kontrola nie przeszła lub przekroczyła 120 s.' }
}
Invoke-Checked120 @('.\.venv\Scripts\python.exe', '-m', 'pytest', 'services/api/tests/test_board_search_api.py', 'services/api/tests/test_board_search_share_public_api.py', 'services/api/tests/test_board_search_sequence_api.py', 'services/api/tests/test_board_search_sequence_public.py', 'services/api/tests/test_board_search_share_query_log.py', '-q')
Invoke-Checked120 @('npm.cmd', 'run', 'test:interactions', '--workspace', '@game-predictor/board-search-ui')
Invoke-Checked120 @('npm.cmd', 'run', 'openapi:generate')
Invoke-Checked120 @('npm.cmd', 'run', 'check:generated', '--workspace', '@game-predictor/admin-api-client')
Invoke-Checked120 @('npm.cmd', 'run', 'docs:check')
Invoke-Checked120 @('npm.cmd', 'run', 'code-map:check')
```

Najpierw wąskie testy powyższych plików (także klient/hosty), następnie
format/lint/typecheck zmienionych części i build Admina/Reviewera. Dostępne
skrypty to `lint`, `typecheck`, `admin:build`, `reviewer:build`; nie uruchamiać
globalnego `quality`. Build przekraczający 120 s wymaga uprzedzenia i jawnego
limitu. Nazwy testów usuniętego silnika zaktualizować po przeniesieniu regresji.
Brak lokalnych zależności naprawić zgodnie z konfiguracją worktree, bez
uruchamiania usług i bez przypadkowego zapisu w cudzym checkoutcie.

## Risks / open questions

- Nie gwarantujemy usunięcia wszystkich timeoutów bez pomiaru; nie dodawać
  benchmarku do tego taska.
- Stare otwarte klienty wymagają odświeżenia po wdrożeniu. Restart usług
  wykonuje operator w osobnym kroku; plan nie daje takiej zgody.
- Akceptacja planu obejmuje proponowane zasady starych zapisów i historii.
  Nie ma innej nierozstrzygniętej decyzji produktowej.

## Outcome

Nie rozpoczęto implementacji. Testy powyżej są planowane, nie wykonane.
