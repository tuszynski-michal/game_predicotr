---
title: TASK-0126 Representative symbol image picker and catalog refinement
status: done
last_updated: 2026-07-31
---

# TASK-0126 — Representative symbol image picker and catalog refinement

## Status

`done`

## Goal

Pozwolić operatorowi wybrać czytelną grafikę reprezentatywną symbolu spośród
rzeczywistych cropów importu i poprawić nazwę bez zmiany stabilnej tożsamości.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/VERSION_0_2_EXECUTION_PLAN.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- kliknięcie grafiki symbolu otwiera modal z pierwszymi 10 kandydatami,
- kandydaci są rzeczywistymi cropami tej samej grupy bootstrapu,
- `Załaduj kolejne grafiki` używa deterministycznego kursora i nie powtarza
  wcześniej pokazanych obserwacji,
- wybrany crop jest odczytywany przez bezpieczny item-scoped endpoint assetu,
- zapis zmienia wyłącznie nazwę i `image_path`; `mobile_code`, stabilny kod i
  provenance bootstrapu pozostają niezmienne,
- grafika ma jawny hover/focus oraz disabled state, gdy brak kandydatów.

## Acceptance criteria

- [x] API zwraca maksymalnie 10 stabilnie uporządkowanych kandydatów,
- [x] kursor jest scope-bound i kolejne strony nie dublują elementów,
- [x] asset endpoint blokuje traversal i weryfikuje checksumę,
- [x] modal pozwala wybrać grafikę i doładować następną stronę,
- [x] wybór grafiki nie zmienia `mobileCode` ani kodu symbolu,
- [x] loading, empty i error są jawne,
- [x] OpenAPI, testy backendu i Admina przechodzą.

## Outcome

Dodano deterministyczną, scope-bound paginację cropów po 10 elementów,
checksum-bound endpointy obrazu bieżącego i kandydatów oraz atomową operację
wyboru obrazu wraz ze zmianą nazwy. Panel pokazuje rzeczywisty crop na kafelku,
jawny disabled/hover/focus i modal z loading, empty, error oraz doładowaniem
bez duplikatów. Przeglądarka nie przesyła ścieżki pliku do zapisu, a
`code`, `mobileCode` i provenance pozostają niezmienione.

Zweryfikowano testy backendu, generowany klient, typecheck/lint/testy Admina,
zgodność OpenAPI i produkcyjny build panelu.
