---
title: TASK-0582 — Spójność stagingów po imporcie
status: done
---

# TASK-0582 — Spójność stagingów po imporcie

## Goal

Naprawić zgłoszony lifecycle stagingów, ochronić przed ponownym cięciem,
odtworzyć bezpieczne wejście brakującej geometrii i sprawdzić duplikaty.

## Context

Lista rozpoznaje tylko completed, pomijając waiting_for_review po cięciu.
Start dopuszcza kolejny import przy nowym fingerprintcie. Usuwanie po uploadId
nie przypina gry przed odczytem tabel należących do game_data_v2.
W bazie istnieją dwa importy stagingu 9c7de0ca z powielonymi planszami.

## Relevant docs

- ai_docs/requirements/IMAGE_INGESTION.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/PLAN_STANDARD.md

## Scope / acceptance criteria

- [x] Importowany staging pokazuje etap cięcia/weryfikacji i nie oferuje operacji.
- [x] Backend blokuje nowe cięcie i preflight importowanego stagingu niezależnie od modeli.
- [x] Import wymaga kompletnej geometrii (zachowanie TASK-0581).
- [x] Usuwanie nieużywanego stagingu sprawdza właściwy magazyn gry, zachowując ochronę wyników.
- [x] Checkpoint: ograniczone ponowienie blokad Windows i diagnostyka OS; historyczna przyczyna niepotwierdzona.
- [x] Audyt duplikatów i braków; dostęp do szkiców pojedynczych niepociętych plansz bez zmiany zatwierdzonych wyników.
- [x] Testy regresyjne, dokumentacja, osobny commit.

## Technical notes

Źródłem prawdy pozostają joby importu i materializowane wyniki, nie stan retencji
(ingested oznacza skopiowanie oryginałów). Istniejące importy są niezmienne;
retry wykonuje się przez job. Audyt nie wykazał odroczonych całych źródeł
w manifestach wykonanych importów. Potwierdzona przez użytkownika korekta
pojedynczych plansz korzysta z istniejącej kolejki i szkicu initialQuad;
nowy staging nie jest potrzebny. Nie zmienia to zatwierdzonych geometrii.
Nie usuwać duplikatów ani danych domenowych bez preview i osobnej zgody.
Nie uruchamiać OCR ani cięcia w ramach recovery. Obecne obce zmiany pozostają poza commitem.

## Expected files

- apps/admin/src/features/imports/image-folder-import-state.ts oraz panel i testy
- services/api/src/game_predictor_api/api/image_imports.py
- services/api/src/game_predictor_api/storage/browser_staging_retention_repository.py
- services/worker/src/game_predictor_worker/images/page_geometry_incremental.py
- odpowiednie testy API/workera oraz dokumentacja
- skrypt audytu stagingów bez modyfikacji danych

## Verification

Skoncentrowane pytest i testy Node, Ruff, mypy, admin typecheck. Każdy proces
skończony z timeoutem do 120 s. Audyt SQL read-only z statement_timeout 15 s.
Weryfikacja recovery z nowego procesu, porównanie checksum, pozycji i numeru
sekwencji oraz obecności plików; bez automatycznej akceptacji szkiców.

## Outcome

Zrealizowano kryteria powyżej. Szczegóły i ograniczenia:
[raport audytu](../../quality/STAGING_LIFECYCLE_AUDIT_0582.md).

- 102 testy pytest API/workera oraz 1 test integracyjny PostgreSQL: PASS.
- 56 testów Node panelu, akcji i statusów: PASS.
- Ruff, mypy zmienionych modułów/skryptu, admin typecheck: PASS.
- ESLint: 0 błędów, istniejące ostrzeżenie next/no-img-element.
- Prettier, eksport OpenAPI --check i check:generated: PASS.
- Read-only audyt rzeczywistej gry: 11 916 szkiców bez brakujących plików
  ani błędnych powiązań; próbki correction-context ze wszystkich 13 importów: HTTP 200.
- Worker przeładowany po potwierdzeniu braku aktywnych jobów; nowy proces działa.
  Testy checkpointu sprawdzają wznowienie i zachowanie starego indeksu po błędzie.
  Nie wykonywano restartu systemu ani nowego rzeczywistego cięcia.
- Nie usuwano 10 191 dodatkowych plansz ani stagingu ac700907, nie tworzono
  nowej gry i nie przenoszono nauki między grami. Usunięcie danych wymaga
  osobnego preview i zgody zgodnie z AGENTS.md.
- Nie uruchamiano pełnego zestawu testów repozytorium ani builda produkcyjnego.
  Zmiany użytkownika pozostają poza commitem.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0582 | gpt-6-astra | high | Spójność statusów, transakcji i rzeczywistych danych wymaga analizy całego przepływu. | Własny review ochrony danych i testów; bez delegowania. |
