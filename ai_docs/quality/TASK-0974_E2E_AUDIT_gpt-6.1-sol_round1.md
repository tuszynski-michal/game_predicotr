# Audyt E2E — import nowej gry 777 przez V3 (runda 1)

Werdykt: PASS
Audytor: Codex (GPT-6), reasoning nieudostępniony w metadanych sesji

## Streszczenie

W przejrzanym kodzie ścieżka V3 obsługuje `777a2`: wybiera model profilu `grid_profile_777_v2`, przygotowuje geometrię, importuje pełne siatki, udostępnia komórki do weryfikacji oraz pozwala trenować i aktywować model symboli. Nie znalazłem blokady P0/P1 ograniczającej ten przepływ do Mumii.

Brak aktywnego modelu symboli nie blokuje pierwszego importu, jeżeli resolver dopuści cold-start. Jest jednak istotne rozróżnienie: katalog zgodny z globalnym bootstrapem uruchamia ten bootstrap. Sam brak treningu i aktywacji nie gwarantuje komórek `?`. Brief nie podaje kodów ośmiu symboli, więc dokładny tryb pierwszego importu `777a2` pozostaje niezweryfikowany.

Znalazłem jedną uwagę P2: przycisk startu dla `777a2` nadal nazywa operację „importem Mumii”. PASS dotyczy przeglądu statycznego; nie potwierdza odbioru działających usług ani jakości siatek na folderze operatora.

## Znaleziska

### P0

Brak.

### P1

Brak potwierdzonych znalezisk.

### P2

**P2-1 — Przycisk startu zachowuje nazwę Mumii i przesłania etykietę cold-startu.**

- **Miejsce:** `apps/admin/src/features/imports/image-folder-import-panel.tsx:2118`.
- **Skutek dla `777a2`:** każdy rozpoznany preflight neuronowy wyświetla „Rozpocznij import Mumii”. Ta gałąź poprzedza również „Rozpocznij pierwszy import bez modelu”. Operator widzi błędną nazwę gry, choć żądanie używa właściwego `gameId` i snapshotu.
- **Minimalna poprawka:** zastosować neutralną etykietę „Rozpocznij import V3” albo nazwę bieżącej gry. Dla dopuszczonego cold-startu pokazać odpowiednią etykietę przed ogólną gałęzią neural.
- **Proponowana weryfikacja:** test etykiety dla profilu 777 v2 z `unclassifiedColdStartAllowed=true` oraz regresja Mumii.

## Ścieżka operatora krok po kroku (działa / nie działa / niezweryfikowane, z dowodem `ścieżka:linia`)

1. **Wybór szkicu `777a2` i silnika — działa.**
   Admin rozpoznaje oba profile silnika siatek. Dla 777 v2 pokazuje V3 i pomija argument klasycznego wariantu. Backend normalizuje brak wariantu lub V1.1 do ścieżki neuronowej.
   Dowody: `apps/admin/src/features/imports/image-folder-import-panel.tsx:290`, `apps/admin/src/features/imports/image-folder-import-panel.tsx:309`, `services/api/src/game_predictor_api/api/image_imports.py:465`.

2. **Folder `seq_<start>-<end>.jpg` i raport — działa w kodzie.**
   Zakresy i kanoniczne sekwencje są rozpatrywane w obrębie gry. Resolver odczytuje jej `expected_layout_count`; nie narzuca identyfikatora Mumii ani jej katalogu symboli. Raport osobno pokazuje gotowość modelu symboli i możliwość cold-startu.
   Dowody: `services/api/src/game_predictor_api/domain/image_sequence_canonical.py:122`, `services/api/src/game_predictor_api/storage/image_sequence_canonical_repository.py:54`, `services/api/src/game_predictor_api/application/jobs.py:1750`.

3. **„Przygotuj geometrię stron” — działa z modelem 777 v2.**
   Resolver wybiera bieżący model profilu gry. Rejestr 777 v2 wskazuje run `43933ac8d7d443c8b9079630a83de2e6` i eksport `2cd19738367121e6-round3`. Worker ładuje wersję ze snapshotu; magazyn sprawdza manifest, rozmiary i SHA-256 bez fallbacku do Mumii.
   Dowody: `services/api/src/game_predictor_api/storage/grid_profile_snapshot_resolver.py:45`, `services/api/src/game_predictor_api/domain/grid_engine_profiles.py:132`, `services/worker/src/game_predictor_worker/images/neural_page_geometry_preflight.py:230`, `services/api/src/game_predictor_api/storage/grid_engine_model_store.py:50`.

