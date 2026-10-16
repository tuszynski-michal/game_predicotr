---
title: TASK-1001 — Odbiór procesu i instrukcja operatora
status: done
last_updated: 2026-10-16
---

# TASK-1001 — Odbiór procesu i instrukcja operatora

## Status

`done`

## Goal

Potwierdzić działanie całego procesu i możliwość dalszej pracy bez historii czatu.

## Context

Task jest częścią zaakceptowanej rewizji 6. Odbiór procesu i dokumentacja trwałości. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- Ukończone piony aplikacji i audyty.
- Odbiór na rzeczywistych danych wymaga właściwych zgód i anotacji; wynik wspólnego modelu raportowany oddzielnie.
- Istniejąca kopia operatora: `D:\game_predictor_backup`, wskazana 2026-10-14 jako wystarczająco aktualna. Nie tworzyć nowego snapshotu ani dodatkowego backupu bazy. Nie mylić tego z niezmiennymi snapshotami kohort treningowych.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

Zmiana ról na jawne polecenie operatora2026-10-16 po ukończeniu TASK-0995: Claude Code wykonuje, Codex audytuje. Historycznych raportów i wykonawców ukończonych zadań nie zmieniamy.

- Wykonawca: `claude-opus-5-5`, reasoning `high` (zamiennik `claude-fable-5-1`/`medium`; wybór wykonawcy po sugestii operatora 2026-10-16, uzasadnienie w sekcji 8 planu). integracja i dowody trwałości.
- Dodatkowy review: `gpt-6-astra` (przy braku dostępności `gpt-6.1-sol`), reasoning `medium`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../../process/CURRENT_STATE.md)
- [Plan rewizja 6](../../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [DEFINITION_OF_DONE](../../process/DEFINITION_OF_DONE.md).
- [AUDIT_REPORT_TEMPLATE](../../quality/AUDIT_REPORT_TEMPLATE.md).
- Zakres odczytu uzupełniający z planu: DEFINITION_OF_DONE, AUDIT_REPORT_TEMPLATE, dokumenty właścicielskie tasków.

## Scope

- E2E na izolowanej bazie: korekta → kohorta → run → ocena → aktywacja → wybrany przebieg → restart.
- Osobno aktualna baza bez treningu, propozycja i przyjęcie przez człowieka.

## Out of scope

- Bez automatycznego wdrożenia, push, migracji operatora i masowego przetwarzania.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Proces działa po restarcie i utracie odpowiedzi; obie gry i nowa gra zachowują izolację symboli.
- [ ] Stara 777 ma regresję.
- [ ] Rzeczywiste liczby i ograniczenia są opisane bez domniemanych wyników.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

E2E na izolowanej bazie: korekta → kohorta → run → ocena → aktywacja → wybrany przebieg → restart. Osobno aktualna baza bez treningu, propozycja i przyjęcie przez człowieka.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

### Kontrakt przed kodem (2026-10-16, Claude Code)

- Nowy test `services/api/tests/integration/test_v3_grid_fine_tuning_acceptance_postgres.py` (PostgreSQL + CUDA) łączy rzeczywiste ogniwa w jeden przebieg: ludzkie korekty → nagrania i role → zamrożona kohorta → run przez serwis i lane `grid-training` z prawdziwym trenerem, SQL store i rejestracją → ocena per gra (serwis, handler, SQL store; silniki ONNX oceny są deterministycznymi atrapami, jakość nie jest deklarowana) → publikacja → aktywacja → nowy interpreter rozwiązuje aktywną wersję resolverem importu i uruchamia wytrenowany model na CPU. Utrata odpowiedzi: powtórzenie runu, oceny, publikacji i aktywacji tym samym kluczem zwraca ten sam wynik.
- Ponowne rozpoznanie aktualną bazą bez treningu, propozycja i przyjęcie przez człowieka, izolacja symboli gier oraz regresja starej 777 są dowodzone istniejącymi testami TASK-0999/1003/1013/1004/1011/1018, uruchomionymi w odbiorze.
- P2-5 TASK-0995: prawdziwy wzorzec `.tmp-*.part` po sukcesie, replay i przerwanym zapisie.
- Regresje odbioru: test migracji 0163 po scaleniu `main` (dwie głowice poniżej 0164, powrót do head przed użyciem).
- `scripts/manage_worker_lanes.ps1`: lane `grid-training` z trwałym wyborem interpretera CUDA (parametr, zmienna `GAME_PREDICTOR_GRID_TRAINING_PYTHON`, `.venv-vision-lab` checkoutu); `all` obejmuje go tylko z interpreterem.
- Porównanie interakcji Admina z baseline HEAD380 po nazwach porażek.
- Dokumenty: instrukcja operatora `guides/V3_GRID_FINE_TUNING_OPERATOR.md`, raport `quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md`, zamknięcie rejestru obowiązków regresyjnych.

## Expected files

- Pozostały zakres wskazany w zaakceptowanym planie: nowe proponowane `ai_docs/guides/V3_GRID_FINE_TUNING_OPERATOR.md`, `ai_docs/quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md`, testy odbiorowe; wymagania, architektura, mapy i stan.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/api/tests/test_v3_grid_fine_tuning_acceptance.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Przeniesione P2-5 z TASK-0995/ClaudeR2PASS: w test_immutable_publish_survives_new_store_and_lost_response zastąpić stary glob*.staged faktycznym.tmp-*.part i sprawdzić brak resztek po sukcesie/replay. To accepted niskie ryzyko pokrycia, nie otwartyP0/P1; produkcyjne finally bez zmiany, real hard-crash/guardedscan/24h regression jużPASS.
- Proces działa po restarcie i utracie odpowiedzi; obie gry i nowa gra zachowują izolację symboli.
- Stara 777 ma regresję.
- Rzeczywiste liczby i ograniczenia są opisane bez domniemanych wyników.

## Verification

Zakres: API, WORKER, ADMIN, REVIEWER, wymagane buildy, OpenAPI, DOC, MAP.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run docs:check
git diff --check
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run test:geometry --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run openapi:check
npm run code-map:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_virtual_grid_geometry.py services/api/tests/test_catalog_api.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_vision_lab_training_core.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Bez automatycznego wdrożenia, push, migracji operatora i masowego przetwarzania.

## Outcome

### Execution phase

- Commit: v1.7.393 / `161751ec1987256544ee7ea3ce9157ba1c1efcff`.
- Wykonano 2026-10-16: Claude Code `claude-opus-5-5`/`high`, baza v1.7.392 / `eb2126294ef4854634c434d46b0573b2bba8c34a` (gałąź po scaleniu `main` v1.7.385 w v1.7.391), branch `codex/v3-grid-fine-tuning`, worktree `D:\game_predicotr\worktrees\v3-grid-fine-tuning`.
- Kontrakt przed kodem w Technical notes. Bez migracji i zmian API; jedna poprawka kodu produkcyjnego (D-561, eksport ONNX), reszta to testy, skrypt lane i dokumentacja.
- Audyt R1: Codex `gpt-6-astra`/`medium`, limit 2400 s — [raport R1](../../quality/TASK-1001_AUDIT_gpt-6-astra_R1.md), werdykt REVISE: P0-1 (status i stop lane GPU zależne od interpretera bieżącego wywołania), P1-1 (instrukcja: ponowne rozpoznanie także zapisuje automatycznie), P2-1 (opis `workers:start`). Jedna runda poprawek poniżej.
- Audyt R2: [raport R2](../../quality/TASK-1001_AUDIT_gpt-6-astra_R2.md), werdykt **PASS**, brak P0/P1/P2; zamknięte P0-1, P1-1, P2-1.

### Changed

- Nowy test odbioru `services/api/tests/integration/test_v3_grid_fine_tuning_acceptance_postgres.py`: korekty człowieka → nagrania → zamrożona kohorta → run przez serwis → lane `grid-training` z trenerem CUDA, SQL store i rejestracją → ocena per gra → publikacja → aktywacja → nowy interpreter rozwiązuje aktywną wersję resolverem importu i uruchamia model na CPU; ponowienia tym samym kluczem.
- D-561: parity eksportu ONNX względna do max(1, |wyjście torch|) (`training_core/grid_training.py` `parity_verdict`/`scaled_delta`), zapis `parity-failed.json` przy błędzie (`images/grid_training_child.py`), test jednostkowy; wpis decyzji, indeks (D-532 do archiwum indeksu), VISION_LAB.
- Testy nieaktualne po migracjach V3 (wyłącznie testy): 16 konsumentów bieżącego manifestu v15/v16 → v17, kontrola wersji routingu w baseline i izolacji, literały manifestu i head, wyzwalacze V3 w routingu, capability przed 0161 w panelach, `idempotencyKey` w M2, dwie głowice w cyklu baseline, fixtura `no_job_admission` w sześciu testach `test_image_batch_store.py`, deterministyczny wybór gry w teście statystyk, test migracji 0163 wraca do head, P2-5 TASK-0995 (`.tmp-*.part` po sukcesie, replay i przerwanym zapisie).
- `scripts/manage_worker_lanes.ps1`: lane `grid-training` z interpreterem CUDA z parametru `-GridTrainingPython`, zmiennej `GAME_PREDICTOR_GRID_TRAINING_PYTHON` albo `.venv-vision-lab`; `all` obejmuje go tylko z interpreterem; `npm run workers:start:grid-training`.
- Reviewer: test kontraktu proxy uzgodniony z D-555 (tylko zakresowe `geometry-approvals`).
- Dokumenty: instrukcja operatora `guides/V3_GRID_FINE_TUNING_OPERATOR.md`, raport `quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md`, zamknięty rejestr `quality/V3_BACKEND_REGRESSION_OBLIGATIONS_20261015.md`.

### Runda poprawek po audycie R1

- P0-1: `Get-TargetLaneNames` pomija lane `grid-training` bez interpretera CUDA wyłącznie dla `Start -Lane all`; `Status` i `Stop` obejmują zawsze wszystkie lane i zapisane procesy. Regresja `services/api/tests/test_manage_worker_lanes_script.py` (izolowana kopia skryptu, fałszywy zapisany proces): status pokazuje działający worker GPU i stop go zatrzymuje bez interpretera; jawny start bez interpretera odmawia i nic nie zapisuje — 2 PASS.
- P1-1: instrukcja opisuje skutki ponownego rozpoznania według stanu celu z sekcji 2.5 planu: propozycja dla „Złej siatki”, ochrona decyzji człowieka, zapis automatyczny odroczonych slotów i niechronionych automatycznych plansz po bramkach, konflikt przy zmianie źródła, obowiązkowy pilot do 100 zdjęć i osobne potwierdzenie szerszego zakresu.
- P2-1: osobne opisy `workers:start` (tylko `general`), `workers:start:all` (warunkowo z `grid-training`) i `workers:start:grid-training`.

### Verification results

- Test odbioru: PASS w 464 s (trening 1200 kroków 351 s, PASS oceny, publikacja i aktywacja, restart). Pierwszy przebieg ujawnił `GRID_TRAINING_ONNX_PARITY_FAILED` (D-561), drugi długość ścieżki katalogu testu.
- API 3261 PASS / 484 skip / 0 FAIL; worker 3040 PASS / 43 skip / 17 FAIL środowiskowych (jak TASK-0997); GPU E2E 2 PASS; Admin unit 772/772, interakcje 281/291 z tymi samymi 10 porażkami co HEAD380; Reviewer 279/279 i 95/95; klient 129/129; buildy Admin i Reviewer, `openapi:check`, ruff/mypy zmienionych plików PASS.
- PostgreSQL pełny zestaw: 506 testów, pierwszy przebieg 20 FAIL i 1 ERROR, sklasyfikowane względem czystego `main` (27 testów, 3 FAIL `main`); po poprawkach 26 dotkniętych plików sekwencyjnie: 241 testów, 236 PASS, 4 skip, 1 FAIL; testy GC: kwarantanna PASS, retencja 1 PASS i 1 FAIL. Obie porażki to znana usterka `reset_game` sprzed V3 (identyczna na `main`, zapisana od TASK-0999).

### Not completed

- Poprawka `reset_game` (kolejność usuwania zależności i usuwanie plików przed bazą): usterka sprzed V3, poza planem; zaproponowana osobna sesja. Akcji „usuń dane układu gry” nie używać do czasu poprawki.
- 17 testów worker uruchamiających podproces nie przejdzie w worktree z dowiązanym `.venv`; po scaleniu do `main` sprawdzić je w głównym checkoucie.
- Rzeczywisty trening, ocena, publikacja i aktywacja na danych Mumii i 777a2 oraz odbiór w przeglądarce — po integracji, za osobną zgodą operatora.
- Interpreter `.venv-vision-lab` istnieje tylko w checkoucie na C; checkout D go nie ma.

### Documentation updates

- Instrukcja operatora, raport odbioru, D-561, VISION_LAB, rejestr obowiązków, CURRENT_STATE, CODE_MAP.

### Recommended next task

- Integracja planu do `main` (zgoda operatora z 2026-10-16): scalenie `main`, preflight, stop usług, fast-forward i push, `npm install`, `npm run db:migrate` do 0166, restart usług i testy na `main`.
