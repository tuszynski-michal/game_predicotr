---
title: TASK-1174 — Następna plansza i szybkie ładowanie korekty
status: done
last_updated: 2026-11-09
---

# TASK-1174 — Następna plansza i szybkie ładowanie korekty

## Status

`done`

## Goal

Następna plansza i szybkie ładowanie korekty.

## Context

Operator zaakceptował2–4h na margines0%, testy i Opus, połączył z najnowszym
zgłoszeniem powtarzającej się planszy i wolnego ładowania. Pełny zakres dwóch
tasków jest zlecony; zgoda nie obejmuje wdrożenia ani merge.

## Recommended execution

gpt-6.1-sol/high. Terminalowy niezależny Claude Code claude-opus-5-5/high,
przed commitem; otwarte P0/P1 po jednej rundzie poprawek zatrzymują task.
Bez automatycznej delegacji ani zmiany modelu.

## Relevant docs

- `ai_docs/delivery/FULL_FIELD_CORRECTION_FLOW_PLAN_20261109.md`.
- `ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md`, `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`.
- `ai_docs/requirements/IMAGE_INGESTION.md`, `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`.
- `ai_docs/process/CROSS_AUDIT.md`, `ai_docs/process/DEFINITION_OF_DONE.md`.
- `ai_docs/process/decisions/DECISION_LOG_2026.md` — konkretne D-462/D-488/D-591/D-596/D-597 przez indeks; nie czytać całości.

## Out of scope

Trening, default geometrii, zapis do bazy operatora, masowe akceptacje, restarty,
merge/push i wdrożenie. Testy PG wyłącznie disposable. Operatorowe odczyty bounded/read-only.

## Scope

T1 planu. Ustalone przyczyny: reset kursora po save reviewAll oraz agregaty counts=all, których ten ekran nie pokazuje. Nie zmieniać znaczenia view=all ani zamieniać go w filtr tylko niepotwierdzonych.

## Acceptance criteria

- [x] Spełnione kryteria przypisanej sekcji planu i regresje dotychczasowych konsumentów.
- [x] Spójny kontrakt API/OpenAPI/SDK/wrapper/test.
- [x] Właściwe testy/lint/types/build/docs/map i niezależny Opus z receipt.
- [x] Outcome i zamknięcie task-close; commit i hash zgodnie z sekwencją zamknięcia.

## Expected files

apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx; domain/application/schemas/api image_grid_reviews; istniejące testy Reviewera/API/PG; generowany OpenAPI/SDK i wrapper test; dokumenty/mapa.

## Test cases

Normal save/last/deferred materialization/duplicate sequence/source filter/stale response/save failure; correction regression. NONE zero calls to counts repository; old ALL/CORRECTION unchanged. Meaningful PostgreSQL paging test and bounded real read-only timing.

## Verification

Python z D:/game_predicotr/.venv; PYTHONPATH własnego API/workera. Reviewer
`npm run test:geometry --workspace @game-predictor/reviewer` (najpierw właściwe pliki),
scoped Ruff/mypy/ESLint/TS, potem wymagany build. Skończone komendy timeout≤120s;
znany build/audyt według limitów repo. Nie uruchamiać usług.

## Risks / open questions

Dane operatora nie stanowią testowych fixture; same confidence/regularność nie
kwalifikują pełności. Brak GT nie jest pomiarem poprawy klasyfikacji. Nie tworzyć
fikcyjnego PASS. Wszelkie zmiany kolejności/source identity muszą zachować sequence.

## Outcome

Commit: v1.7.587 / `1181797cbad2bdd62fda9ff249ee60ce8d1123b7`.

Naprawiono przejście po zapisie `reviewAll`, zmianę UUID deferred→review,
koniec zakresu i ochronę nowego zakresu przed starą odpowiedzią. Correction
zachowuje swoją kolejkę. Dodano jawne `counts=none` w istniejącym API,
OpenAPI/SDK i teście wrappera; żaden agregat nie jest wykonywany. Predykaty
partycji ograniczają odczyt do bieżącej gry bez usuwania ochrony widoczności.

Weryfikacja: API/domena24 i PG2, Reviewer38, klient160 PASS; Ruff, scoped ESLint,
mypy4 moduły, Reviewer typecheck/build, docs/map PASS. Szczegóły i ograniczenia
pomiaru: `ai_docs/quality/TASK-1174_VERIFICATION.md`. Po zmianie ograniczony
read-only odczyt listy1.236s; nie jest to gwarancja całkowitego czasu ekranu.

Audyt Opus5.5/high przez terminal R1: REVISE (P0-1,P1-1,P1-2).
Jedna runda poprawek: jawne kursory i historia, świeża „Poprzednia”, retry tego
samego odczytu, przejście po propozycji i aktualizacja bez utraty miejsca.
P2-1/2/3 naprawione; P2-4 wyjaśnione w weryfikacji (pochodzenie stanu importu,
różnice końców linii generatora). **R2 PASS**,0 otwartych P0/P1:
`ai_docs/quality/TASK-1174_AUDIT_claude-opus-5-5.md` i receipt, SHA pakietu
2fd6022c900673562dd7fc841aafea8a3ba2645c3eb8114b846abeda69b39d8d.
Zachowano również R1 i jego receipt. Rzeczywisty model Opus5.5 potwierdzony
system.init; effort high jest żądany, nie poświadczony przez backend.

P2-4: świadomie dołączono aktualizację stanu Mumie z zakończonej wcześniejszej
operacji tego samego czatu (źródło RESULT.json). Pozostałe pliki generatora bez
faktycznego diffu nie trafiają do commita. P2-5/6/7 przyjęto jako ograniczenia UX:
„Poprzednia” może pominąć zapisany deferred do czasu materializacji kompletnego
zdjęcia; po odrzuceniu/cofnięciu końca komunikat pustego zakresu bywa mylący;
po nietypowych powtórzonych trzech wpisach tej samej pozycji retry zachowuje
miejsce, ale ekran błędu nie ma osobnego „Od początku”. Nie zmienia to zapisów
ani normalnego przejścia naprzód. Nie rozszerzano rund audytu dla tych P2.
Bez migracji, operatorowych zapisów/restartów/merge. Następnie TASK-1175,
zgodnie z poleceniem wykonania obu poprawek. Margin0% nie jest jeszcze gotowy.

Aktualizacja wdrożenia2026-11-09: TASK-1175 ukończony; operator zaakceptował
merge/push/cleanup oraz restart API/Reviewera/general. Main i origin zawierają
oba taski; nowy Reviewer i worker działają. HTTP zwróciło trzy różne kolejne
pozycje w1.9–2.2s. Odbiór:
ai_docs/quality/FULL_FIELD_CORRECTION_DEPLOYMENT_20261109.md.
