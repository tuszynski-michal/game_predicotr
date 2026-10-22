---
title: TASK-1086 — Domknięcie zabezpieczeń relokacji źródeł C
status: done
last_updated: 2026-10-22
---

# TASK-1086 — Domknięcie zabezpieczeń relokacji źródeł C

## Status

`done` — operator zatwierdził zastąpienie pełnego skanu analizą
rzeczywistych zależności od plików oraz dodatkowe 15–25 minut kontroli.

## Goal

Rozliczyć P2-1–7 audytu TASK-1085 przed zatwierdzaniem migracji i odcięcia C.

## Context

Operator zatwierdził dodatkowe 20–40 minut na zabezpieczenia, test izolowanej
bazy i pełny skan bazy tylko do odczytu. Bez zapisu danych operatora,
restartów, scalenia i usuwania C. Kontynuacja na codex/retire-c-copy.
Następnie zatwierdził dodatkowe 15–25 minut i zastąpienie pełnego skanu
analizą rzeczywistych zależności od plików; pełne historyczne JSON poza zakresem.

## Recommended execution

gpt-6.1-sol, high. Jedna wąska runda poprawek P2 po audycie Claude TASK-1085;
bez powtarzania zakończonego audytu. Pomocnicza eksploracja repo-explorer:
gpt-6-luna/medium, tylko do odczytu, zgodnie z regułą AGENTS.md dla szerokiej eksploracji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/quality/LEGACY_C_COPY_RETIREMENT_20261022.md`
- `ai_docs/quality/TASK-1085_AUDIT_claude-opus-5-5.md`
- `ai_docs/tasks/completed/1085-prepare-legacy-c-copy-retirement.md`

## Scope / technical notes

- Propagować jawny receipt do obu ścieżek managed reprocess (zwykła i ręczna
  kontynuacja). Zachować domyślne zachowanie bez receiptu i bajty manifestów.
- Podgląd v2 zapisuje skonfigurowany artifact_root i dokładny zestaw istniejących
  manifestów z SHA. Apply odmawia przy braku/zmianie dowolnego z nich.
  Kontrola dotyczy procesu skryptu; restart działających workerów pozostaje
  obowiązkiem operatora przed apply. Nie obiecywać kontroli ich wersji.
- Przed pierwszym UPDATE wyliczyć dozwolone after_payload z before i korzeni;
  odmówić dodatkowych zmian nawet po przeliczeniu SHA. Stare preview v1
  odrzucane; świeży podgląd wymagany do wykonania.
- Zmiana zatwierdzona przez operatora 2026-10-22: zamiast pełnego skanu
  dowolnych tekstów i JSON sprawdzić wszystkie skalarne kolumny przechowujące
  lokalizacje plików (także domeny/tablice) i prześledzić otwierane deskryptory
  JSON w kodzie. Tylko READ ONLY, ograniczone zapytania, jawne ograniczenia.
  Pełny skan głębokich historycznych JSON pozostaje poza nowym zakresem.
- Test PostgreSQL wykorzystuje wyłącznie własną bazę z prefiksem TASK-1086 i UUID;
  migracje schematu przez istniejący Alembic. Cleanup wyłącznie utworzonej bazy.
- P2-6: obecny effort potwierdzony audytem; test argumentów uzupełnić lokalnie
  bez kontaktu z modelem. Brak zmiany schematu produkcyjnego.
- Test potwierdził dodatkowy blocker: ścisłe schematy odpowiedzi API odrzucają
  receipt dodany przez relokację. Operator został poinformowany przed zmianą.
  Opcjonalne pole w wariantach payloadu źródłowego, OpenAPI, generowany klient,
  re-eksport typu przez wrapper i test GET/list stanowią jeden pion kontraktu.

## Expected files

- `services/api/src/game_predictor_api/application/jobs.py`, testy managed reprocess.
- `scripts/legacy_job_path_migration.py` i jego testy, nowy test integracyjny.
- Proponowane: `scripts/scan_legacy_database_paths.py` i test skanera.
- Test loadera w `services/worker/tests/test_image_source_ingestion.py`.
- Test argumentów w `scripts/tests/test_auditor_cli.ps1`.
- `schemas/jobs.py`, OpenAPI i wygenerowane typy klienta Admin, re-eksport
  w jego index.ts oraz test żądania/odpowiedzi klienta.
- Raport przygotowania, DATA_MODEL, mapa kodu i CURRENT_STATE.

## Acceptance criteria / test cases

- [x] Obie ścieżki reprocessu przenoszą receipt; brak receiptu bez zmian.
- [x] Po usunięciu starego źródła i kopii managed reprocess odtwarza obraz z D.
- [x] Brak/zmiana manifestu albo niedozwolony after_payload blokuje apply.
- [x] Izolowany PostgreSQL: poprawny zapis JSONB, konflikt po podglądzie,
      blokada NOWAIT i rollback bez częściowego UPDATE, ponowienie po utracie odpowiedzi.
- [x] Odczyt kolumn ścieżkowych i analiza operacyjnych deskryptorów JSON
      rozliczają rzeczywiste zależności od starego korzenia C.
- [x] Testy pionu, lint/typecheck, dokumentacja, mapa i docs:check; wcześniejsze
      błędy typów API odtworzone na niezmienionym main, bez nowej regresji.

## Verification

Python D:/game_predicotr/.venv/Scripts/python.exe, PYTHONPATH wskazuje ten
worktree. pytest bez uruchamiania usług; każda komenda ma timeout ≤120 s.
Skan w odcinkach ≤90 s, pojedyncze zapytanie ≤10 s.

## Outcome

Commit: v1.7.462 (hash dopisuje kolejny commit).

### Changed

- Obie ścieżki managed reprocess propagują receipt; źródła bez receiptu bez zmian.
- Wersja v2 preview/apply przypina zestaw i SHA manifestów oraz artifact_root,
  sprawdza API i worker w nowym procesie oraz dopuszcza tylko wyliczoną relokację.
- Opcjonalne pole API, OpenAPI i klient wygenerowany, re-eksport typu oraz test
  GET/list. Test znalazł i usunął odrzucanie receiptu przez ścisłe schematy API.
- Skaner tekstów i JSON, kluczy JSON, tablic i domen, bez parentów partycji,
  READ ONLY. Małe porcje TID, checkpointy i rozłączne części, jawna niepełność.
- P2-6: sześć asercji rzeczywistego fragmentu budowania argumentów bez modelu.

### Verification results

- 76 testów relokacji, managed reprocess, loadera i API — PASS, 75.44 s.
- Test PostgreSQL na własnej bazie z Alembic head — PASS, 16.21 s (końcowy):
  konflikt updated_at, NOWAIT, rollback po pierwszym UPDATE, JSONB, utrata
  odpowiedzi/ponowienie, skan wartości i kluczy JSON, podział pokrycia,
  dodatni przypadek skanu kolumn ścieżkowych i odmowa wznowienia innego zakresu.
- Test wrappera klienta — PASS. Typy klienta, OpenAPI i zgodność generowanego
  klienta — PASS. Istniejący kontrakt Vision Lab bez zmian.
- Ruff — PASS; mypy nowych/zmienionych skryptów --follow-imports=skip — PASS.
- Mypy API z normalnym sprawdzaniem modeli Pydantic i zależności domenowych,
  z pominięciem grafu importów storage/worker: dokładnie te same 23 błędy
  w 13 plikach co na niezmienionym main; brak nowych błędów w zmienionym pionie.
  Pełny graf przekroczył limit 110 s, a globalne --follow-imports=skip
  daje niemiarodajne błędy Pydantic. Nie oznaczono pełnego typechecku API jako PASS.
- Testy PowerShell: 16 asercji PASS, bez uruchomienia audytora.
- Świeży preview v2: 179 jobów, 176 manifestów z SHA, 55 katalogów z ponownym SHA,
  blockers=[]. SHA: b6089b4c5cff7b42b11673f11f1b973c6439fd20fb69b47ccbecdd147ec96ca0.
- Odczyt READ ONLY wszystkich 133 kolumn ścieżkowych w 108 tabelach — PASS,
  complete=true, errors=[]: wyłącznie 14 historycznych host_base_path sesji.
- Analiza konsumentów JSON i odczyt odpowiadających danych — PASS: brak operacji
  V7, odwołań jobów do lokalnych manifestów i plików lokalnych manifestów/draftów;
  ustawienia ścieżek aplikacji z nowego procesu wskazują D. Ścieżki względne
  modeli, zdjęć, cohortów i wydań rozwiązywane względem kontrolowanych korzeni.
- Prywatne potwierdzenia w artifacts/maintenance/legacy-c-20261022:
  database-operational-paths.json i operational-json-sources.json; zakres i
  ścieżki konsumentów rozliczone w raporcie przygotowania.

### Not completed

- Pełny historyczny skan 2092 kolumn / 392 tabel jest nieukończony: pokryto 825 kolumn,
  169 tabel. Baza 147370317503 B (~137.3 GiB). Głębokie JSON wymagają
  znacznie dłuższego odczytu; checkpointy zapisane, brak dalszych procesów skanu.
  Operator jawnie zastąpił ten zakres analizą rzeczywistych zależności; nie
  uznano częściowego skanu historii za pełne pokrycie bazy.
- Bez UPDATE na danych operatora, restartów, merge/push i usuwania C.
- Worktree ma junction .venv oraz node_modules do głównego D; sprzątanie musi
  odpiąć same dowiązania, nigdy ich cele.

### Documentation updates

- DATA_MODEL i API_CONTRACT aktualizują zachowanie po relokacji.
- Raport przygotowania zachowuje historię audytu i rozliczenie uwag.
- Mapa kodu wygenerowana; docs:check — PASS.

### Recommended next task

- Po akceptacji wyniku i zgodzie na scalenie wdrożyć kod; operator restartuje
  API i workery. Odświeżyć preview i uzyskać zgodę na relokację 179 ścieżek.
  Kontrolowane odcięcie starej nazwy C i samo usunięcie wymagają osobnej zgody.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1086 | gpt-6.1-sol | high | Wąskie zabezpieczenia danych i test transakcji po zatwierdzonym zwiększeniu kosztu. | Nie; jedna runda poprawek P2 po niezależnym audycie Claude TASK-1085. |
