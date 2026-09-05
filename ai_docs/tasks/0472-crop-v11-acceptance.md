# TASK-0472 — Odbiór v11
## Status
blocked — quality gate failed
## Relevant docs
- `ai_docs/quality/SELECTED_CROP_V11_REGRESSIONS.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
## Dependencies / goal
0471. Odbiór dokładnej ścieżki produkcyjnej bez strojenia na holdout.
## DoD / tests
Zero niebezpiecznych automatów i cropów reklamy, minimum 90% poprawnych
automatów na czytelnych kompletnych źródłach. Raport osobno dla wyglądów gry,
czasy/pamięć, testy core/Admin, lint/typecheck/format/build. Brak oryginałów
innej gry ogranicza odbiór. Nie aktywować jeśli bramka nie przejdzie.
## Outcome
2026-09-05: odbiór wykonano dokładną ścieżką renderCropSource, bez zapisu
wynikowych JPEG-ów. Holdout: 0/2 poprawnych automatów (wymagane >=90%),
0 błędnych automatów, 2 obowiązkowe korekty: incomplete_layout po 960 i 1600.
Zero błędów przy zerowej liczbie akceptacji nie oznacza sukcesu jakości.

Na polecenie użytkownika zatrzymano strojenie i wdrożenie. Release gate pozostaje
false; istniejące katalogi, importy i decyzje nie zostały zmienione. Task nie
spełnia DoD i pozostaje aktywny jako blocked, zamiast trafić do completed.

Weryfikacja: 72 testy core, 18 kontraktów Admina, 7 testów runnera (w tym
EXIF 1–8), typecheck core/Admin, scoped lint, scoped format i build Admina OK.
Replay baseline v10: 7/7 zgodnych. Pełny lint Admina blokują dwa wcześniejsze,
niezwiązane błędy set-state-in-effect w geometry-guard-resolution-panel.tsx.
Nie wykonano pełnych testów aplikacji ani live QA przeglądarki. Zgodność samplerów
dotyczy tych samych RGBA; różnice dekoderów JPEG Node/przeglądarka nie zostały
zmierzone. Oryginały gry literowej pozostają niedostępne.

Raport: ai_docs/quality/SELECTED_CROP_V11_REGRESSIONS.md. Dalsza praca wymaga
osobnego polecenia: analiza ekstrakcji kandydatów, nie osłabienie ochrony granic.
