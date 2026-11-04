# Audyt TASK-1157: detektor w procesie korekt i dowodowy ratunek (focused R2)

Werdykt: PASS
Audytor: claude-opus-5-5/high
Wykonawca: gpt-6-astra/high
Zakres: baza 6325a0579c6f2cd5aed66b4cf894c09682be4ab1 (v1.7.561) plus niezacommitowane zmiany z pakietu `artifacts/audits/task1157-r2` (manifest e8b116cd…, SourceSet 3b568393…), data 2026-11-04. Oceniałem tylko zamknięcie uwag R1, P1 koordynatora i skutki delty R1→R2.
Runda: 2

Przegląd był wyłącznie statyczny (Read/Glob/Grep). Nie zmieniałem żadnych plików i nie uruchamiałem testów, usług, bazy ani sieci.

## Streszczenie

Główna zmiana tej rundy, atomowa publikacja receiptów bez nadpisywania, rzeczywiście zamyka P1 koordynatora. Receipt powstaje w kolejności tempfile → fsync → `os.link`. Obliczenia CPU startują dopiero po opublikowaniu i odczytaniu rezerwacji. Awaria przed publikacją pozwala na czystą ponowną próbę. Rezerwacja bez wyniku zużywa próbę. Uszkodzony lub obcy receipt nadal kończy się twardym błędem.

Alias z tymi samymi bajtami i innymi pozycjami działa zachowawczo: nie dostaje nowego budżetu i zostaje w ręcznej korekcie. Test z prawdziwym czytnikiem odtwarza złożoną regresję P2-4. Nie znalazłem nowych P0/P1. Zostały dwa drobne ryzyka P2.

## Znaleziska

### P0

Brak.

### P1

Brak. P1 koordynatora (wcześniej R1 P2-1) jest zamknięte, dowody niżej.

### P2

- [P2-6] `services/worker/src/game_predictor_worker/images/grid_rescue_runtime.py:212-219` oraz `services/worker/tests/test_screen_rescue_proof.py:331-340`: alias wpisuje do `rescueExecution` próby pierwszego zakresu (`state: completed`, `resultSha256`), a zwraca bazowe detekcje bez ratunku.
  - **Skutek:** projekcja dla aliasu pokazuje „wykonane” próby, które nie zostały zastosowane do jego wyników. Przy odtwarzaniu w T5 można je błędnie przypisać temu wystąpieniu. Ryzyko łagodzą kod `GRID_RESCUE_SLOT_BINDING_REQUIRED` i odmienne `identity.positions`. Bezpieczeństwo nie jest naruszone, bo blokada auto-crop jest egzekwowana (`grid_reinference_handler.py:764-766` → `NEURAL_AUTO_CROP_BLOCKING_REASONS`).
  - **Minimalna poprawka:** sama dokumentacja w handoffie T5. Próby w summary z tym kodem powodu należą do innego zakresu i nie są wykonaniem dla tego wystąpienia. Bez nowej wersji kontraktu.
- [P2-7] `services/worker/src/game_predictor_worker/images/grid_rescue_runtime.py:63-78`: brak fsync katalogu po `link` i brak sprzątania osieroconych plików `.rescue-pending-*`.
  - **Skutek:** na systemie plików bez hardlinków (FAT/exFAT, część udziałów SMB) `os.link` rzuca `OSError`, więc zadanie kończy się błędem zamiast ręcznej korekty. Osierocone pliki tymczasowe się kumulują. Działanie zostaje fail-closed. Gwarancji na wypadek utraty zasilania wykonawca jawnie nie deklaruje.
  - **Minimalna poprawka:** akceptacja ryzyka z notą w VISION_LAB, że katalog artefaktów musi leżeć na NTFS. Opcjonalnie sprzątanie `.rescue-pending-*` starszych niż operacja.

## Pokrycie kryteriów (zakres R2)

