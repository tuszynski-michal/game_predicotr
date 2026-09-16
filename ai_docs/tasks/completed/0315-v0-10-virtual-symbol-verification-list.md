---
title: TASK-0315 — Wirtualizowana lista Weryfikacji Symboli
status: done
version: 0.10
---

# TASK-0315 — Wirtualizowana lista Weryfikacji Symboli

## Cel

Utrzymać keysetowe strony po 500 metadanych, ale nie renderować ani nie pobierać
obrazów dla całej strony. Admin ma renderować wyłącznie viewport z małym
overscanem, używać atlasów wyłącznie dla aktualnie widocznych wirtualnych
komórek oraz przechowywać maksymalnie trzy strony metadanych.

## Zakres

- dodać przypięte `@tanstack/react-virtual`;
- dodać listowy filtr confidence oraz związać go z keyset cursorami i snapshotem
  filtra operacji masowej;
- ograniczyć backendowy limit listy do 500;
- wprowadzić selekcję jawną do 10 000 elementów oraz snapshot całego filtra z
  `excludedIds`, bez pobierania tych ID do przeglądarki;
- użyć batchowego atlasu do maksymalnie 100 wirtualnych kart z viewportu;
- prefetchować tylko jedną następną stronę i utrzymać window maksymalnie trzech
  stron;
- zaktualizować OpenAPI, klient, wymagania, kontrakt API, Current State i
  Decision Log.

## Poza zakresem

- brak migracji, zmian trwałej geometrii, pipeline'u, modelu symboli i backendowego
  generowania obrazów;
- brak pobierania 10 000 obrazów lub jawnych ID dla akcji „wszystkie wyniki”;
- brak usuwania historycznych cropów i cache'ów.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DECISION_LOG.md` (D-241)
- `ai_docs/process/CURRENT_STATE.md`

## Invarianty

- lista pozostaje keysetowa i pokazuje wyłącznie bieżącego właściciela logicznej
  planszy;
- jednocześnie w pamięci klienta pozostają najwyżej trzy strony po 500
  metadanych;
- DOM obejmuje tylko viewport i ograniczony overscan, a atlas nie zawiera więcej
  niż 100 wirtualnych komórek;
- filtr i jego snapshot wiążą grę, symbol, stan, confidence oraz rewizję katalogu;
- zmiana filtra po zaznaczeniu wymaga potwierdzenia i czyści zaznaczenie;
- pojedyncza decyzja pozostaje bezpośrednia, a większa operacja jest trwałym jobem;
- zdalny Reviewer nie otrzymuje rozszerzonych endpointów lokalnego Admin API.

## Outcome

- Admin używa stałych stron po 500 metadanych, wirtualizuje karty przez
  `@tanstack/react-virtual` i utrzymuje maksymalnie trzy sąsiednie strony.
  Prefetch obejmuje wyłącznie jedną kolejną stronę metadanych.
- Wirtualne cropy są pobierane batchowym atlasem tylko dla viewportu i małego
  overscanu, maksymalnie 100 komórek; legacy assety zachowują lazy thumbnail.
- Confidence jest związane z listą, cursorem i snapshotem całego filtra.
  Zaznaczenie wszystkich wyników przechowuje scope oraz ograniczone
  `excludedIds`, nie listę wszystkich ID ani obrazów.
- Testy Admina obejmują bounded window dla 500/1000/10000 metadanych, limit
  atlasu, anulowanie spóźnionej odpowiedzi oraz snapshot filtrowanego wyboru.
  Testy API sprawdzają limit 500 i scope confidence kursora.
