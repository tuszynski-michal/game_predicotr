---
title: TASK-0413 Atomic source grid approval and multi-board manual geometry
status: done
last_updated: 2026-09-03
---

# TASK-0413 — Atomowe zatwierdzanie zdjęcia i ręczna geometria wielu plansz

## Problem

Lokalny ekran „Zatwierdzanie cięcia siatki” pobiera do dziewięciu aktywnych
plansz jednego zdjęcia, lecz zatwierdza je kolejno, używając snapshotu
pobranego przed pierwszym zapisem. Pierwszy zapis może zmienić wspólną
projekcję źródła; kolejne żądanie jest wtedy konfliktem rewizji. UI wygląda,
jakby zatwierdzenie nie zadziałało, a po przejściu dalej pokazuje błąd.

Operator potrzebuje też odrębnego trybu, w którym wyznacza po kolei cztery
narożniki każdej aktywnej planszy zdjęcia (pozycje row-major), a potem zapisuje
i zatwierdza cały komplet jedną transakcją.

## Scope

- dodać checksum- i revision-bound endpoint atomowego zatwierdzenia wszystkich
  bieżących plansz jednego zdjęcia;
- przed mutacją sprawdzić komplet aktywnych slotów, ich właścicieli, rewizje,
  źródło i topologię; konflikt nie może zatwierdzić części zdjęcia;
- zmienić akcję „Zatwierdź całe zdjęcie” na pojedyncze żądanie źródłowe;
- dodać za „Zmień siatkę” tryb „Wyznacz plansze osobno” dla `virtual_source`;
- zbierać cztery narożniki plansz po kolei według `positionIndex`, umożliwić
  korektę każdego kompletu i zapisać wszystkie plansze źródła atomowo;
- zachować istniejący pojedynczy edytor i legacy workflow bez zmiany;
- zaktualizować OpenAPI, klient, testy i dokumentację.

## Out of scope

- brak migracji, nowych workerów, batch jobów lub modyfikacji danych istniejących
  importów;
- brak automatycznej zmiany geometrii lub klasyfikacji symboli;
- brak rozszerzania zdalnego, ograniczonego Reviewera.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/CURRENT_STATE.md`

## Definition of Done

- jedno kliknięcie zatwierdza wszystkie nadal bieżące aktywne plansze źródła
  albo nie zatwierdza żadnej;
- UI po sukcesie przechodzi do następnego zdjęcia, a po konflikcie odświeża
  bieżące dane zamiast pozostawiać pozorny sukces;
- tryb wieloplanszowy prowadzi operatora przez cztery narożniki plansz w
  kolejności row-major, nie myli kolejności i wymaga pełnego kompletu;
- ręczny zapis wielu plansz tworzy jedną rewizję geometrii źródła i spójnie
  aktualizuje cropy, komórki, audyt oraz kolejkę;
- testy obejmują konflikt po snapshotcie, brak częściowego zatwierdzenia,
  kolejność 9 plansz i atomowy zapis ręcznych quadów.

## Outcome

- Dodano dwa lokalne endpointy source-scoped oraz wygenerowany klient:
  atomowe zatwierdzenie bieżącego kompletu i atomowy zapis pełnej ręcznej
  geometrii `virtual_source`.
- Backend najpierw blokuje oraz waliduje wszystkie sloty jednego zdjęcia, ich
  właścicieli, rewizje, checksumy i topologię. Konflikt albo niepełny komplet
  nie zapisuje pojedynczej planszy.
- `Zatwierdź całe zdjęcie` używa jednego żądania. Edytor ma tryb `Wyznacz
  plansze osobno`, który prowadzi przez LT → PT → PD → LD dla slotów row-major
  i zapisuje komplet dopiero po wskazaniu wszystkich narożników.
- Uruchomiono testy API, OpenAPI, klienta i Reviewera oraz Ruff, typecheck i
  lint. Lokalny build Reviewera ukończył generowanie artefaktów, lecz drugi
  ręcznie uruchomiony build został poprawnie zablokowany przez aktywną blokadę
  Next.js; nie uruchamiano równoległej kopii.