4. **Przypisanie detekcji do numerów — działa.**
   Automatyczne przypisanie wymaga zgodnej liczby detekcji, poprawnej struktury i jednoznacznego układu przestrzennego. Obsługiwany układ strony do 3×3 plansz oraz plansza 3×5 odpowiadają briefowi. Zakres przekraczający 500000 wymaga korekty; brakujące pozycje pozostają jawne, bez przesuwania numerów.
   Dowody: `services/api/src/game_predictor_api/domain/neural_grid_proposal.py:442`, `services/api/src/game_predictor_api/domain/neural_grid_proposal.py:522`, `services/api/src/game_predictor_api/domain/neural_grid_proposal.py:375`, `services/worker/src/game_predictor_worker/images/neural_pending_geometry.py:113`.

5. **Start bez aktywnego modelu symboli — mechanizm działa; dokładny tryb `777a2` niezweryfikowany.**
   Cold-start dopuszcza grę bez zatwierdzonych komórek, kohort, iteracji i aktywacji. Admin uwzględnia tę możliwość przy odblokowaniu przycisku, a API ponownie sprawdza ją przed utworzeniem joba. Worker tworzy wtedy `?` z confidence 0 bez inferencji ONNX.
   Dowody: `services/api/src/game_predictor_api/storage/symbol_model_snapshot_resolver.py:178`, `apps/admin/src/features/imports/image-folder-import-panel.tsx:488`, `services/api/src/game_predictor_api/api/image_imports.py:1112`, `services/api/src/game_predictor_api/api/image_imports.py:1435`, `services/worker/src/game_predictor_worker/images/production_workflow.py:2591`.

   **Warunek:** jeżeli kody symboli są dokładnie zgodne z globalnym bootstrapem, resolver zwraca bootstrap przed rozpatrzeniem cold-startu. To zachowanie jest objęte istniejącym testem.
   Dowody: `services/api/src/game_predictor_api/storage/symbol_model_snapshot_resolver.py:79`, `services/api/tests/test_symbol_model_snapshot_resolver.py:261`.

6. **Import i renderowanie 15 komórek — działa.**
   Job neuronowy przypina `neural-auto-crop-v1`. Pełne, strukturalnie poprawne i przypisane detekcje otrzymują automatyczne cropy. Renderer zachowuje dokładne węzły lattice i pochodzenie `neural_grid_v1`. Szkic reguł 3×5 wystarcza do przypięcia topologii; nie ma wymogu opublikowanych reguł.
   Dowody: `services/api/src/game_predictor_api/domain/neural_crop_policy.py:14`, `services/worker/src/game_predictor_worker/images/neural_pending_geometry.py:102`, `services/worker/src/game_predictor_worker/images/production_workflow.py:1944`, `services/api/src/game_predictor_api/storage/job_repository.py:65`, `services/api/src/game_predictor_api/application/jobs.py:575`.

7. **Lokalny Reviewer, korekty i cofnięcia — działa w obsługiwanym zakresie.**
   Kolejka korekt używa `gameId` oraz opcjonalnego `importJobId`, bez bramki profilu Mumii. Korekta odroczonego slotu obsługuje snapshot `unclassified` bez ładowania ONNX. Proxy dopuszcza preview, zapis, odrzucenie i cofnięcie. Cofnięcia zachowują ograniczenia D-542, m.in. odmowę dla kwalifikowanej geometrii częściowej lub niekompletnej historii.
   Dowody: `apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx:127`, `services/worker/src/game_predictor_worker/images/manual_board_cell_symbol_prediction.py:80`, `apps/reviewer/src/security/reviewer-proxy-policy.ts:129`, `services/api/src/game_predictor_api/storage/geometry_correction_revert_repository.py:1762`.

