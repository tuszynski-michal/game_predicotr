# Audyt E2E - import nowej gry 777 przez V3 (runda 2)

Werdykt: PASS
Audytor: Codex (GPT-6), reasoning nieudostępniony w metadanych sesji

## Streszczenie

Przegląd statyczny commita `55af1b63aa7012588fb1d2ecf40191ce59248b5d` (`v1.7.315`) potwierdza obsługę opisanej ścieżki `777a2`: preflight modelem 777 v2, automatyczne cropy pełnych siatek, cold-start symboli, weryfikację, trening i aktywację.

Podane kody `WISNIA`, `WINOGRON`, `CYTRYNA`, `POMARANCZ`, `SLIWKA`, `ARBUZ`, `SIEDEM`, `GWIAZDA` nie pasują do angielskich kodów globalnego bootstrapu. Przy braku historii wskazanej w briefie pierwszy import otrzyma snapshot `unclassified`, tworząc oczekujące komórki `?` bez inferencji modelu symboli.

P2-1 zamknięte. Nie znaleziono nowych P0/P1/P2. PASS nie potwierdza wdrożenia ani odbioru rzeczywistego folderu.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

Brak nowych znalezisk.

## Zamknięte

**P2-1 — Etykieta startu nazywała każdy import neuronowy importem Mumii i przesłaniała cold-start.**

- `apps/admin/src/features/imports/image-folder-import-panel.tsx:2118`: gałąź neural sprawdza teraz `unclassifiedColdStartAllowed`. Pokazuje „Rozpocznij pierwszy import V3 bez modelu” albo „Rozpocznij import V3”.
- `apps/admin/test-interactions/neural-import-readiness.test.mjs:213`: test interakcyjny sprawdza etykietę cold-startu, odblokowanie przycisku i wysłanie przypiętego manifestu dopiero po kliknięciu.
- `apps/admin/test/image-folder-import-panel-contract.test.mjs:126`: test kontraktowy wymaga obu etykiet V3 i wyklucza tekst „import Mumii”.
- `apps/admin/test-interactions/neural-import-readiness.test.mjs:414`: osobny test profilu 777 v2 sprawdza wybór V3 i ukrycie V1.1.

Testy przejrzano statycznie. Test kliknięcia nadal używa fixture Mumii; test 777 v2 nie otwiera raportu ani nie klika startu.

## Ścieżka operatora krok po kroku

1. **Wybór `777a2` i V3 — działa w kodzie.**
   Profil `grid_profile_777_v2` należy do profili importu neuronowego. Historyczne `requires_clarification` pozostaje poza tym zbiorem.
   Dowody: `services/api/src/game_predictor_api/domain/grid_engine_profiles.py:279`, `apps/admin/test-interactions/neural-import-readiness.test.mjs:414`.

2. **Folder i raport — działa w kodzie.**
   Brak zgodnego modelu symboli nie blokuje raportu. Backend zwraca osobno blocker modelu, dopuszczenie cold-startu i fingerprint jego snapshotu.
   Dowód: `services/api/src/game_predictor_api/application/jobs.py:1748`.

3. **„Przygotuj geometrię stron” — działa z właściwym modelem.**
   Resolver wybiera model bieżącego profilu gry. Rejestr 777 v2 wskazuje run `43933ac8d7d443c8b9079630a83de2e6` i eksport `2cd19738367121e6-round3`. Worker ładuje model ze snapshotu, bez stałego wyboru Mumii.
   Dowody: `services/api/src/game_predictor_api/storage/grid_profile_snapshot_resolver.py:45`, `services/api/src/game_predictor_api/domain/grid_engine_profiles.py:132`, `services/worker/src/game_predictor_worker/images/neural_page_geometry_preflight.py:230`.

4. **Przypisanie plansz do numerów — działa.**
   Automatyczne przypisanie wymaga zgodnej liczby detekcji i jednoznacznego układu przestrzennego. Obsługuje stronę 3×3 i limit `expectedLayoutCount`. Brakujący slot pozostaje jawny; późniejsze numery nie są przesuwane.
   Dowody: `services/api/src/game_predictor_api/domain/neural_grid_proposal.py:442`, `services/worker/src/game_predictor_worker/images/neural_pending_geometry.py:113`.
   Test zachowania luki i numerów: `services/worker/tests/test_neural_folder_correction_pipeline.py:121`.

5. **Start bez modelu symboli — działa dla podanego katalogu i stanu gry.**
   Resolver porównuje dokładne kody, bez tłumaczenia ich na klasy bootstrapu. Po niezgodności dopuszcza cold-start tylko bez zatwierdzonych komórek, kohort, iteracji i aktywacji. Admin uwzględnia ten stan przy odblokowaniu startu; API sprawdza go ponownie.
   Dowody: `services/api/src/game_predictor_api/storage/symbol_model_snapshot_resolver.py:79`, `services/api/src/game_predictor_api/storage/symbol_model_snapshot_resolver.py:197`, `apps/admin/src/features/imports/image-folder-import-panel.tsx:488`, `services/api/src/game_predictor_api/api/image_imports.py:1112`.

