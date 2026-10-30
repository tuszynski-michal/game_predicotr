# TASK-1113 — Odblokowanie zapisu super symbolu

## Status

`done`

## Goal

Zapis super symbolu kończy stan zapisywania i przechodzi do następnej serii także przy włączonym React StrictMode.

## Context

Operator zgłosił zawieszony zapis, pilny ze względu na oczekującego klienta. Cztery testy regresyjne odtwarzają problem: efekt montowania po kontrolnym cleanupie StrictMode pozostawia `mounted.current = false`. Panel ignoruje sukces, odmowę, konflikt oraz błąd połączenia, więc host nadal blokuje zamknięcie. Admin i Reviewer mają `reactStrictMode: true`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md` — Super game series, zapis i przejście do następnej serii.
- `ai_docs/architecture/API_CONTRACT.md` — Super game series, CAS super symbolu.
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Przywrócić znacznik montowania przy każdym uruchomieniu efektu.
- Sprawdzić sukces, błąd połączenia, odmowę i konflikt w StrictMode.
- Zachować ochronę przed spóźnionymi odpowiedziami i istniejący przepływ retriggerów.

## Out of scope

Zmiany API i bazy, restart usług, merge i push.

## Acceptance criteria

- [x] Po sukcesie znika blokada zapisu i otwiera się następna seria.
- [x] Odmowa, konflikt i błąd połączenia kończą zapis oraz pokazują komunikat.
- [x] Dotychczasowe testy panelu i modala przechodzą.
- [x] Formatowanie, lint i typy zmienionego pakietu przechodzą.

## Expected files

- `packages/board-search-ui/src/super-game-series/super-game-series-panel.tsx` — efekt montowania `SuperGameSeriesPanel`.
- `packages/board-search-ui/test-interactions/super-game-series-panel.test.mjs` — helper montowania i regresje StrictMode.

## Verification

Testy interakcji panelu i modala przez `tsx --tsconfig packages/board-search-ui/tsconfig.json --test`; lint i typecheck pakietu. Każda komenda ograniczona przez `subprocess.run(timeout=120)`; regresje przed poprawką: 0/4 PASS.

## Risks / open questions

Brak pytań blokujących. Założenie: naprawiamy odtworzoną przyczynę wiszącego UI; testy nie dowodzą czasu odpowiedzi działającego serwera klienta. Bez zmiany kontraktu i zachowania produktu, bez osobnego planu i wymaganego audytu.

## Outcome

Commit: v1.7.514 / `923dd029f22a26569efb46d2aef55b49e5f1ad1a`.

### Changed

- Efekt montowania ponownie ustawia `mounted.current = true`; kontrolny cleanup StrictMode nie powoduje już odrzucania aktualnych odpowiedzi. Rzeczywiste odmontowanie nadal wyłącza obsługę odpowiedzi.
- Cztery regresje StrictMode obejmują zapis po przeglądzie retriggera, przejście do kolejnej serii, odblokowanie hosta, odmowę API, konflikt rewizji i utratę połączenia.

### Verification results

- Przed poprawką: cztery nowe regresje FAIL, odtwarzają zawieszony zapis.
- Po poprawce, w nowym procesie: 21/21 testów interakcji panelu i modala PASS (15,3 s), w tym wszystkie cztery regresje.
- ESLint obu zmienionych plików PASS, `tsc --noEmit` pakietu PASS, Prettier zastosowany.
- Zachowane istniejące testy retriggerów, CAS, blokady zamknięcia w trakcie zapisu, korekt planszy i przejścia do następnej serii. Kryteria taska i właściwe punkty DoD spełnione.

### Not completed

- Nie restartowano usług, nie wykonywano zmian danych, merge ani push. Bez pełnego builda i testu na fizycznym Androidzie: poprawka ograniczona do cyklu życia efektu, bez zmiany układu i API. Weryfikacja działającego klienta wymaga odświeżenia strony przez operatora.
- Nie wymagano audytu krzyżowego: zadanie nie wykonuje planu z takim wymaganiem.

### Documentation updates

- Task i stan projektu zamykane skryptem `close_task.py`; zachowanie wymagane przez ADMIN_APP i kontrakt API pozostają aktualne.

### Recommended next task

- Odbiór zapisu po Ctrl+F5 w działającej aplikacji operatora.
