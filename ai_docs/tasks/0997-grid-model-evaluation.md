---
title: TASK-0997 — Ocena per gra i bramka kandydata
status: todo
last_updated: 2026-10-16
---

# TASK-0997 — Ocena per gra i bramka kandydata

## Status

`todo`

## Goal

Zapobiec publikacji poprawy jednej gry kosztem drugiej.

## Context

Task jest częścią zaakceptowanej rewizji 6. Metryki i bramka osobno dla gier. Realizacja całego planu i orientacyjny koszt 12–28 dni roboczych zostały jawnie zatwierdzone 2026-10-14.

## Dependencies / entry conditions

- D-556 report seam z0995: przed kodem0997 trzeba rozstrzygnąć pełny v2 reader/writer i globalną barierę aktualności wspólnego raportu. Zmiana danych dowodowych wymaga audytu high zgodnie z AGENTS i tabelą planu.
- TASK-0996 i niezależne, kompletne dane kontrolne.

- Zgoda na implementację nie zastępuje zgód operacyjnych wymaganych w tym tasku. Proponowane decyzje D-548–D-552 wymagają udokumentowanego przyjęcia przed zależną zmianą zachowania.

## Recommended execution

Zmiana ról na jawne polecenie operatora2026-10-16 po ukończeniu TASK-0995: Claude Code wykonuje, Codex audytuje. Historycznych raportów i wykonawców ukończonych zadań nie zmieniamy.

- Wykonawca: `claude-fable-5-1`, reasoning `high`. metryki i kwalifikacja publikacji.
- Dodatkowy review: `gpt-6-astra`, reasoning `high`, oddzielny kontekst, tylko do odczytu, brief ograniczony do diffu taska.
- Eskalacja: rozbieżność planu, kontraktu lub niedostępna konfiguracja modelu wymaga jawnego rozstrzygnięcia; bez ukrytego zamiennika.

## Relevant docs

- `AGENTS.md`
- [CURRENT_STATE](../process/CURRENT_STATE.md)
- [Plan rewizja 6](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md) — sekcje 2–5, właściwy opis taska w sekcji 6 i tabela modeli w sekcji 8.
- [VISION_LAB](../architecture/VISION_LAB.md).
- [VISION_LAB](../requirements/VISION_LAB.md).
- Zakres odczytu uzupełniający z planu: D-483, VISION_LAB, reguły oceny tego planu.