| Kryterium | Status | Dowód |
|---|---|---|
| Kompletny receipt publikowany atomowo, bez nadpisania, przed CPU | spełnione | `grid_rescue_runtime.py:60-81`: mkstemp w tym samym katalogu, fsync, `os.link`, `FileExistsError` → walidacja zwycięzcy. Linie 104-109: `calculate()` dopiero gdy `fresh` |
| Awaria przed publikacją pozwala ponowić; awaria po rezerwacji zużywa próbę | spełnione | `test_screen_rescue_contract.py:183-225`: 4 punkty `os._exit(71)`, świeży proces. `before_fsync`/`before_reserve_publish` → `completed` i brak pliku `calculated`. `after_reserve`/`before_result_publish` → `consumed_without_result`, bez ponownego wywołania |
| Uszkodzony lub obcy receipt nie jest traktowany jako odzyskanie | spełnione | `_read` w liniach 30-58 (JSONDecodeError jest ValueError, zestaw kluczy, sha, identity). Test `:259-265` dla `""`, ucięcia i `{}` |
| Brak odnawiania tokenów i brak nadpisywania | spełnione | `os.link` nie zastępuje istniejącego celu. Alias: `attempt` w liniach 93-94 kończy się błędem, zanim cokolwiek się wykona |
| Alias różniący się tylko pozycjami: baseline, ręczna korekta, stabilny powód; dryf = twardy błąd | spełnione (uwaga P2-6) | `_read` w liniach 43-57 porównuje wszystkie klucze poza `positions`. Runtime w liniach 212-219. Testy `test_screen_rescue_contract.py:227-257` (źródło/pin obcy → `CHECKPOINT_INVALID`) i `test_screen_rescue_proof.py:331+` (`FIT_OUTLIERS` dowodzi oryginalnego baseline) |
| Hash etykiet z prawdziwego czytnika: prepare_split == capture dla full TRAIN/A i partial REG; strażnik zachowany | spełnione | `services/api/tests/test_screen_correction_reader_contract.py:22`. Działa prawdziwy kod `prepare_split` v3, `split_mapping`, `validate_population`, `capture`/`approval`/`render`/`exact_lattice` i `_capture`. Etykieta nie zawiera roli ani trybu (`capture`, budowa `label`). Dryf w każdej roli (`:199`) → `GRID_CORRECTION_LABELS_CHANGED`, `published == []` |
| P2-3: koszt synchronicznej inspekcji i brak powodu w pinie udokumentowane jako ryzyko | spełnione | delta VISION_LAB i DECISION_LOG_2026: T5 pokazuje „niedostępne/nieznane” |
| P2-5: ranking checkpointu ocenia wybrany potok od oryginału; checkpoint związany z własnym bestStep/path proof; B/REG nie wybierają | spełnione (dokumentacja) | delta DECISION_LOG_2026 i VISION_LAB. Kod poza deltą jest identyczny z R1 (według manifestu) |
| Brak nowej polityki/wersji i brak przepisywania wydanych danych | spełnione | delta dotyczy tylko runtime, testów i dokumentacji; SQL bez zmian |

## Listy zamknięte i otwarte

**Zamknięte:**
- **P1 koordynatora / R1 P2-1:** atomowa publikacja plus testy z kontrolowanymi awariami procesu (dowody w tabeli).
- **R1 P2-2:** zachowawczy alias, bez budżetu, z blokadą `NEURAL_GRID_SLOT_BINDING_REQUIRED`.
- **R1 P2-3:** zaakceptowane ryzyko, udokumentowane.
- **R1 P2-4:** złożony test z prawdziwym czytnikiem.
- **R1 P2-5:** semantyka udokumentowana.

**Otwarte:** P2-6, P2-7 (oba P2, nieblokujące).

## Proponowane testy

- **Alias na poziomie handlera:** `grid_reinference_handler` z pinem v2, dwa wystąpienia tego samego `checksum_sha256` z różnymi `expected_positions` w jednej operacji. Sprawdza `reasonCodes` w surowym cache i blokadę auto-crop v2.
  - Komenda: `.\.venv\Scripts\python.exe -m pytest services/worker/tests -k alias`
- **Ścieżka zatwierdzenia przez komendę:** wariant `test_screen_correction_reader_contract.py` z `action='approved'` i komendą/manifestem zatwierdzenia. Obecny test pokrywa tylko `geometry_saved`.
- **Osierocone pliki tymczasowe:** po awarii `before_fsync` drugi restart nie zwiększa liczby prób, a `summary` ignoruje `.rescue-pending-*`.

## Zakres przeglądu i ograniczenia

- **Przeczytane w całości:** INDEX oraz part-01 do part-03: raport R1, klasyfikacja koordynatora, delty dokumentacji, runtime i testów, nowy test czytnika, czytnik `GridCohortEvidenceReader`, `prepare_split`, `split_mapping`, `_capture`, polityka auto-crop i emitowany SQL v2/v4.
- **Przeczytane celowanymi zakresami w repozytorium:** `grid_rescue_runtime.py:1-110` (zgodny z pakietem), `grid_reinference_handler.py:690-784`, sygnatury `population`/`contexts`/`validate_population` w `grid_correction_split.py` oraz `AUDIT_REPORT_TEMPLATE.md`.
- **Nie uruchamiałem:** testów, ruff, mypy ani usług. Wyniki wykonawcy (21+1 PASS) przyjmuję wyłącznie jako deklarację.
- **Czego nie da się sprawdzić statycznie:**
  - zachowania `os.link` i fsync na docelowym wolumenie;
  - trwałości po utracie zasilania (wykonawca jej nie deklaruje);
  - roli i transakcji w PG dla nowej kompozycji. Test podstawia granice SQL i publikacji, a `contexts` wymusza role, więc solver nie wybiera ról samodzielnie.
