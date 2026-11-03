**Audyt TASK-1155 (focused review): audytor claude-opus-5-5/high, Runda2**

Werdykt: PASS

- **Baza:** `codex/full-board-detection` @ `0a7ef2d3` plus niezacommitowane zmiany TASK-1155. Delta liczona względem snapshotu R1 (SHA pakietu R1 `30e36c35…c772`).
- **Zakres:** pakiet `artifacts/audits/TASK1155-focused-r2-review.md`. Oceniam tylko zamknięcie P1 koordynatora, P2-1..P2-5 z R1 i zgłoszonych P3 oraz skutki zmienionego kodu i testów. Do tego celowane odczyty kontekstu:
  - `grid_training_cohort_evidence.py:333-346` (opakowanie błędu wycofanego źródła),
  - `source_replacement_guards.py:42-51`,
  - `input_diagnostics.py:46-50,86-93` (`ModelPin`, `DiagnosticUse`),
  - `grid_cohort_dataset.py:214-220,481-486` (semantyka `fullPhotos`),
  - `grid_diagnostic_readiness.py:20,90-95,172-173`,
  - `diagnose_full_board_input.py:352-368`.
- **Tryb:** tylko przegląd statyczny (Read/Grep/Glob). Niczego nie zmieniłem i nie uruchomiłem testów, usług ani bazy. Wyników wykonawcy nie powtarzałem.

### P0 / P1
Brak.

**P1 koordynatora jest zamknięte.** Sprawdziłem to w kodzie:
- `reconstruct_input` (`input_diagnostics.py:187-198`) liczy kanoniczny `digest(archived_preset)` i porównuje go z `model.preset_sha256`.
- Wymaga też, żeby `model.preprocessing_version` było równe `SUPPORTED_PREPROCESSING_VERSION` i `archived_preset.preprocessing_version`.
- Porównuje `screen`/`board` z presetu z `screen_preset`/`board_preset` rekordu.
- Capture zapisuje jako `archived_preset` cały `bundle["preset"]`, którego SHA już wcześniej porównał z SHA bundle (`scripts/...:~240-243`). Hash dotyczy więc pełnego presetu, a nie jego podzbioru. Przypięcie SHA bundle pozostaje osobne.
- Pięć nowych przypadków negatywnych przelicza checksum envelope. Każdy z nich łapie wyłącznie nowa kontrola, bo pola `archived_preset` i `model.preprocessing_version` nie biorą udziału w odtwarzaniu. Usunięcie którejkolwiek kontroli wywróciłoby test, więc testy rzeczywiście odtwarzają regresję.
- Test `test_supported_preprocessing_matches_runtime_protocol` wiąże stałą z `neural_grid_protocol.PREPROCESSING_VERSION`.

### P2 (1)

1. **Nowy wymagany kontrakt ma tę samą wersję schematu.**
   - **Miejsce:** `services/worker/src/game_predictor_worker/geometry_core/input_diagnostics.py:97` (`schema_version` `…-v1`) i `:101` (`archived_preset` wymagany).
   - **Skutek:** rekordy R1 i R2 mają ten sam identyfikator `full-board-input-diagnostic-v1`, ale niezgodne kształty. Przedwydaniowy rekord R1, który zachowano jako dowód, przy odtworzeniu odpadnie z ogólnym `ValidationError` zamiast z jawnym kodem wersji. Działa to bezpiecznie (rekord jest odrzucany), ale historia jest niejednoznaczna, a T4 nie rozróżni wersji po polu.
   - **Minimalna poprawka:** podnieść wersję do `full-board-input-diagnostic-v2` albo dodać jawny kod `DIAGNOSTIC_ARCHIVED_PRESET_REQUIRED`. Do tego test rekordu w kształcie R1 (bez `archived_preset`), który oczekuje tego kodu.

### P3 (bez wpływu na werdykt)
- **Licznik nominalny:** `grid_diagnostic_readiness.py:152` sumuje w `nominalHumanBoards` także odrzucone (wycofane) źródła. Różnicę nominal−qualified można więc odczytać jako straty kwalifikacji. Wystarczy dopisać to do `limitations` albo dodać licznik `rejectedNominalHumanBoards`.
- **Testy dryfu bez kodu błędu:** `test_full_board_input_diagnostics.py` (przypadki dryfu, `pytest.raises((ValueError, ValidationError))`) nie ma `match=`. Dziś każdy przypadek łapie tylko jedna kontrola, ale `match="DIAGNOSTIC_PRESET_…"` utrwaliłby, która.
- **Brak testu drugiego kodu:** nie ma testu dla `GRID_COHORT_SOURCE_REMOVED`, testowany jest tylko `SOURCE_REPLACEMENT_RETIRED`.
- **Kontrola frozen tylko dla ról z manifestu:** `scripts/diagnose_full_board_input.py:~375-383` porównuje wyłącznie role obecne w manifeście. Użyte źródło z rolą spoza `_ROLES` nie zostałoby wykryte. Semantyka `boards/photos/fullPhotos` jest zgodna z `grid_cohort_dataset.py:481-486`.
- **Testy tylko dla Windows:** `publish_capture` i testy katalogu nie działają poza Windows i nie mają `skipif`. Jest to jawne ograniczenie.
- **Pozostałe P3 z R1, nadal otwarte:**
  - nazwa pola `fullHumanAnnotatedCount` w tasku vs `fullyHumanAnnotatedPhotos` w kodzie;
  - zapasowe `fitted_nodes` przy `FIT_FAILED`;
  - konto właściciela schematu w readiness.

