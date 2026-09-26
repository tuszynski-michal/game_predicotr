---
title: TASK-0667 — T02 — kontrakty i galeria
status: done
last_updated: 2026-09-26
---

# TASK-0667 — T02 — kontrakty i galeria

## Status

`done`

## Goal

Pokazać zdjęcia, siatki i cropy przez bezpieczny lokalny pion API–OpenAPI–klient–UI.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

T01 done i opublikowany snapshot. Przed kodowaniem ponownie sprawdź bieżący kod, dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz w planie i tasku.

Wznowienie 2026-09-26: użytkownik dostarczył folder
`C:\Users\tuszy\Documents\new_traning_set` do testowania modelu oraz utworzył
`C:\Users\tuszy\Documents\game_predictor_vision_data`. Wejście zawiera 1180
JPEG-ów w sześciu folderach gier (777: 240, blazing zd: 120, gang zd: 190,
mumie wybrane: 240, reels: 230, tresure zd: 160). Nie jest snapshotem DB.
T02 przygotowuje lokalny snapshot plikowy przed uruchomieniem galerii;
tożsamości lokalne nie udają identyfikatorów bazy. Źródła pozostają bez zmian.
Wszystkie obrazy są na tym etapie materiałem do podglądu/testowania, bez
zatwierdzonych etykiet ani kwalifikacji treningowej. Historyczne `777`
pozostaje `comparison_only`. Prefiksy przed `__` dają 118 kandydatów rodzin,
lecz nie dowodzą niezależności nagrań; T03 musi zweryfikować pochodzenie.
Pełen folder może zasilać galerię; limit pilota anotacji pozostaje bez zmian.
Kontrola SHA-256 wykazała 1160 unikalnych obrazów i 20 par duplikatów w
`reels` (rodziny `REELS450100`/`REELS451200`, `REELS471200`/`REELS475500`).
Manifest zachowuje wystąpienia i wspólny hash. Wybór splitu pozostaje w T03.

## Recommended execution

`gpt-6-sol`, reasoning `medium`; osobny audyt `gpt-6-astra`, reasoning `medium`. Pion UI, OpenAPI i zabezpieczeń HTTP przecina kilka modułów. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T02 — kontrakty i galeria)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447)

## Scope

Wspólne GeometryEngine/GeometryResult/SymbolRecognizer, adapter baseline, galeria Next.js, FastAPI, allowlist proxy, Host/Origin/JSON, zarejestrowane assety i klient generowany.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [x] Wyniki na dostarczonych zdjęciach; 3 × 3 jawnie unsupported, jeśli baseline nie obsługuje; błąd obrazu nie blokuje galerii; obcy Host/Origin/trasa i prosty POST odrzucone.
- [x] Audyt przypisanym modelem nie pozostawia P0–P2; zmiana ma osobny commit, Outcome i CURRENT_STATE.

## Technical notes

Zachowaj kontrakty z planu i właścicieli istniejących decyzji. Błędy wejścia oznaczaj per źródło lub próbka, a błąd integralności i infrastruktury zatrzymuje zależny run. Nie promuj predykcji do ręcznego zatwierdzenia. Istotne odstępstwo wymaga aktualizacji planu przed implementacją.

## Expected files

- Istniejące `services/worker/src/game_predictor_worker/images/screen_layout_v3/engine.py::detect_screen_layout_v3` (adapter), `services/api/src/game_predictor_api/domain/board_topology.py::BoardTopology`, `package.json::openapi:check`. Nowe (proponowane) `services/worker/src/game_predictor_worker/vision_lab/contracts.py::GeometryResult`, `.../api.py::app`, `apps/vision-lab/src/app/page.tsx::Page`, `packages/vision-lab-api-client/`, `services/worker/tests/test_vision_lab_api.py`.

## Test cases

- 24/16 węzłów i poprawne cropy; uszkodzony obraz obok poprawnego; obcy Host/Origin, brak Origin, niedozwolona trasa i asset path; wygenerowany klient zgodny z OpenAPI.

## Verification

Z katalogu repozytorium (proponowany nowy test powstaje w tym tasku):

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @('-m','pytest','services/worker/tests/test_vision_lab_api.py') -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'pytest timeout 120s' }
if ($p.ExitCode -ne 0) { throw "pytest exit $($p.ExitCode)" }
```

Po teście wykonaj lint/typecheck zmienionych modułów i wymagane kontrole kontraktu, każdą jako skończony proces z limitem maksymalnie 120 s. Testy tu są planowane, niezaliczone; zaliczenie wymaga kryteriów powyżej i braku regresji.

## Risks / open questions

- Zmiana schematu danych, zakresu zdjęć lub kosztu poza planem wymaga jawnej aktualizacji przed zależnym działaniem.

## Outcome

Implementacja i audyt zakończone. Użytkownik wybrał numerację zgodną
z AGENTS.md: `v1.7.1` po historycznym `v1.7` (`6eb1d646`). Następny
commit w tym torze zwiększa patch do `v1.7.2`. Etap A kończy się na STOP A.

Commit: `v1.7.1` — `fb188b9ee6bd9263604a19cc7b1904f6d11edd3a`.
Hash dopisano po commicie; ten wpis pozostaje lokalną aktualizacją
dokumentacji do kolejnego commita, bez zmiany hasha ukończonego taska.

### Changed

- Kontrakty geometrii/symboli, adapter istniejącego baseline, galeria Next.js,
  FastAPI i zamknięty proxy, generowany klient i kontrola dryfu OpenAPI.
- Snapshot plikowy dostarczonych 1180 JPEG-ów, idempotentny retry,
  lokalne tożsamości i duplikaty bez usuwania źródeł oraz bez etykiet.
- Zasady doboru modeli w planie i aktywnych taskach zgodnie z decyzją
  użytkownika: najmniejszy adekwatny audytor, maksimum Astra medium.

### Verification results

- Python 19/19, testy granicy UI 2/2, test żądania klienta 1/1.
- Ruff/format, scoped mypy 8 modułów, ESLint, oba typechecki, Prettier,
  production build i główne `openapi:check` przeszły.
- Snapshot retry i odczyt 1180 źródeł w nowych procesach, smoke po jednym
  zdjęciu na grę oraz odbiór UI: filtr, duplikaty, overlay/cropy, 3 × 3
  unsupported. Audyt Sol medium → Astra medium, cykl 2 bez P0–P2.
- DoD: pion API–OpenAPI–klient–UI spójny, błędy źródeł i HTTP przetestowane,
  dokumentacja i instrukcja restartu zapisane. Brak zmian DB/produkcyjnych
  konsumentów. Nie dotyczy migracja ani domenowe numery sekwencji.

### Not completed

- Etap B, anotacje, trening, aktywacja, push/merge i migracje poza zakresem.
- Nie wykonano pełnego zestawu testów repo ani fizycznego testu Androida;
  sprawdzono wąski viewport przeglądarki desktopowej. Baseline 3 × 3 jest
  jawnie unsupported. Szerokie mapowanie wyjątków API pozostaje uwagą
  diagnostyczną niższego priorytetu, nie nierozwiązanym P0–P2.

### Documentation updates

- Plan i przypisania modeli, architektura, D-447, CURRENT_STATE, indeks,
  `guides/VISION_LAB_LOCAL.md`, `quality/VISION_LAB_STAGE_A_ACCEPTANCE.md`.

### Recommended next task

- STOP A. Po osobnym uruchomieniu etapu B: TASK-0668, edytor anotacji,
  kontrola pochodzenia, split i backup; bez automatycznego treningu teraz.
