---
title: TASK-0309 — Wirtualne komórki renderowane bezpośrednio ze źródła
status: done
last_updated: 2026-08-29
---

# TASK-0309 — Wirtualne komórki renderowane bezpośrednio ze źródła

## Goal

Dodać wspólny, niewykonujący trwałego zapisu loader kanonicznego obrazu oraz
renderer wirtualnych komórek. Piksele mają powstawać po dokładnie jednym EXIF
transpose i jednym source-direct `warpPerspective` na komórkę.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/tasks/completed/0307-v0-10-attested-virtual-geometry-contracts.md`
- `ai_docs/tasks/completed/0308-v0-10-virtual-geometry-provenance.md`

## Scope

- `CanonicalSourceLoader` stosujący EXIF dokładnie raz i zwracający ciągłe,
  tylko do odczytu RGB `uint8` wraz z kanoniczną proweniencją;
- execution-scoped cache gwarantujący jeden decode tego samego źródła;
- `VirtualCellRenderer` konsumujący kontrakt `VirtualCell` z TASK-0307;
- jeden bezpośredni warp źródło→wynik na każdą komórkę;
- checksum specyfikacji renderu i checksum wynikowych pikseli;
- brak trwałych PNG oraz brak pośredniego rastra planszy w ścieżce produkcyjnej;
- diagnostyczne, wyłącznie pamięciowe porównanie wariantów A/B/C;
- testy EXIF 1–8, single-decode, v19 parity i A/B/C.

## Out of scope

- uruchomienie nowego renderera w pipeline;
- zapis rekordów `virtual_source` do bazy;
- zmiana algorytmu geometrii, croppera v19 albo modelu symboli;
- endpointy, UI, cache podglądów, OpenCV geometry engine i rollout gry;
- migracje oraz przetwarzanie danych użytkownika.

## Invariants

- źródłem jest niezmienny managed original związany oczekiwaną checksumą;
- współrzędne odnoszą się do RGB po dokładnie jednym EXIF transpose;
- renderer odrzuca drift źródła, wymiarów, checksummy pikseli i konfiguracji;
- produkcyjny wariant B nie materializuje planszy i nie zapisuje pliku;
- historyczny v19 zachowuje fingerprint oraz dotychczasowe piksele;
- błędna specyfikacja jest odrzucana przed pierwszym warpem.

## Outcome

Dodano `CanonicalSourceLoader` z weryfikacją SHA-256 managed original,
obsługą EXIF 1–8, pojedynczym decode i ograniczonym do jednego źródła cache'em.
Zwracana macierz RGB jest ciągła, niemodyfikowalna i związana z istniejącym
kontraktem `NormalizedSourceImage`; loader nie tworzy pliku roboczego.

Nowy `VirtualCellRenderer` waliduje całą partię przed rasteryzacją i renderuje
każde pole dokładnie jednym source-direct `warpPerspective`. Każdy wynik zawiera
logiczny klucz, kanoniczny render spec, checksumę specu, checksumę RGB i wersję
extractora. Produkcyjny wariant B nie tworzy planszy pośredniej ani trwałego
cropu. Diagnostyka A/B/C pozostaje wyłącznie w pamięci.

Historyczny cropper v19 nie został zmieniony. Test porównawczy potwierdził
identyczne bajty wszystkich 15 wyników B/v19 oraz dokładnie 15 warpów. Testy
pokrywają również EXIF 1–8, single-decode/cache, brak plików wynikowych, A/B/C i
fail-closed przed pierwszym warpem przy driftcie źródła. Nowa ścieżka nie została
podłączona do pipeline'u, bazy, API, UI ani modelu symboli.
