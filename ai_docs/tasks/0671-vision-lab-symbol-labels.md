---
title: TASK-0671 — T06 — etykiety symboli
status: blocked
last_updated: 2026-09-27
---

# TASK-0671 — T06 — etykiety symboli

## Status

`blocked` — T06a odebrane; T06b wymaga rzeczywistych zatwierdzeń symboli i kwalifikacji zbioru. Nadrzędne T06 pozostaje aktywne, dlatego ten plik nie trafia do `completed/`.

## Goal

Zbudować zbiór symboli z weryfikowalnym pochodzeniem DB lub lab.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

T06a wymaga zweryfikowanego snapshotu, dostępnego magazynu geometrii i bezpiecznej konfiguracji osobnego magazynu symboli. Puste słowniki nie blokują budowy narzędzi, które służą ich zatwierdzaniu. T06a nie oznacza ukończenia T03 ani kwalifikacji danych.

T06b wymaga rzeczywistych zatwierdzonych słowników i etykiet oraz spełnienia dotyczących symboli bramek pochodzenia i podziału T03. Wyjątki D-453/D-456 nie są zgodą na symbole historycznych 777 ani na użycie geometrycznego podziału całymi grami w treningu symboli. Brak danych lub niezbędnej decyzji operatora zatrzymuje T06b oraz zależne T07–T09. T06 pozostaje otwarte po ukończeniu samych narzędzi.

Przed kodowaniem ponownie sprawdź bieżący kod, dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz w planie i tasku.

## Recommended execution

`gpt-6-sol`, reasoning `medium`; osobny audyt `gpt-6-sol`, reasoning `medium`. Proweniencja cropów i słowniki decydują o legalnym wejściu danych do treningu. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T06 — etykiety symboli)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447, D-453, D-456 i doprecyzowanie bootstrapu T06)
- `ai_docs/delivery/VISION_LAB_SYMBOL_LABELS_CONTRACT.md` (pełny kontrakt T06a; wymagany przed implementacją)

## Scope

Import kwalifikujących zatwierdzeń DB, decyzje lab_human_approved, lokalne słowniki, tożsamość cropa i ponowne zatwierdzenie po recrop.

T06a dostarcza narzędzia, adapter zweryfikowanego eksportu DB, zgodny pion API/klienta/UI, trwałość i testy. T06b dotyczy operacyjnego zbioru, nie samych testów na fixture. Każde podzadanie ma własny audyt, commit i Outcome. Żadne nie zatwierdza klas lub zdjęć za operatora.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [x] Mechanizm sprawdzania źródła próbki przetestowany; unknown/unreadable/grid issue poza klasami; brak mapowania nie tworzy rekordów DB. Nie jest to odbiór rzeczywistego zbioru.
- [x] T06a: pusty bootstrap, niezmienne wersje słownika, dokładna tożsamość cropa, drift, CAS/retry, restart i backup/restore pokryte testami; dotychczasowe dane geometrii pozostają zgodne.
- [x] T06a: nowe trasy mają generowany kontrakt, zamknięte proxy, test żądania i ochronę holdoutów przed dekodowaniem.
- [ ] T06b: rzeczywiste zatwierdzenia i raport kwalifikacji; brak danych nie jest raportowany jako ukończenie zbioru.
- [ ] Audyt przypisanym modelem nie pozostawia P0–P2; zmiana ma osobny commit, Outcome i CURRENT_STATE.

## Technical notes

Zachowaj kontrakty z planu i właścicieli istniejących decyzji. Błędy wejścia oznaczaj per źródło lub próbka, a błąd integralności i infrastruktury zatrzymuje zależny run. Nie promuj predykcji do ręcznego zatwierdzenia. Istotne odstępstwo wymaga aktualizacji planu przed implementacją.

## Expected files

- Istniejące `services/worker/src/game_predictor_worker/symbols/training_job.py` (reguły DB). Nowe (proponowane) `services/worker/src/game_predictor_worker/vision_lab/symbol_labels.py::qualify_symbol_sample`, `apps/vision-lab/src/components/symbol-label-editor.tsx::SymbolLabelEditor`, `services/worker/tests/test_vision_lab_symbol_labels.py`.

## Test cases

- Recrop i rewizja geometrii wykluczają próbkę; predykcja nie jest approval; słownik lokalny bez DB; konflikt klasy fail-closed.

## Verification

