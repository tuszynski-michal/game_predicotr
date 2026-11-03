---
title: Manifest wymiany całych źródeł
status: done
last_updated: 2026-11-03
---

# TASK-1127 — Manifest wymiany całych źródeł

## Status

`done`

## Goal

Trwale zapisać i eksportować dokładny plan wymiany wybranych zdjęć bez wycofywania źródeł.

## Dependencies / entry conditions

A1–A3 ukończone; A3 2720e7aa, zapis hasha 5b260fc2. Cały plan, koszt i audyty Opus 5.5 zaakceptowane. Integracja main 40581449 do gałęzi roboczej jest częścią B1, bez merge do main/push. Migracja 0173 łączy audytowane 0171/0172; 0174 dodaje B1. Bez bazy operatora, usług, treningu i retirement.

## Recommended execution

gpt-6-astra / high; niezależny claude-opus-5-5 / high przed commitem. Niedostępność modelu lub sprzeczność wymagań blokuje zależny zakres.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`
- D-543: `ai_docs/process/decisions/DECISION_LOG_2026.md#d-543--odrzucanie-przyciętych-plansz-po-imporcie-i-przejęcie-sekwencji-przez-zdjęcie-zastępcze`

## Scope

- Game-scoped batch/entry/slot/retired schema, manifest magazynu, RLS i indeksy.
- Exact sourceIds, aliasy tej samej gry/SHA/atestowanego zakresu; deduplikacja zdjęć bez zaokrąglania do dziewiątek.
- Preview wszystkich plansz/seq/revisions/powodów/zależności, zapis planned, odczyt i eksport JSON/CSV.
- Istniejący board-source-cleanup-preview rozszerzony o mode; POST/GET w board-sources, bez drugiego cleanup service.
- Append-only ledger ocen człowieka zapisywany atomowo z A2 label i receiptem.
- Backend/OpenAPI/generated/wrapper/request tests i wybór źródeł w Adminie.

## Out of scope

Wycofanie, aktywne rezerwacje, usuwanie grafu/plików, import zamiennika i strażnicy B2a. Planned nie blokuje zwykłych importów. Przed retirement wymagany nowy podgląd.

## Acceptance criteria

- [x] Preview przypina dokładną tożsamość, także aliasy i obcych właścicieli; drift odmawia zapisu.
- [x] Manifest jest trwały i można go ponownie pobrać po restarcie/utracie odpowiedzi.
- [x] Idempotency + expected revision chronią każdą komendę; replay nie tworzy duplikatów.
- [x] Nie powstają aktywne rezerwacje/retired; canonical, historia, modele i pliki pozostają.
- [x] Ostatnia rozstrzygająca ocena człowieka dla aktualnych pikseli wygrywa niezależnie od wieku runu.
- [x] Readable wyłącza tylko powód danego pola mimo historycznego quality_issue; pending/skipped nie cofają rozstrzygnięcia.
- [x] Legacy sprzeczności bez chronologii blokują źródło; bez jawnej oceny obowiązuje wcześniejsze manual unreadable.
- [x] API i UI udostępniają całe źródła, powody, zakresy, blokery oraz JSON/CSV.
- [x] Testy, lint/typecheck, migracja izolowana, docs/code-map i audyt rozliczone.

## Technical notes

Każdy alias ma FK RESTRICT przez source_replacement_sources; nullable FK slotów obejmują nowy source/review, a batch/entry jest spójny. Strażnicy B2a nadal muszą poprzedzać skutki plikowe. Schema nie tworzy rezerwacji: tabele slots/retired są puste aż do B2b. Plan grupuje źródła tylko przez game/SHA/exact attested range, obejmuje wszystkie aliasy; niejednoznaczny zakres lub właściciel innego SHA blokuje całe zdjęcie. Sam SHA manifestu nie daje uprawnień.

Ledger ma ordinal per game/cell pod EXCLUSIVE ownership lock, unique command/cell i snapshot identity. Nie ma FK do efemerycznej projekcji cell. Legacy zgodne aktualne oceny zachowują wszystkie proof IDs/revisions; sprzeczne wymagają świeżej oceny. Zmiana pikseli nie przenosi oceny. Nowa jawna decyzja zawęża D-543 wyłącznie dla przyszłego kontrolowanego retirement.

Integracja main dodaje do coverage B2a grid_correction_split population/prepare/validate, photo-only register_cohort_use, freeze, currentness oraz workflow/recovery. Zachowane frozen kohorty i reporty pozostają czytelne.

## Expected files

Nowe domain/storage/schemas source_replacement, migrations 0173/0174, manifest v21 i testy. Istniejące api/cleanup.py, main.py, storage/symbol_readability.py, manifest routing/lifecycle importy, klient API i Admin cleanup/readability. Dokumentacja właścicielska, mapa kodu oraz konflikty integracji obu pionów.

## Verification

