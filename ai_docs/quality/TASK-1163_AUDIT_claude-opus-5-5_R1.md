# Audyt TASK-1163 — Trwała procedura audytu krzyżowego

Werdykt: REVISE

Audytor: claude-opus-5-5, high (effort według zlecenia, niepotwierdzony przez audytora)

Wykonawca: gpt-6.1-sol, high (według planu i taska)

Zakres: HEAD...e16c49fde071de7a65cb4c11e306712637e89c88 oraz zmiany niezacommitowane, data 2026-11-08

Runda: 1

SHA pakietu: 209ea3f42c80e6e02bdebdeccdbe0abe9ebd979f9e9a9d0a1db3fcdea9b6939a

Otwarte P0: 0

Otwarte P1: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano runner scripts/run_claude_audit.py , delegację z scripts/audit_task.ps1 , testy, procedurę oraz skille. Mechanizmy trwałości są statycznie poprawne: blokada żądania, zapis ukończenia przed publikacją, replay, własność drzewa procesów i weryfikacja system.init.model . Błędy kończą się bez publikacji PASS. Blokuje jedna niezgodność: walidator odrzuca raport wypełniony dosłownie według wersjonowanego szablonu, a fixture testów tego nie wykrywa. Główne ryzyko to utrata płatnego audytu i zużycie próby transportowej przy poprawnej odpowiedzi audytora.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] scripts/run_claude_audit.py:254 — Walidator wymaga wiersza zaczynającego się dokładnie od Zamknięte: , natomiast szablon w ai_docs/quality/AUDIT_REPORT_TEMPLATE.md:77 każe użyć Zamknięte (tylko w rundzie 2 lub później): ..., i to w zapisie dwuwierszowym. Prompt w scripts/run_claude_audit.py:296-298 odsyła do szablonu i nie wymienia formy Zamknięte:, a fixture w scripts/tests/test_claude_audit_runner.py:55 używa formy niewystępującej w szablonie. Skutek: audytor, który dosłownie stosuje szablon, dostaje kod 4 po pełnym płatnym przebiegu, próba przechodzi w blocked, a kolejna wymaga jawnego -TransportAttempt. Dotyczy to CLI oraz importu Desktop. Minimalna poprawka: zmienić szablon na jednowierszowe Zamknięte: <identyfikatory albo Brak.>, dodać tę formę do promptu i dodać test budujący raport z bloku szablonu. Alternatywnie walidator może akceptować obie formy, ale wtedy musi poprawnie czytać listę wielowierszową.

### P2

- [P2-1] scripts/run_claude_audit.py:258 — W rundzie 1 raport z - [P1-1], Otwarte P1: 0 iZamknięte: P1-1 przechodzi jako PASS, choć szablon dopuszcza listę zamkniętą dopiero od rundy 2. Znalezisko zapisane bez formy - [P1-n] w ogóle omija sprawdzenie. Wymaga to wewnętrznie sprzecznej odpowiedzi audytora, stąd P2. Poprawka: w rundzie 1 odrzucać identyfikatory zamknięte, odrzucać identyfikator obecny na obu listach oraz treść inną niżBrak. bez identyfikatora w sekcjach P0/P1.

- [P2-2] scripts/run_claude_audit.py:404 — Kategoria błędu jest liczona także po udanym przebiegu, z ogona stdout zawierającego treść raportu i partial messages. Słowo „OAuth” w ostatnich 8 KiB zapisze failure_category: cli-auth przy ukończonej próbie, a przy innej awarii może podsunąć błędną diagnozę. Audyty tego taska są na to szczególnie narażone. Poprawka: klasyfikować wyłącznie w ścieżce błędu i wyłącznie ze stderr oraz pola resultzdarzenia z is_error.

- [P2-3] scripts/run_claude_audit.py:611 — parser.error kończy proces kodem 2, a ai_docs/process/CROSS_AUDIT.md:81 definiuje 2 jako timeout i 1 jako błędne wejście. Dotyczy też scripts/audit_task.ps1:556-557: pusty parametr importu może zostać pominięty przez PowerShell 5.1, co argparse zgłosi jako błąd składni. Skutek to fałszywa diagnoza timeoutu, bez ryzyka PASS. Poprawka: nadpisać error, aby zwracał 1, i sprawdzać niepustość parametrów importu przed wywołaniem runnera.

