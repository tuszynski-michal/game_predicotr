---
title: TASK-0308 — Trwała proweniencja wirtualnej geometrii 0.10
status: done
last_updated: 2026-08-29
---

# TASK-0308 — Trwała proweniencja wirtualnej geometrii 0.10

## Goal

Dodać addytywny schemat `0082`, który pozwoli przyszłym jobom przechowywać
geometrię i tożsamość wirtualnego renderu bez trwałego pliku cropa, zachowując
pełną zgodność istniejących rekordów `legacy_file`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/tasks/completed/0307-v0-10-attested-virtual-geometry-contracts.md`

## Scope

- migracja `0082_virtual_geometry_foundation` z upgrade i downgrade;
- kanoniczne metadane układu współrzędnych na `source_images`;
- append-only `image_source_geometry_revisions`;
- per-game `image_geometry_rollout_states`, domyślnie w trybie legacy;
- dual-schema `legacy_file | virtual_source` dla plansz, obserwacji, rewizji
  geometrii, bieżącej projekcji review, eventów i próbek kohorty;
- warunkowe constraints: virtual nie wymaga ścieżki, ale wymaga kompletnej
  proweniencji render spec i rendered-pixel SHA-256;
- bounded, idempotentny backfill stanów rolloutowych bez skanowania obrazów;
- repozytoria source geometry i rolloutu przygotowane dla późniejszego
  pipeline'u, lecz jeszcze przez niego nieużywane;
- testy migracji, constraintów, backfillu i rollbacku.

## Out of scope

- uruchomienie migracji na bazie użytkownika;
- zmiana pipeline'u, workera, klasyfikatora symboli, API albo UI;
- renderowanie pikseli, OpenCV, EXIF decode i zapis nowych cropów;
- backfill render speców lub checksumm pikseli dla historycznych cropów;
- przełączenie którejkolwiek gry z trybu legacy.

## Invariants

- istniejące rekordy pozostają `legacy_file` i zachowują wymagane ścieżki;
- `virtual_source` nie może wskazywać pliku cropa i musi wiązać źródło,
  geometrię, logiczną komórkę, render spec oraz checksumę pikseli;
- schema nie kopiuje binariów do PostgreSQL;
- geometria źródła jest append-only i używa kanonicznej przestrzeni
  `exif-normalized-rgb-pixels-v1`;
- bounded backfill nie oblicza geometrii ani nie zgaduje EXIF;
- zmiana schematu nie aktywuje żadnej flagi ani write path 0.10.

## Outcome

Migracja `0082_virtual_geometry_foundation` dodaje kompletne, opcjonalne
metadane przestrzeni współrzędnych źródła, append-only rewizje geometrii strony
oraz per-game rollout domyślnie wyłączony. Plansze, obserwacje, ręczne rewizje,
projekcja review, eventy i próbki kohorty obsługują warunkowy kontrakt
`legacy_file | virtual_source`. Existing rows zachowują ścieżki i działanie;
virtual wymaga source geometry, logicznej tożsamości, render spec i checksummy
wynikowych pikseli.

Repozytorium geometrii blokuje źródło, sprawdza jego grę, topologię i pełne
coordinate metadata, nadaje monotoniczną rewizję oraz zapewnia idempotencję po
geometry checksum. Repozytorium rolloutów materializuje brakujące stany legacy
w deterministycznych partiach po UUID gry: domyślnie 200, maksymalnie 500.
Nie skanuje obrazów ani dużych tabel cropów. Dotychczasowe konsumery plikowe
odrzucają przyszły virtual record stabilnym błędem do czasu TASK-0309+.

### Lock analysis

- nowe tabele i indeksy nie skanują tabel historycznych;
- nowe nullable columns oraz kolumny z constant server default wymagają
  krótkiego `ACCESS EXCLUSIVE`, lecz na PostgreSQL 11+ nie przepisują tabel;
- `DROP NOT NULL` i zamiana check constraintów również wymagają krótkiego
  locka katalogowego, bez przebudowy danych;
- nowe constrainty na dużych tabelach są `NOT VALID`: obowiązują nowe i
  zmieniane rekordy, ale nie wykonują pełnego skanu podczas upgrade'u;
- ich bounded walidacja historyczna pozostaje częścią późniejszego rollout
  taska; backfill rolloutów pracuje w małych transakcjach.

### Rollback

Downgrade do `0081` jest przetestowany i bezpieczny, dopóki nie istnieje żadna
source geometry, virtual asset ani gra przełączona z legacy. Guard migracji
blokuje destrukcyjny downgrade po pojawieniu się takiej proweniencji. Wtedy
rollback operacyjny oznacza powrót rollout state gry do legacy oraz zachowanie
nowych tabel, nie utratę audytu.

Weryfikacja: 63 testy migracji/modeli, izolowany PostgreSQL
upgrade→bounded backfill→downgrade oraz 103 testy regresyjne review/search/
reinference przeszły. Ruff i scoped strict mypy nowego repozytorium są czyste.
Pełny graf mypy nadal zgłasza dwa wcześniejsze, niezwiązane błędy w
`image_imports.py` oraz `image_job_repository.py`. Migracji nie uruchomiono na
bazie użytkownika.