Z katalogu repozytorium (proponowany nowy test powstaje w tym tasku):

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @('-m','pytest','services/worker/tests/test_vision_lab_symbol_labels.py') -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'pytest timeout 120s' }
if ($p.ExitCode -ne 0) { throw "pytest exit $($p.ExitCode)" }
```

Po teście wykonaj lint/typecheck zmienionych modułów i wymagane kontrole kontraktu, każdą jako skończony proces z limitem maksymalnie 120 s. Testy tu są planowane, niezaliczone; zaliczenie wymaga kryteriów powyżej i braku regresji.

## Risks / open questions

- Zmiana schematu danych, zakresu zdjęć lub kosztu poza planem wymaga jawnej aktualizacji przed zależnym działaniem.

## Outcome

T06a odebrane technicznie 2026-09-27. Wykonawca Sol medium, niezależny
audyt Sol medium PASS bez otwartych P0–P2. Pre-code zamknął trzy P2;
audyt implementacji zamknął trzy dalsze P2 w dwóch cyklach. Drobna P3
responsywności poprawiona i odebrana osobno. Commit T06a: do zapisania
po kontroli indeksu; bazowy HEAD v1.7.30 / 4072dd53a260677e60a24c49f870e7ef1a58c093.

Preflight wykazał brak słowników i etykiet w snapshotcie folderowym.
D-458 rozdziela narzędzia T06a od rzeczywistych danych T06b, bez osłabienia
bramek. D-453/D-456 nie zatwierdzają symboli ani podziału symbolowego.

### Changed

- Panel `/symbols`, formularz słownika, jawne zatwierdzenia cropów, stany nieznany/nieczytelny/błąd siatki, wycofanie i identyczny retry.
- Osobny magazyn, niezmienne wersje i historia decyzji, dokładna tożsamość RGB/PNG, CAS i blokady międzyprocesowe, backup/restore do nowego celu.
- Adapter zweryfikowanego eksportu DB tylko do odczytu; brak sesji DB i automatycznego mapowania.
- Pełny pion API/OpenAPI/klient/proxy/UI; operator ukryty, toasty, numeracja od 1, responsywny układ.

### Verification results

- Niezależnie: 73 backend, 40 UI i 10 klienta PASS. Wykonawca: 43 backend oraz osobna częściowo pokrywająca się seria 39 regresji PASS.
- Ruff, Mypy (8 modułów), ESLint, TypeScript, OpenAPI/generated check, format i diff check PASS. Build PASS.
- Osobne reprodukcje błędnego legacy splitu i podmiany źródła DB po starcie poprawnie blokowane; CLI backup/restore w nowych procesach PASS.
- Read-only odbiór realnego API/UI po restarcie procesów: 0 etykiet, 0 słowników, symbol revision 0, geometry revision 268. Magazyn symboli nie został utworzony; SHA geometrii bez zmian: `084bc39de16502de46f6237cbc2fb453a9dc00665ab20d1319301f44f6efa314`.
- Browser QA desktop i viewport 390 PASS; końcowe pageWidth=clientWidth=375, bez poziomego przepełnienia. Nie zatwierdzano przykładów operatora. Dowody/logi: `ai_docs/quality/VISION_LAB_SYMBOL_LABELS_20260927.md`.

### Not completed

- T06b: brak rzeczywistych zatwierdzonych słowników/etykiet oraz kwalifikowanego podziału symboli; nie wykonywano T07–T09, treningu ani aktywacji.
- Nie wykonano restartu systemu ani testu fizycznego Androida. Nie uruchamiano pełnego repo quality, benchmarków, sesji DB, destrukcyjnych operacji, push ani merge.

### Documentation updates

- D-458, plan etapu C, pełny kontrakt T06a, wymagania/architektura, przewodnik uruchomienia i raport jakości; CURRENT_STATE aktualizowany.

### Recommended next task

- Domknąć T06b: rzeczywiste klasy i etykiety symboli z zatwierdzeń operatora albo zgodnego eksportu DB, następnie kwalifikacja pochodzenia i podziału per gra. Nie rysować ponownie poprawnych siatek. Nie omijać zamrożonych holdoutów ani roli historycznych 777.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T06a — narzędzia i adaptery | `gpt-6-sol` | `medium` | Trwałość decyzji, słowniki i tożsamość cropów. | `gpt-6-sol`, `medium` |
| T06b — kwalifikacja rzeczywistego zbioru | `gpt-6-sol` | `medium` | Weryfikacja pochodzenia i bramek danych, bez zastępowania decyzji operatora. | `gpt-6-sol`, `medium` |
