---
title: TASK-0312 — integracja wirtualnej geometrii z pipeline'em
status: done
version: 0.10.5
last_updated: 2026-08-29
---

# Cel

Podłączyć wersjonowany `StructuredOpenCvGeometryEngine` oraz
`VirtualCellRenderer` do produkcyjnego wykonania importu w kontrolowanych,
per-game trybach `legacy`, `shadow`, `review` i `default`, bez zmiany
historycznych fingerprintów i bez osłabienia zasady human-wins.

# Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md` — D-254–D-258
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/tasks/completed/0308-v0-10-virtual-geometry-provenance.md`
- `ai_docs/tasks/completed/0309-v0-10-virtual-cell-source-extraction.md`
- `ai_docs/tasks/completed/0311-v0-10-independent-board-line-refinement.md`

# Zakres

- wybór ścieżki geometrii i assetów na podstawie trwałego rolloutu gry;
- zachowanie niezmienionej ścieżki oraz fingerprintu historycznego legacy;
- pojedynczy decode kanonicznego źródła na wykonanie;
- renderowanie maksymalnie 135 komórek w pamięci i jeden batch ONNX;
- brak trwałych board/cell PNG w ścieżce wirtualnej;
- trwały checkpoint geometrii źródła, prediction revision oraz pełna
  proweniencja `virtual_source`;
- dual-write w trybach shadow/review bez zmiany decyzji legacy;
- idempotentny restart/retry oraz kontrola bieżącego canonical ownership;
- testy restartu, checkpointu, pojedynczego wywołania ONNX, braku PNG,
  dual-write i human-wins.

# Poza zakresem

- zmiana algorytmów Structured OpenCV, progów albo modelu symboli;
- automatyczna promocja gry do nowego trybu;
- nowe endpointy lub UI rolloutu;
- backfill historycznych cropów i geometrii;
- TASK-0313 i późniejsze zadania 0.10.

# Invarianty

- `seq_*` pozostaje jedynym źródłem numeracji i aktywnego prefiksu slotów;
- slot bez finalnej geometrii nie trafia do renderera ani symbol inference;
- confidence symboli nie może wpływać na ważność geometrii;
- decyzja człowieka oraz bieżący canonical owner wygrywają z automatem;
- retry identycznego wykonania nie tworzy nowych rewizji ani duplikatów;
- virtual nie zapisuje board/cell PNG i ma kompletną proweniencję od źródła do
  checksummy renderowanych pikseli;
- historyczne joby i fingerprinty legacy pozostają odtwarzalne.

# Outcome

- Joby importu przypinają checksum-bound snapshot rolloutu gry. Dla legacy
  zachowany jest dokładnie stary fingerprint; tryby Structured OpenCV wiążą
  fingerprint z wersjami silnika, renderera i preprocessingu.
- Produkcyjny workflow obsługuje `structured_shadow`, `structured_review` i
  `structured_default`. Wariant default dekoduje źródło raz, renderuje najwyżej
  135 komórek w pamięci, wykonuje jeden batch ONNX i nie zapisuje board/cell
  PNG. Shadow zachowuje primary legacy i dual-write'uje wirtualną geometrię
  oraz predykcję; review kończy się trwałym deferralem bez inferencji.
- Store zapisuje source coordinate metadata, append-only source geometry,
  `virtual_source` dla plansz i komórek oraz prediction revision z pełnym
  render provenance. Rehydratacja wykonuje te same projekcje bez ponownej
  inferencji, a canonical owner jest sprawdzany przed utworzeniem automatycznej
  planszy.
- Testy obejmują niezmieniony fingerprint legacy, drift snapshotu, restart z
  odtworzeniem pikseli, checkpoint geometrii, dokładnie jedno wywołanie ONNX,
  brak PNG, dual-write oraz kompletną proweniencję prediction revision.
- Bounded serwowanie wirtualnych assetów w Reviewerze pozostaje świadomie poza
  zakresem i rozpoczyna TASK-0313.
- Weryfikacja: 141 właściwych testów API/workera, Ruff, OpenAPI drift check oraz
  typecheck i build wygenerowanego klienta przechodzą. Scoped mypy nie zgłasza
  błędów w zmienionych modułach; pełne przejście zależności nadal raportuje dwa
  znane błędy bazowe w `application/image_imports.py:430` i
  `storage/image_job_repository.py:122`, istniejące przed TASK-0312.