### Zamknięcie uwag R1

| ID | Status | Uzasadnienie statyczne |
|---|---|---|
| P1 koordynatora (preset/hash) | **zamknięte** | jak wyżej |
| P2-1 wycofane źródło | **zamknięte** | `capture` zamienia `SourceReplacementError` na `GridCohortError(code)` (`evidence.py:338-341`). `readiness.py:117-128` łapie tylko 2 kody, inne kody przepuszcza dalej (jest test). Błędy SQL i timeout nie są łapane. Kursor `nextSourceId` bierze ostatnie źródło z `selected` (obejmuje odrzucone). Test sprawdza stronę złożoną wyłącznie z odrzuconych źródeł. |
| P2-2 przypięcie presetu/modelu | **zamknięte** | jak P1 |
| P2-3 ochrony DB | **zamknięte** | Prawdziwy listener: test 8000→1000 ms i `TimeoutError` przy przekroczonym terminie, rollback i `event.remove` sprawdzone. Przekroczenie terminu w trakcie `capture` nie daje raportu. PG: rzeczywiste `SHOW transaction_read_only=on`, SQLSTATE 25006 i 57014 (`pg_sleep` przy timeout 50 ms), w tabeli 0 wierszy. Ograniczenie: `GameStorageRouter.bind` jest zastąpiony. |
| P2-4 `diagnosticUse` | **zamknięte** | Klucz `(source_id, source_sha256, normalized_pixel_sha256, purpose)` z wersją klucza. Pozostałe pola `DiagnosticUse` są typu `Literal`, więc `setdefault` nie zależy od kolejności. Lista `records` jest sortowana po SHA. Test sprawdza duplikat, kolejność i zgodność z `report.records`. |
| P2-5 trwałość i wyłączność | **zamknięte z jawnym ograniczeniem** | `mkstemp`→fsync→`rename` bez nadpisania (Windows) lub `link` (POSIX), plik tymczasowy zawsze sprzątany. Capture: fsync wszystkich plików, potem `rename` katalogu, który na Windows nie zastępuje istniejącego. Testy: wyścig dwóch zapisów, awaria fsync, kolejność fsync/rename, istniejący pusty katalog. Brak fsync katalogu i gwarancji przy zaniku zasilania (zadeklarowane). Przy błędzie zostaje katalog staging. |
| P3 frozen: liczniki | **zamknięte** | tylko użyte źródła, porównanie z manifestem, test rozbieżności, plik nie powstaje |
| P3 populacja readiness | **zamknięte** | wpis w `limitations` |
| P3 słaby test historyczny | **zamknięte** | jeden rekord: `automatic` + blocker `NEURAL_GRID_FIT_OUTLIERS` → `blocked` |
| P3 nazwa pola, `fitted_nodes`, konto DB | otwarte (P3) | bez zmian |
| P2-R2-1 wersja schematu | **otwarte (P2)** | nowe |

### Pokrycie kryteriów (tylko te, których dotyczy delta)
- **Identyfikacja modelu/presetu i wersji preprocessingu:** teraz w pełni weryfikowalne z samego rekordu, z zastrzeżeniem P2-R2-1.
- **LIVE i frozen, liczniki i ograniczenia:** spełnione i wzmocnione (selected/nominal/qualified/successful, `rejectedSources`, zgodność z manifestem).
- **`diagnosticUse` tylko z faktycznie użytymi przykładami, readiness daje `[]`:** spełnione. Readiness i frozen nadal zwracają `[]`.
- **Role, historia, kopie i bufory bez zmian:** spełnione. Transakcja READ ONLY potwierdzona realnie w PG. Nowy kod nie wprowadza zapisów do bazy.
- **Pozostałe kryteria:** bez zmian względem R1 (spełnione).
- **Testy, audyt i commit:** otwarte zgodnie z procedurą. Ten PASS pozwala przejść do task-close i commita.

### Proponowane testy
- Rekord w kształcie R1 bez `archived_preset` daje jawny kod lub wersję (P2-R2-1).
- `match=` z kodem dla każdego przypadku dryfu presetu.
- `GRID_COHORT_SOURCE_REMOVED` trafia do `rejectedSources`.
- Frozen z użytym źródłem o roli spoza manifestu.

### Ograniczenia
- Przegląd wyłącznie statyczny pakietu delty i wymienionych fragmentów kontekstu. Nie wprowadziłem żadnych zmian i nie uruchomiłem testów (38 jednostkowych + 2 PG wykonawcy przyjmuję jako niezweryfikowane).
- Nie widziałem danych operatora, capture R2 ani logów `*r2*.log`.
- Numery linii są przybliżone, liczone z hunków delty.
- Test PG nie obejmuje `GameStorageRouter.bind` ani prawdziwej selekcji i capture.
