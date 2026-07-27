---
title: Android release panel and artifact UI
status: done
last_updated: 2026-07-27
---

# TASK-0038 — Android release panel and artifact UI

## Status

`done`

## Goal

Dostarczyć w lokalnym panelu administracyjnym kompletny pion tworzenia
niezmiennego wydania Android, uruchamiania kontrolowanego workflow, monitorowania
powiązanego joba oraz wskazania zweryfikowanych artefaktów do ręcznej instalacji.

## Context

TASK-0036 dostarczył niezmienny wybór wersji gry i API release, a TASK-0037 jeden
resumowalny workflow kończący się zweryfikowanym snapshotem i APK. Panel nie
udostępnia jeszcze tych operacji administratorowi.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_03_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- formularz wersji release i wyboru od 1 do 15 aktywnych gier,
- wybór dokładnie jednej opublikowanej wersji datasetu i reguł per gra,
- walidacja kompletności oraz zgodności wymiarów przed wysłaniem,
- utworzenie niezmiennego draftu przez wygenerowany klient API,
- uruchomienie builda tylko dla draftu, bez pola na komendę lub ścieżkę,
- automatyczne odświeżanie release i powiązanego joba podczas builda,
- jawne statusy, etap, postęp i kontrolowany błąd joba,
- retry nieudanego workflow na tym samym jobie,
- historia release z dokładnym wyborem źródeł, checksumami i ścieżkami,
- kontrolowane pobranie gotowego APK oraz kopiowanie ścieżek artefaktów,
- stany loading, empty, error i retry,
- testy czystego stanu, akcji API, komponentu przez build produkcyjny i
  kontraktu pobierania artefaktu.

## Out of scope

- automatyczna instalacja APK na telefonie,
- dowolne komendy, dowolne ścieżki i eksplorator plików sterowany przez klienta,
- fizyczny Gradle build, macierz awarii i aktualizacja urządzenia (`TASK-0039`),
- benchmark 500 000 layoutów (`M3.5`),
- publiczna dystrybucja, chmura i Google Play.

## Acceptance criteria

- [x] Administrator tworzy draft z 1–15 kompletnymi wyborami gry/datasetu/reguł.
- [x] Panel pokazuje wyłącznie opublikowane, zgodne źródła aktywnych gier.
- [x] Build może zostać uruchomiony tylko dla draftu i nie przyjmuje komendy.
- [x] Aktywny release i jego job są odświeżane bez duplikowania żądań.
- [x] Błąd joba jest widoczny, a retry wznawia ten sam job.
- [x] Historia pokazuje niezmienne wersje, wybory, statusy, ścieżki i checksumy.
- [x] Gotowy APK można pobrać wyłącznie przez kontrolowany endpoint release.
- [x] Ścieżki snapshotu i APK można skopiować bez ujawniania ścieżki wejściowej
  po stronie API.
- [x] Loading, empty i error mają jawny tekst oraz bezpieczne ponowienie.
- [x] Panel używa wyłącznie wygenerowanego klienta i przechodzi pełną jakość.

## Assumptions

- Przeglądarka nie otwiera bezpośrednio katalogu Windows na podstawie ścieżki
  względnej API. Kontrolowane pobranie zweryfikowanego APK spełnia wymaganie
  udostępnienia artefaktu, a przyciski kopiowania pozwalają otworzyć lokalny
  katalog ręcznie.
- Endpoint pobrania rozwiązuje wyłącznie APK zapisane w gotowym release względem
  serwerowego katalogu artefaktów; klient nie przekazuje ścieżki.
- Lista release jest źródłem prawdy dla historii, a szczegół aktywnego release
  jest odświeżany podczas `building`.

## Expected files

- `apps/admin/src/features/releases/`
- `apps/admin/src/features/catalog/catalog-workspace.tsx`
- `apps/admin/src/components/admin-shell.tsx`
- `apps/admin/src/app/globals.css`
- router i composition root Admin API dla kontrolowanego pobrania
- OpenAPI i wygenerowany klient TypeScript
- testy panelu i API
- dokumentacja procesu, kontraktu i testów

## Verification

```powershell
npm test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
pytest services/api/tests/test_mobile_releases_api.py -q
npm run quality
```

## Risks / open questions

- Pobranie wymaga, aby lokalny Admin API i worker używały tego samego
  skonfigurowanego katalogu artefaktów; composition root musi mieć jawny,
  bezpieczny katalog bazowy.

## Outcome

- Dodano sekcję `Wydania Android` z formularzem dokładnych, zgodnych i
  opublikowanych źródeł dla 1–15 aktywnych gier. Draft jest niezmienny, a build
  nie ma pola komendy ani ścieżki.
- Panel pokazuje historię, pełny skład release, status tekstowy, etap i postęp
  powiązanego joba, błąd, retry tego samego joba oraz automatyczny polling bez
  równoległego żądania dla tego samego release.
- Snapshot i APK mają widoczne względne ścieżki i SHA-256. Gotowy APK jest
  pobierany przez wygenerowany klient i nowy kontrolowany endpoint, który
  ponownie sprawdza status, katalog, typ pliku, symlinki i checksumę.
- Zaakceptowano D-040 i udokumentowano wspólny
  `GAME_PREDICTOR_ARTIFACT_ROOT`; panel nie uruchamia Explorera ani dowolnych
  komend systemowych.
- Pełna bramka jakości przeszła: 221 standardowych testów Python, 64 mobile, 57
  panelu, 23 wspólnej domeny i 9 klienta API. Ponadto przeszło 7 fizycznych
  testów PostgreSQL oraz produkcyjny build Next.js. Fizyczny release APK i
  aktualizacja urządzenia pozostają zakresem TASK-0039.