8. **Weryfikacja symboli i operacje zbiorcze — działa.**
   Dopuszczenie pełnych komórek neuronowych zależy od silnika, polityki i poprawnego bindingu, nie od profilu Mumii. Zbiorcze mutacje są zakresowane przez grę. Dla komórek `?` operator wybiera realny symbol i używa „Zapisz i zatwierdź”; samo zbiorcze zatwierdzenie filtra `?` jest prawidłowo blokowane.
   Dowody: `services/api/src/game_predictor_api/storage/image_geometry_completeness_state_repository.py:499`, `services/api/src/game_predictor_api/storage/image_symbol_review_bulk_operation_repository.py:549`, `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx:2344`, `services/api/src/game_predictor_api/application/image_symbol_review_bulk_operations.py:386`.

9. **„Ulepsz rozpoznawanie” — działa po zebraniu zatwierdzeń.**
   Przycisk wymaga zatwierdzonych komórek i braku aktywnej ciężkiej operacji. Źródła treningowe kwalifikują aktualne, zatwierdzone rendery z realnymi symbolami. Brak obrazów referencyjnych symboli ani pochodzenie neural nie stanowią bramki. Trening nadal wymaga odpowiedniego pokrycia klas w podziałach danych.
   Dowody: `apps/admin/src/features/model-quality/model-quality-workspace.tsx:772`, `services/api/src/game_predictor_api/storage/symbol_cell_training_source_repository.py:218`, `services/worker/src/game_predictor_worker/symbols/training_job.py:305`.

10. **Aktywacja modelu symboli — działa po przejściu bramki jakości.**
    Rejestr wymaga kandydata `candidate_ready` z kompletnymi artefaktami. Dodatkowa kontrola prawdy kontrolnej Mumii jest pomijana dla `777a2`; nie blokuje jej zwykłego modelu produkcyjnego.
    Dowody: `services/api/src/game_predictor_api/storage/symbol_model_registry_repository.py:184`, `services/api/src/game_predictor_api/storage/symbol_model_registry_repository.py:221`.

11. **Ochrona historycznej 777 — działa przy konfiguracji z briefu.**
    `requires_clarification` nie należy do profili neuronowych. Historyczna gra pozostaje na ścieżce klasycznej. Ponowne użycie preflightu i start importu sprawdzają zgodność profilu snapshotu z bieżącym profilem gry.
    Dowody: `services/api/src/game_predictor_api/domain/grid_engine_profiles.py:279`, `services/api/src/game_predictor_api/application/jobs.py:2161`, `services/api/src/game_predictor_api/application/jobs.py:2221`.

## Zakres przeglądu i ograniczenia

Przejrzano ścieżki Admina, API, workera, Reviewera i wspólne kontrakty wskazane w briefie oraz dokumentację D-521–D-523/D-544 i odpowiednie testy.

Pozostałe odniesienia do Mumii mają następujące znaczenie:

- `page-geometry-preflight-v13-neural-mumie-pilot` jest wspólnym, historycznym identyfikatorem polityki. Nie wybiera modelu Mumii.
- `MUMIE_GAME_ID` ogranicza ochronę źródeł kontrolnych oraz dodatkowe kontrole treningu i aktywacji Mumii. Dla `777a2` te kontrole są pomijane. Dowody: `services/worker/src/game_predictor_worker/symbols/protected_sources.py:110`, `services/api/src/game_predictor_api/storage/symbol_model_iteration_repository.py:154`.
- Pilot importu laboratoryjnego modelu symboli Mumii pozostaje odrębnym zakresem. Przepływ `777a2` korzysta ze zwykłego treningu na kohorcie DB.
- Nie znaleziono bramki `superGameKind` ograniczającej opisany import, korekty, weryfikację lub trening.

Audyt dotyczy commita `4344510b804031c0ebcf9f8f458007ff9ee836d4` (`v1.7.314`) na `feat/v3-777-profile`.

Nie uruchamiano usług, testów, inferencji, treningu ani operacji bazodanowych. Nie potwierdzano aktualnego stanu wdrożenia, plików modeli ani katalogu symboli w bazie operatora. Wyniki testów zapisane w Outcome nie były ponownie wykonywane.

**Przegląd statyczny, bez zmian w plikach.** Worktree pozostał czysty. Odbiór rzeczywistego folderu i jakości modelu pozostaje krokiem operatorskim.