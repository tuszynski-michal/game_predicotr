---
title: TASK-0307 — Kontrakty attested `seq_*` i wirtualnej geometrii 0.10
status: done
last_updated: 2026-08-29
---

# TASK-0307 — Kontrakty attested `seq_*` i wirtualnej geometrii 0.10

## Goal

Utworzyć czyste, wspólne kontrakty domenowe dla zakresu nazwy `seq_*`,
aktywnych pozycji plansz oraz wirtualnych komórek wyprowadzanych z geometrii
w przestrzeni źródłowego obrazu po pojedynczym zastosowaniu EXIF.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`

## Scope

- jeden parser `seq_<start>-<end>.jpg|jpeg` dla API i workera;
- zakres 1–9 ciągłych numerów oraz aktywne sloty będące row-major prefiksem
  strony 3 × 3;
- kanoniczna przestrzeń współrzędnych `exif-normalized-rgb-pixels-v1`;
- czyste typy źródła, wypukłego quada, geometrii aktywnej planszy i
  renderowania wirtualnej komórki;
- deterministyczne identity logicznej komórki oraz render spec identity;
- projekcyjne wyprowadzenie `rows × columns` quadów komórek bez wymuszania
  prostokąta lub rombu w obrazie;
- regresje parsera, częściowej ostatniej strony, perspektywy i tożsamości po
  zmianie rewizji geometrii.

## Out of scope

- migracja, ORM, API, UI, feature flag i konfiguracja runtime;
- automatyczna geometria OpenCV, keypoint fallback oraz ręczny edytor;
- odczyt albo zapis cropów, inferencja i trening symboli;
- backfill, przeliczenie danych użytkownika i usuwanie starych artefaktów.

## Invariants

- nazwa `seq_*` jest źródłem liczby oraz kolejności maksymalnie dziewięciu
  plansz; częściowa strona ma wyłącznie sloty `0..N-1`;
- współrzędne geometrii dotyczą RGB po dokładnie jednym EXIF transpose;
- quad jest wypukły, uporządkowany i wewnątrz obrazu, lecz nie musi mieć boków
  równoległych ani prostopadłych;
- logical ID komórki nie zmienia się przy nowej geometrii, natomiast render ID
  zmienia się przy zmianie geometrii lub konfiguracji renderowania;
- nowy kontrakt nie tworzy ani nie wymaga trwałego cropa.

## Outcome

Dodano wspólny parser oraz domenowy model `AttestedSequenceRange`; API i
worker korzystają teraz z jednej walidacji nazw `seq_*`. Zakres mapuje do
row-major prefiksu aktywnych slotów, a błędny zakres blokuje zarówno preflight,
jak i managed ingestion.

Moduł `image_geometry_v2` definiuje bez zależności od ORM, HTTP, OpenCV i
systemu plików: EXIF-normalized source, perspektywiczny quad, topologię,
geometrię aktywnej planszy, konfigurację bezpośredniego renderowania oraz
odrębne SHA-256 logical/render identity wirtualnej komórki. Nie zapisuje
żadnego cropa i nie aktywuje nowego pipeline'u.

Odbiór: 60 celowanych testów API/workera przeszło; Ruff, mypy oraz Prettier
dla zmienionych plików są poprawne. TASK 0308 może teraz dodać addytywny
schemat, bez ponownego definiowania znaczenia slotu, quada lub tożsamości.
