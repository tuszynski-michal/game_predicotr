# TASK-0471 — Spójne przygotowanie i recovery
## Status
done
## Relevant docs
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/quality/SELECTED_CROP_V11_REGRESSIONS.md`
## Dependencies / goal
0470. Wspólne próbkowanie/polityka dla worker/fallback/CLI i bezpieczny journal.
## Scope / expected files
Core preparation, Admin worker/client/storage, runner katalogowy i testy recovery.
## DoD / tests
Przypięta polityka, fail-closed nieznana wersja, maksymalnie 2 poziomy,
checksum-bound zapis i restart, bez nadpisania obcych wyników. V11 nieaktywny
do odbioru 0472; nie uruchamiać przeliczenia katalogów użytkownika.
## Outcome
Wspólny sampler bilinear RGBA i wersjonowany fingerprint dla worker/fallback/Node.
Przypięta polityka jest przekazywana do obu ścieżek; nieznana wersja fail-closed.
V11 pozostaje nieaktywny (CLI blokuje jego wybór przed odbiorem). Manifest
przenosi dowód i wykonane poziomy. Node zapisuje per-file intencje, fsync,
no-clobber publikację, weryfikację SHA i shardy; retry sprawdza pliki, a nie
samą obecność wpisu. Ochrona źródeł, obcych wyników, katalogów przejętych przez
przeglądarkę, symlinków/junctionów i rezerwy 30 GiB. Read-only reuse starego
kompletnego manifestu; niepełny stary stan nie jest automatycznie przejmowany.
Testy: 72 core, 18 kontraktów Admina, 6 integracyjnych testów recovery Node OK;
typecheck core/Admin i lint czterech zmienionych modułów Admina OK. Pełny lint
Admina: 2 wcześniejsze błędy set-state-in-effect w geometry-guard-resolution-panel.
Nie wykonano mutacji katalogów użytkownika. Browserowe i Node dekodery JPEG
mogą różnić się pikselami; wspólny sampler jest identyczny dla identycznego RGBA,
pełne porównanie dekoderów na żywej przeglądarce pozostaje ograniczeniem odbioru.
Następny: 0472, bez aktywacji jeśli bramki nie przejdą.