6. **Import i cropy 15 komórek — działa.**
   Job przypina `neural-auto-crop-v1`. Automatycznie cięte są tylko przypisane, strukturalnie poprawne detekcje z pełną widocznością komórek. Renderer używa dokładnych 24 węzłów i pochodzenia `neural_grid_v1`. Szkic reguł 3×5 wystarcza do przypięcia topologii.
   Dowody: `services/api/src/game_predictor_api/application/jobs.py:851`, `services/worker/src/game_predictor_worker/images/neural_pending_geometry.py:102`, `services/worker/src/game_predictor_worker/images/production_workflow.py:1944`, `services/api/src/game_predictor_api/storage/job_repository.py:78`.

7. **Materializacja cold-startu — działa bez ONNX symboli.**
   Worker tworzy `?` z confidence `0`. Projekcja zapisuje rendery i pozycje, pomija rewizje predykcji modelu oraz synchronizuje komórki do weryfikacji. Nie próbuje ładować zastępczej ścieżki `.no-onnx`.
   Dowody: `services/worker/src/game_predictor_worker/images/production_workflow.py:2591`, `services/worker/src/game_predictor_worker/images/production_workflow.py:2635`, `services/worker/src/game_predictor_worker/images/pipeline_store.py:676`, `services/worker/src/game_predictor_worker/images/pipeline_store.py:747`.
   Test braku wywołania ONNX: `services/worker/tests/test_production_image_workflow.py:2537`.

8. **Reviewer i korekta — działa w obsługiwanym zakresie.**
   Kolejka korzysta z `gameId` i opcjonalnego `importJobId`. Predykcja po korekcie obsługuje snapshot `unclassified`. Proxy dopuszcza korektę, odrzucenie oraz preview i wykonanie cofnięcia. Nadal obowiązują ograniczenia D-542/D-543.
   Dowody: `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx:128`, `services/worker/src/game_predictor_worker/images/manual_board_cell_symbol_prediction.py:80`, `apps/reviewer/src/security/reviewer-proxy-policy.ts:129`.

9. **Weryfikacja symboli i zapis zbiorczy — działa.**
   Dopuszczenie pełnych cropów zależy od polityki neural i zgodności źródła, gry, lattice oraz bindingu. Nie zależy od profilu Mumii. Dla `?` operator wybiera rzeczywisty symbol i używa „Zapisz i zatwierdź”. Samo zatwierdzenie filtra `?` jest blokowane.
   Dowody: `services/api/src/game_predictor_api/storage/image_geometry_completeness_state_repository.py:499`, `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx:2344`, `services/api/src/game_predictor_api/application/image_symbol_review_bulk_operations.py:386`.

10. **„Ulepsz rozpoznawanie” i aktywacja — działa po spełnieniu bramek danych i jakości.**
    Trening korzysta z zatwierdzonych, aktualnych renderów i rzeczywistych kodów katalogu. Nie wymaga obrazów referencyjnych ani profilu Mumii. Aktywacja wymaga kompletnego kandydata `candidate_ready`; dodatkowa kontrola prawdy Mumii nie dotyczy `777a2`.
    Dowody: `services/api/src/game_predictor_api/storage/symbol_cell_training_source_repository.py:218`, `services/worker/src/game_predictor_worker/symbols/training_job.py:647`, `services/api/src/game_predictor_api/storage/symbol_model_registry_repository.py:184`.

11. **Ochrona przed użyciem niewłaściwego profilu — działa.**
    Ponowne użycie preflightu pomija snapshot innego profilu. Start importu odrzuca taki snapshot jako `NEURAL_GRID_PREFLIGHT_INVALID`.
    Dowody: `services/api/src/game_predictor_api/application/jobs.py:2161`, `services/api/src/game_predictor_api/application/jobs.py:2221`.

## Zakres przeglądu i ograniczenia

Ponownie przejrzano poprawkę P2-1 i testy oraz ścieżki API, workera, cropów, projekcji komórek, Reviewera, weryfikacji, treningu i aktywacji.

Pozostałe odwołania do Mumii dotyczą historycznej nazwy polityki preflightu, odrębnego pilota laboratoryjnego modelu symboli oraz kontroli chronionych źródeł Mumii. Nie znaleziono ograniczenia opisanego przepływu przez `MUMIE_GAME_ID`, profil Mumii ani `superGameKind`.

Nie uruchamiano testów, usług, inferencji, treningu ani operacji bazodanowych. Nie potwierdzono instalacji modeli, restartu workera ani rzeczywistego stanu bazy. Wniosek o cold-starcie przyjmuje podany katalog i brak historii z briefu.

Dalsza weryfikacja powinna połączyć w jednym scenariuszu profil 777 v2, pełny ośmiosymbolowy katalog, kliknięcie startu i materializację neuronowych komórek `?`.

**Przegląd statyczny, bez zmian w plikach.** Worktree pozostał czysty. Raport przekazano w czacie; nie zapisano pliku.