- [P2-4] ai_docs/quality/TASK-1163_VERIFICATION.md:86 — Komenda weryfikacji z taska nigdy nie zakończyła się w całości, co wykonawca uczciwie zapisał. Po ostatniej zmianie walidatora (linia 90) uruchomiono tylko 5 przypadków, więc 21 PASS nie dotyczy końcowych bajtów. Poprawka: po usunięciu P1-1 powtórzyć wszystkie grupy na końcowym kodzie i zapisać hash lub stan pliku, którego dotyczą.

- [P2-5] scripts/run_claude_audit.py:552 — Import czyta plik jako utf-8, więc BOM dodany przez narzędzia PowerShell powoduje niedopasowanie nagłówka # Audyt i kod 4. Kontrola SHA, modelu i sesji (linie 544-551) następuje dopiero po zarejestrowaniu próby w linii 536, więc literówka operatora zużywa numer próby. Poprawka: czytać przez utf-8-sig i przenieść walidację parametrów importu przed attempts.append.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (ścieżka:linia lub wynik polecenia) |
| --- | --- | --- |
| Dynamiczne wykrywanie CLI, read-only, brak MCP | spełnione | scripts/audit_task.ps1:322-363 , scripts/run_claude_audit.py:267-288 |
| Auth CLI nie oznacza wylogowania Desktop, brak pętli retry | spełnione (z uwagą P2-2) | scripts/run_claude_audit.py:404-408 , :522-527 |
| Stream, limit 480 s, własny PID i drzewo | spełnione | scripts/run_claude_audit.py:347-348 , :366-369, :389, :423, :615 |
| Idempotencja, restart, odrzucenie aktywnego duplikatu | spełnione | scripts/run_claude_audit.py:500 , :506-520, :581 |
| Główny model, effort, transport, SHA pakietu i raportu | spełnione | scripts/run_claude_audit.py:413 , :440-470, :576-580 |
| PASS wymaga kompletnego raportu bez otwartych P0/P1, błąd nie publikuje PASS | spełnione (fail-closed; zbyt ścisłe według P1-1, luka według P2-1) | scripts/run_claude_audit.py:225-264 , :584-588 |
| Test w nowym procesie i innym worktree, bez płatnego wywołania | niezweryfikowane (kod testów obecny, wykonania nie sprawdzono) | deklaracja ai_docs/quality/TASK-1163_VERIFICATION.md:86 |
| Skille i startup wskazują jedną procedurę, audyt Opus, docs/map PASS | niespełnione (odsyłacze obecne, audyt ma werdykt REVISE) | AGENTS.md, sekcja „Audyt krzyżowy”, ten raport |

P1-1 jest naruszeniem kontraktu między szablonem a walidatorem. Nie powoduje publikacji błędnego PASS, dlatego ma wagę P1, a nie P0.

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P1-1, P2-1, P2-2, P2-3, P2-4, P2-5

## Proponowane testy

- W scripts/tests/test_claude_audit_runner.py dodać przypadek budujący raport z bloku szablonu ai_docs/quality/AUDIT_REPORT_TEMPLATE.md. Komenda: pytest -q scripts/tests/test_claude_audit_runner.py -k template.

- Fail-closed dla rundy 1 z Zamknięte: P1-1 oraz dla znaleziska P1 bez formy - [P1-n].

- Udany przebieg z „OAuth” w treści raportu: brak failure_category w receipt.

- Wywołanie z błędnymi argumentami: kod 1, nie 2.

- Import pliku z BOM oraz import z błędnym SHA bez zużycia numeru próby.

## Zakres przeglądu i ograniczenia

Przeczytano zamrożony brief wraz z pełnym kodem i testami, a w worktree scripts/run_claude_audit.py (linie 225-588), wybrane fragmenty scripts/audit_task.ps1 oraz AGENTS.md , a także wyszukane wiersze szablonu raportu, CROSS_AUDIT.md i pliku weryfikacji. Nie uruchomiono testów, shella, realnego CLI, Desktopu ani bazy. Wynik statyczny nie zastępuje wykonania testów. Nie dało się potwierdzić faktycznej wartości system.init.model ani obsługi flag w realnej wersji CLI. Zachowania Job Object i blokady systemowej oceniono wyłącznie z kodu. Pominięcie pustego argumentu w PowerShell 5.1 (P2-3) wynika ze znanego zachowania powłoki i nie zostało tu wykonane. Rejestracji planu, map generowanych i implementacji T1–T5 nie audytowano. Wiersz listy zamkniętych zapisano w formie Zamknięte: , aby raport przechodził obecny walidator mimo P1-1.