Python `D:/game_predicotr/.venv/Scripts/python.exe`, cwd worktree, PYTHONPATH wskazuje jego services. Ograniczone testy pionu, ruff/mypy, izolowany PostgreSQL, request/UI tests, typecheck, docs i mapa. Timeout poleceń 120 s; audyt 480 s, zewnętrzny 600 s. Testy planowane, wyniki w Outcome.

## Risks / open questions

Pełne retirement pozostaje niedostępne do B2b. Migracja i restart operatora mają odrębne zgody. Kolizje historycznych numerów commitów i obu D-578 zachowane, rozróżniane hashem/kotwicą.

## Outcome

Commit: v1.7.523 (hash dopisuje kolejny commit).

Manifest planned, aliasy/FK, ledger A2 i pion API/OpenAPI/klient/Admin gotowe. Retirement i aktywne reservations pozostają niedostępne. Zintegrowano pin main40581449; decyzją operatora commit zachowuje kolejny numer po branch HEAD522 mimo kolizji z main. Obie D-578 pozostają pod odrębnymi kotwicami.

Verification results: 13 testów unit/HTTP B1 + legacy cleanup PASS; 4 testy integracyjne PostgreSQL i 17 schema readiness PASS. Izolowana baza przechodzi pełną migrację 0174/provision; testy obejmują aliasy, dokładny krótki zakres, foreign pending, stale preview, nową sesję/replay, starszy run oceniony później, pending, rollback po ledger INSERT, odmowę po zmianie pikseli oraz runtime RLS SELECT/INSERT pod ograniczoną rolą. Test czysty obejmuje skipped i legacy sprzeczności/proof. Nie wykonywano migracji ani zmian danych operatora.

Ruff nowych modułów, cleanup, ledger integration i main PASS. Scoped strict mypy: domain/storage/schema B1 plus ApiModel (5 plików), Pydantic/SQLAlchemy sprawdzane, pozostałe importy aplikacji pominięte — PASS. Pierwszy szeroki silent-imports przerwany bez wyniku, bez osieroconych procesów. Admin typecheck z lokalnym aliasem worktree, scoped ESLint, 2 UI recovery tests PASS. Klient build, generated drift check i 2 request tests B1/A2 PASS. OpenAPI --check PASS; mapa zregenerowana. Cztery kontrole docs:check PASS przez Python root; npm wrapper wymaga nieobecnego lokalnego .venv. Nie zmieniano junction ani głównego checkoutu.

Audyt R1 Opus5.5/high: REVISE, modelUsage potwierdzone. P1-1 poprawione: immutable snapshot zachowuje pierwotny legacy proof bez dopisywania mu chronologii; pending/skipped nie usuwa sprzeczności, nowa decisive ocena rozstrzyga. Unit i PG obejmują konflikt, kolejne pending/skipped, nową ocenę i zmianę pikseli. P2-1 poprawione z HTTP testem rzeczywistej zależności: puste body daje 422, planned nie wywołuje recovery. P2-2 jawnie przekazane jako obowiązkowy zakres TASK-1128/B2a (kodowana blokada legacy cleanup przed skutkami ubocznymi); P2-3 zaakceptowane przez koordynatora zgodnie z regułami AGENTS dla P2 (bez nowej osobnej decyzji użytkownika): wszystkie błędy B1 zwracają 409. Celowany R2 PASS zamknął P1-1, bez nowych P0/P1 i bez ponownego audytu upstream. Raporty: `ai_docs/quality/TASK-1127_AUDIT_claude-opus-5-5.md` (R2), `ai_docs/quality/TASK-1127_AUDIT_claude-opus-5-5_R1.md` (historyczny). Oba modelUsage potwierdzają Opus5.5; łączny koszt audytów 1,3420008 USD. Opcjonalne poszerzenia testów z R2 odłożone: obecne asercje dowodzą zachowania pierwotnych proof i wykluczenia ich po zmianie identity. B1 nie było wdrożone, więc nie istnieją operatorowe wpisy ledgeru bez prior proof. Brak uruchomionych API/Admin/workerów, treningu, skanu lub retirement. Testy nie wymagają UI usług; interakcje są sprawdzone w jsdom, bez testu na fizycznym Androidzie. C1 otrzyma osobny request-v1 dopiero z B2b; eksport B1 jest wyłącznie manifestem planned. B2a musi poprzedzać skutki plikowe wspólnym guardem, także w nowych grid correction i retention ścieżkach.


Definition of Done porównane punkt po punkcie: kryteria funkcjonalne i granice B1 spełnione; kod ma oddzieloną kwalifikację, snapshot storage i HTTP/UI; migracje/RLS/FK oraz trwałość poleceń zweryfikowane; API/OpenAPI/generated/wrapper/request test zgodne; kontrola jakości i dokumentacja rozliczone. Loading/empty/error, jawne przyciski dotykowe i blokada podwójnego zapisu obecne. Fizyczny Android oraz migracja/restart operatora pozostają poza wykonaniem. Następny task: TASK-1128/B2a.
