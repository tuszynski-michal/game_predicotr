# TASK-0960 — brief do późniejszego przeglądu Claude

**Status: audyt niewykonany.** Skrypt `audit_task.ps1` wygenerował brief,
ale CLI Claude nie jest dostępne w tej sesji. Dokument nie jest raportem PASS.

Zakres przeglądu: usunięcie niepoprawnego kasowania
`image_review_queue_states` w
`services/api/src/game_predictor_api/storage/cleanup_repository.py`
oraz regresja `test_source_cleanup_batches_preserve_queue_until_last_source`
w `services/api/tests/integration/test_cleanup_repository.py`.
Task i wynik: `ai_docs/tasks/completed/0960-board-source-cleanup-queue-state.md`.
Bazowy commit przed poprawką: `423cc79315ec4605dd146ace4d1366491d351657`.

Pierwsza częściowa operacja usuwała licznik całego importu, mimo że pozostawały
inne zdjęcia. Trigger usuwania następnej pozycji kolejki zgłaszał SQLSTATE23514:
`Cannot delete image review queue state for job ...: projection is missing`.
Poprawka pozostawia utrzymanie i usuwanie pustego licznika temu triggerowi.

Test realnego PostgreSQL sprawdza dwa usunięcia w osobnych zatwierdzonych
transakcjach i nowych sesjach: po pierwszym licznik wynosi `(1, 1)`,
po ostatnim nie ma pozycji ani stanu kolejki. Wynik: 1 passed.
Dotychczasowe testy domain/API: 10 passed. Ruff passed.
Mypy nie zakończył się w limitach 90 i 55 sekund; nie deklarowano sukcesu.

Operacyjnie odtworzono siedem brakujących liczników z pozycji kolejki, po
sprawdzeniu ich identyfikatorów i statusów względem review items. Wersje
oparto na nowym znaczniku mikrosekundowym, aby unieważnić stare kursory.
Nie zmieniono pozycji ani 217 zachowanych accepted reviews.
Dowody operacyjne pozostają w `artifacts/mumie-cropped-boards-20261009/`.

Wszystkie 275 zatwierdzonych źródeł usunięto standardowym API, bez obchodzenia
triggerów, RLS, blockerów ani rozszerzenia zaakceptowanych zakresów.
Końcowy odczyt w nowym procesie: zero rekordów celu, pięć receiptów,
brak rozbieżności liczników. Manifest z nazwami i zakresami pozostaje w repo.

Audyt ma być statyczny i tylko do odczytu, skupiony na P0/P1. Nie wymaga
ponawiania usunięcia danych ani ponownego uruchamiania usług.
