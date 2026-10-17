# TASK-1003 — odpowiedź wykonawcy na Claude R1

R1 zachowuje werdykt **REVISE**. Niniejszy dokument opisuje jedną zatwierdzoną
rundę poprawek, nie jest niezależnym audytem ani końcowym PASS taska.
Wykonawca: gpt-6.1-sol/medium; pomocniczy wykonawca Admina dziedziczył medium.
Kontrakt poprawki zapisano przed kodem w tasku i D-551. Lead przeprowadza
wymagany Claude medium R2/do1200s dla zmienionego zachowania P1.

## Rozliczenie uwag

| Uwaga | Działanie wykonawcy | Dowód i ograniczenie |
| --- | --- | --- |
| P1-1 | Dodano `refresh_effect_gap`: po finalizacji, atomowych source receipts i terminalnym sync przed nowym SHA ustawia `targetCount-recordedTargetCount`. Wyłącznie znany nowy pin i finalny manifest; legacy no-op. Zakres0..target jest walidowany bez clamp. | Red2 FAIL, green2 PASS; backend37 PASS, focused gap/hash/cleanup11 PASS; PG3 PASS. Gap nie jest sumowany jako efekt celu. |
| P2-1 | Świadomie przyjęto ryzyko statement_timeout30s obejmującego całą krótką transakcję finalizacji. Nie przywracano ani nie podnoszono limitu. | Późniejszy timeout nadal wycofuje całość. Nie wykonano benchmarku szerokiej gry. |
| P2-2 | Pin i capacity obliczane raz na `prepare_page`, przed pętlami. | Bez zmiany snapshotu, manifestu, scopeSignature i kwalifikacji. Mypy i PG wykonują rzeczywistą ścieżkę. |
| P2-3 | Po `rg` usunięto wyłącznie nieużywane helpery Admina, ich typy/import oraz wymagania `GridQualityClient`. | Historyczny backend i SDK pozostają. Dwie fake legacy metody nadal służą za pułapkę mounted GET-only testu. |
| P2-4 | Do Verification dopisano i uruchomiono rzeczywiste `npm run test:geometry --workspace @game-predictor/admin`. | Pełny wynik pozostaje **FAIL: 226/236 PASS, 10 FAIL** poza diffem w SuperGame. Nasz focused19 i actions/contract18 PASS. Szczegóły poniżej. |
| P2-5 | Nowy pin bez finalnego manifestu pokazuje nieukończony zakres i niedostępne efekty także przy failed/cancelled prepare. | Rzeczywisty mounted test odróżnia nowy niesfinalizowany zakres od legacy „nie zapisano”. Bez nowego pola API. |

`empty_effect`, DTO i per-target receipt nadal zawierają
`notRecordedTargetCount=0`; pole usunięto jedynie z addytywnych `EFFECT_FIELDS`.
Agregat otrzymuje bieżącą różnicę po zapisie całego źródła. Poprzedni gap nie
jest sumowany ani dekrementowany receiptami. Nieznany/mieszany pin w
FAILED/CANCELLED nadal pozwala zamknąć lease bez nadania polityki lub
publikacji statystyk sukcesu.

## Red, green i rzeczywisty zakres dowodów

- `TASK-1003_R2_gap_red.log`: FAILED/CANCELLED, target3/recorded1, oczekiwany gap2, otrzymano0 (**2 FAIL**). To reproducer P1 sprzed zmiany producenta.
- `gap_green`: **2 PASS**. `backend_green_1`: **37 PASS, 1 HTTP deselected**. `gap_cleanup_hash_green_02`: **11 PASS**, w tym kontrolne3→2→0, brak clamp, legacy SHA, mixed/unknown pin failure/cancel cleanup. Ręcznie ustawione kontrolne liczniki unit nie są deklarowane jako persystowane PG receipts.
- `pg_gap_01`: **3 PASS** na własnej małej fixture. Prawdziwy runtime przygotowuje zakres trzech targetów i zapisuje dwa receipts pierwszego źródła; cancel ma recorded2/gap1, resume kończy ostatni target i gap0. Nie podstawiano ręcznie tych receipts. Kontrolowany wyjątek po rzeczywistym writerze cofa efekty, zachowując dokładne prepared effectStats; po retry/replay completed ma0. Niespójna partial projekcja zostaje odrzucona: efekty komórkowe0, gap równy frozen targetCount, geometria i target receipts bez częściowego zapisu.
- Fixture `TASK-1003_R2_PG_01_PG_RECEIPT.json` potwierdza owner, PID[], databaseRemaining0/roleRemaining0. Baza operatora pozostaje poza zakresem.
- Focused Admin interakcje **19/19 PASS**; actions/contract **18/18 PASS**; pełny Admin typecheck i focused ESLint/format **PASS**. Mypy trzech zmienionych modułów **PASS** z `--follow-imports=silent`.

Zaktualizowano wcześniejszy statyczny test kontraktu, ponieważ zmienił się
świadomie kontrakt montowanego UI. Usunięto dokładnie siedem asercji:
`recalculableBoardCount`, `currentV19BoardCount`, `unsupportedVirtualBoardCount`,
komunikat „wirtualne v0.10 do ręcznej”, komunikat „plikowych siatek symboli 3×5
modułem v19”, `geometryVersion` i `cropperVersion`. Pozostałe asercje są
zachowane. Red17/18 i green18/18 znajdują się w nowych R2 logach. Rzeczywiste
mounted default/GET-only/exactcommand/reload/conflict/late-response testy oraz
backend i SDK historyczne nie zostały osłabione.

## Niezwiązany pełny wynik test:geometry i ograniczenia

`TASK-1003_R2_admin_geometry_01.log` pozostaje **FAIL**: 226 PASS i 10 FAIL.
Wszystkie dziesięć błędów pochodzi z `super-game-series-workspace.test.mjs`:
`undefinedSeriesCountLabel` otrzymuje undefined counts i rzuca TypeError
(`super-game-series-state.ts:101`). Te pliki są poza diffem. Nie poprawiano
SuperGame w tym tasku ani nie maskowano błędów.

W ignorowanym katalogu skopiowano dokładny moduł stanu z HEAD380, SHA256
`7e4190ab0ff322904723e805dea87767c2476f78b09ce02e84ae2d5718c2951a`.
Nie ma on runtime imports. Jedna ograniczona reprodukcja potwierdziła, że
ten dokładny helper HEAD380 rzuca ten sam TypeError dla undefined counts
(`supergame_pure_baseline_01`,1 PASS reproducer). **Nie wykonano pełnej
mounted reprodukcji dziesięciu testów na czystym HEAD ze wszystkimi jego
zależnościami**; nie przedstawiamy jej jako dowiedzionego preexisting PASS/FAIL.

Legalny persystowany unknown-comparison path nadal nie został wykazany.
Poprzedni helper-only dowód i jawne ograniczenie pozostają ważne; nie
wykonywano kolejnych eksperymentów z niepoprawnym PG unknown fixture.

Nie wykonano operator operations, usług, migracji operatora, backupu,
rzeczywistych modelowych runów/GPU, publikacji/aktywacji/defaultu, benchmarku,
stage/commita, integracji, push ani audytu przez wykonawcę. Stare raporty,
R1_SOURCE_ARCHIVE, RUNS i evidence nie zostały zmienione. Końcowy handoff R2
zawiera delta paths, pełne SHA taska, nowe evidence SHA i cleanup; po nim
wykonawca czeka na niezależny werdykt.