- [D-483](../process/decisions/DECISION_LOG_2026.md#d-483--metryka-nadrzędna-silnika-siatek-odsetek-zdjęć-kompletnych-i-poprawnych) — właściwy pełny wpis; odczyt tylko decyzji wskazanych dla tego taska.

## Scope

- Identyczne źródła dla bazy i kandydata, pełny inference od zdjęcia, wyniki per gra/nagranie.
- Wersjonowane definicje metryk.
- REGRESSION tylko do końcowej kontroli.

## Out of scope

- Nie zastępować nieznanej jakości zerowym błędem.

- Zmiany historycznej gry 777 (kod `7`), współdzielenie modeli symboli i automatyczne operacje na danych operatora poza osobną zgodą.

## Acceptance criteria

- [ ] Regresja dowolnej gry blokuje wspólny PASS.
- [ ] Brak detekcji ma koszt.
- [ ] Brak danych, parity lub aktualnych dowodów blokuje publikację.
- [ ] Dobór checkpointu nie używa REGRESSION.
- [ ] Wyniki właściwych kontroli, audytu i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu.

## Technical notes

Identyczne źródła dla bazy i kandydata, pełny inference od zdjęcia, wyniki per gra/nagranie. Wersjonowane definicje metryk. REGRESSION tylko do końcowej kontroli.

Chronione zachowanie: deterministyczna `sequence_number`, brak obcego przypisania symboli, ochrona ręcznych decyzji i danych kanonicznych. Nowe encje wymagają Alembic; zmiana API obejmuje OpenAPI, wygenerowany klient, wrapper i test żądania. Publikacja, aktywacja i rzeczywisty run pozostają odrębnymi operacjami. Szczegółowe kontrakty, źródła prawdy i błędy obowiązują z sekcji 2 i 4 planu; wyników jakości nie domniemywać.

### Ustalona granica rzeczywistego raportu (D-556, przed zależnym SQL)

Istniejący publication reader w domain/grid_model_publication.py pozostaje bez zmiany w0995: producer kolumny i JSON to server:grid-model-evaluator-v1, schema grid-model-evaluation-read-v1, policy grid-model-per-game-gate-v1 i zamknięty dotychczasowy zestaw pól. Nowy application-grid-evaluation-v1 nie jest zgodnym producentem i nie jest przyjmowany.

Nowy binding rozpoznaje wyłącznie przyszły grid-model-evaluation-read-v2 z tym samym zaufanym producer/policy. Jest to wersjonowane rozszerzenie istniejącego read modelu, nie równoległy model oceny. Wymagana część identyfikacyjna obejmuje schemaVersion, producer, policyVersion, versionId, baseVersionId, familyId i cohorts. Cohorts jest niepustą listą do100 różnych gier i kohort; każdy wpis ma dokładnie gameId, cohortId, manifestSha256. UUID mają kanoniczną postać, SHA to64 małe znaki hex. Wersja kolumny report.version_id musi równać się versionId JSON, a wybrany własny wpis, baza i rodzina muszą dokładnie odpowiadać stored header/manifest rzeczywistej kohorty. JSON ma limit1MiB i exact SHA całych UTF-8 report_json, z canonical_json/descriptor_sha256 obowiązującymi po stronie rzeczywistego writera. Walidator bindingu sprawdza pełny checksum, producer i wymagane tożsamości; nie nadaje PASS ani nie zastępuje walidacji pełnych metryk przez0997. Pozostała część raportu zachowuje dotychczasowe przypięte manifest/base/cohort/requiredGameIds/games i szczegóły oceny zgodnie z kompletnym v2 kontraktem, który0997 utrwali przed swoim kodem. Nie zamrażamy dziś fikcyjnego formatu metryk. Zgodność requiredGameIds, rzeczywistych cohort refs i całej oceny musi być sprawdzona przez0997.

0995 nie zmienia obecnego require_evaluation_evidence i nie tworzy przyszłych raportów/bindingów. Stary v1 raport nie jest dowodem nowego v2 cohort binding i otrzymuje typed unsupported-provenance, bez naruszania jego dotychczasowego odczytu. Bind może chronić również rzeczywisty raport negatywny; jakość/PASS nie jest warunkiem zachowania zależności. Nieistniejący, zmieniony lub niepowiązany raport jest odrzucany. Test pełnego rzeczywistego0997 producer → binding → withdrawal → blokada publication jest obowiązkowy później, bez fikcyjnej oceny teraz.

Transakcja bindingu dotyczy jednej własnej kohorty i aktualnego zakresu jednej gry, z atomowym use/event/receipt. Wspólny raport kilku gier nie może przepinać GameStorageRouter do innej gry w jednej transakcji.0997 ma dostarczyć trwały, idempotentny protokół przygotowania raportu i oddzielnych własnych game bindings; brak choć jednego wymaganego bindingu lub aktualnego dowodu blokuje publikację/aktywację/default nowego v2 kandydata. Globalna bariera aktualności raportu musi uwzględnić notices wszystkich objętych gier bez owner fallback/obcych source partition reads i bez odwrócenia catalog→registry→ownership kolejności. Potrzebny most minimalnych notices/validation proofs i jego exact uprawnienia wymagają osobnego pełnego kontraktu przed kodem0997;0995 nie przedstawia tego mostu ani wspólnej publikacji jako wykonanych. Nie zakładamy fikcyjnej pojedynczej transakcji wszystkich gier. Dotychczasowe v1 historyczne dowody i już przypięte modele zachowują własne kontrakty.

## Expected files

- Istniejące: [neural_grid_training.py](../../services/worker/src/game_predictor_worker/vision_lab/neural_grid_training.py) — `compute_losses`, `train_run`, `evaluate_network`.
- Istniejące: [gate.py](../../services/worker/src/game_predictor_worker/geometry_core/gate.py) — `GateThresholds`, `compare`, `decide`, `gate_photo`.
- Pozostały zakres wskazany w zaakceptowanym planie: i istniejące metryki; nowe proponowane `services/worker/src/game_predictor_worker/training_core/grid_evaluation.py`, `services/api/src/game_predictor_api/application/grid_model_evaluation.py`, `grid-model-comparison.tsx`.

Nowe pliki/symbole są proponowane, nie istniejącą implementacją. Przed kodowaniem sprawdzić je z CODE_MAP i CODE_MAP_SYMBOLS; ograniczyć diff do tego pionu.

- Nowy proponowany test pionu: `services/worker/tests/test_grid_model_evaluation.py`; obejmuje poniższe kryteria, restart i konflikty właściwe dla taska. Nazwa/symbole testów zostaną ustalone przy implementacji; nie jest to istniejący test.

## Test cases

- Rzeczywisty v2 report writer jest akceptowany przez publication reader; v1 kontrakt bez regresji. Brak jednego multi-game bindingu, stale proof, crash/restart i withdrawal blokują nową kwalifikację; bez rebind/fallback/obcych source partition reads. Nowy most aktualności/proofs wymaga pełnego kontraktu przed kodem0997.
- Regresja dowolnej gry blokuje wspólny PASS.
- Brak detekcji ma koszt.
- Brak danych, parity lub aktualnych dowodów blokuje publikację.
- Dobór checkpointu nie używa REGRESSION.

## Verification

Zakres: WORKER, API, ADMIN, OpenAPI.

Polecenia z katalogu worktree, każde z twardym timeoutem do 120 s. Istniejące testy poniżej są regresjami, a nie pełnym dowodem nowego pionu. Nowy proponowany test z Expected files musi także zostać wykonany po implementacji. To kontrole planowane; dobór skoncentrowanych nowych testów, Ruff i mypy nastąpi po wskazaniu zmienionych modułów, przed szerszym zestawem. MIG oznacza wyłącznie izolowaną bazę testową.

```powershell
npm run test --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run openapi:check
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_verified_training_datasets.py
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_vision_lab_neural_grid.py
```

Warunek zaliczenia: spełnione kryteria i brak otwartych P0/P1 audytu. Brak danych, anotacji lub wykonanej kontroli raportować jawnie. Nie uruchamiać usług, produkcyjnej migracji, treningu ani masowego przetwarzania jako części kontroli.

## Risks / open questions

- Nie zastępować nieznanej jakości zerowym błędem.

## Outcome

### Execution phase

- Nie rozpoczęto.
- Original base: v1.7.360 / `171e23799ebdbee4ed4590a53376bf870c6741c2`.
- Zatwierdzony upstream/current HEAD: main v1.7.362 / `885ba12fb56305a47871daf743973c84469ad23d` (operator 2026-10-14); oryginalna baza pozostaje zapisana powyżej.
- Worktree: `D:\game_predicotr\worktrees\v3-grid-fine-tuning`; branch `codex/v3-grid-fine-tuning`.
- Commit: nie utworzono; następny patch ustalić z rzeczywistej historii gałęzi.
- Audit: wymagany `gpt-6-astra`, reasoning `high`; raport jeszcze nie istnieje, otwarte uwagi jeszcze nie ustalone.
- Następny krok: sprawdzić warunki wejściowe i ponownie odczytać task oraz odpowiadający fragment planu.

### Changed

- Nie rozpoczęto. Docelowy zapis wyniku: porównanie, wersja polityki i powody PASS/REVISE/braku możliwości oceny.

### Verification results

- Kontrole aplikacji nieuruchomione; powyższe komendy są planowane.

### Not completed

- Implementacja, kontrole, audyt, commit i integracja.

### Documentation updates

- Plik taska utworzony przez TASK-1015.

### Recommended next task

- TASK-1006
