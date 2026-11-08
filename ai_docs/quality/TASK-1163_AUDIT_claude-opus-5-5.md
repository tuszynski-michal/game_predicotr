# Audyt TASK-1163 — Trwała procedura audytu krzyżowego, focused review R2

Werdykt: PASS

Audytor: claude-opus-5-5, high (effort według zlecenia, niepotwierdzony przez audytora)

Wykonawca: gpt-6.1-sol, high (według raportu R1)

Zakres: HEAD...e16c49fde071de7a65cb4c11e306712637e89c88 oraz zmiany niezacommitowane, zawężone do sześciu uwag R1 i ich bezpośrednich skutków, data 2026-11-08

Runda: 2

SHA pakietu: bef9a747b56c9cbb0deb3002600f52f2c1ee201a24ce1e024e957f4962fb3520

Otwarte P0: 0

Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono poprawki uwag P1-1 oraz P2-1–P2-5, wraz z walidatorem, promptem, szablonem, ścieżką importu, parserem argumentów, wrapperem PowerShell i testami. Jedyna uwaga blokująca, P1-1, jest usunięta, a szablon, prompt, walidator i test opisują teraz ten sam jednowierszowy kontrakt. P2-2, P2-3, P2-4 i P2-5 są zamknięte. P2-1 jest usunięta częściowo, bo sekcja z jednym identyfikatorem nadal przepuszcza dodatkowe znalezisko bez identyfikatora. Doszła jedna nowa uwaga P2 dotycząca zależności nowego importu testowego od katalogu roboczego. Żadna z otwartych uwag nie blokuje commita.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `scripts/run_claude_audit.py:269` — Poprawka częściowa. Blokada zamknięć w rundzie 1 (`:260-261`) i rozłączność list (`:262-263`) działają, ale warunek `body != "Brak." and not identified` odrzuca tylko sekcję całkowicie pozbawioną identyfikatorów. Sekcja zawierająca `- [P1-1] ...` oraz dodatkowe znalezisko bez identyfikatora przechodzi, choć `ai_docs/process/CROSS_AUDIT.md:66-67` wymaga `Brak.` albo znalezisk z identyfikatorami. Skutek: w rundzie 2, przy `P1-1` na liście zamkniętych i `Otwarte P1: 0`, raport z dodatkowym nienumerowanym błędem blokującym uzyska PASS. Wymaga to wewnętrznie sprzecznej odpowiedzi audytora, dlatego waga pozostaje P2. Proponowana poprawka: odrzucać każdy element listy najwyższego poziomu w sekcjach P0/P1, który nie zaczyna się od `- [Pn-m]`, z dopuszczeniem wcięć kontynuacji. Alternatywą jest jawna akceptacja ryzyka.

- [P2-6] `scripts/tests/test_claude_audit_runner.py:19` — Nowy import `from scripts.run_claude_audit import ...` zależy od katalogu roboczego. Repozytorium nie ma `scripts/__init__.py` ani `conftest.py` w katalogu głównym lub `scripts/`, a `pyproject.toml:41` nie dodaje korzenia repozytorium do `pythonpath`. Polecenie z taska (`ai_docs/tasks/1163-durable-cross-audit-runner.md:101`) używa `.venv` z głównego repozytorium i ścieżki `<worktree>/...`, bez wskazania katalogu roboczego. Uruchomienie spoza worktree da błąd importu albo porówna walidator innej kopii, podczas gdy testy procesowe nadal użyją `RUNNER` z worktree. Dotyczy to pięciu przypadków korzystających bezpośrednio z `validate_report`. Proponowana poprawka: ładować moduł przez `importlib.util.spec_from_file_location` ze ścieżki `RUNNER` albo zapisać w tasku wymagany katalog roboczy.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| P1-1: jednowierszowy kontrakt w szablonie, prompcie i walidatorze | spełnione | `ai_docs/quality/AUDIT_REPORT_TEMPLATE.md:80`, `scripts/run_claude_audit.py:254`, `:311-312`, render bloku szablonu w `scripts/tests/test_claude_audit_runner.py:403`; stara forma nie występuje w skryptach, `ai_docs/process` ani skillach audytu |
| P2-1: runda 1 bez zamknięć, rozłączne listy, identyfikatory P0/P1 | częściowo spełnione (otwarty przypadek sekcji mieszanej) | `scripts/run_claude_audit.py:260-271`; test obejmuje wyłącznie sekcję całkowicie nienumerowaną |
| P2-2: kategoria auth/rate tylko po błędzie, ze stderr lub `result` z `is_error` | spełnione | `scripts/run_claude_audit.py:418-426`; scenariusze `oauth`, `rate`, `oauth_topic`, `error_exit_oauth_topic` w pliku testów, `:270-294` oraz sekcja regresji |
| P2-3: błędne argumenty kończą się kodem 1, PowerShell odrzuca puste parametry importu | spełnione | `scripts/run_claude_audit.py:616-620`, `:654-658`, `scripts/audit_task.ps1:376-386`, `:585`, `ai_docs/process/CROSS_AUDIT.md:83-85` |
| P2-4: pełny zakres po końcowych bajtach, z zapisem hashy | spełnione według zapisu wykonawcy; wykonania nie potwierdzono niezależnie | `artifacts/audits/TASK-1163_R2_VERIFICATION.json:2-67`: 5+10+13+1+3+2=34, co zgadza się ze statycznym zliczeniem przypadków (21+13); hashe początkowe i końcowe są identyczne; suma czasów grup 64,61 s odpowiada czasowi całego przebiegu, co potwierdza wykonanie sekwencyjne |
| P2-5: UTF-8 z BOM i preflight przed zapisem próby | spełnione | `scripts/run_claude_audit.py:505-519` przed `:530` i `:568`; ponowne `redact` w `:595` jest idempotentne; katalog żądania powstaje dopiero po preflighcie; test BOM i literówek w pliku testów |

## Listy zamknięte i otwarte

Zamknięte: P1-1, P2-2, P2-3, P2-4, P2-5

Otwarte: P2-1, P2-6

## Proponowane testy

- W `scripts/tests/test_claude_audit_runner.py` dodać do `test_finding_lists_cannot_hide_findings` przypadek sekcji mieszanej: `- [P1-1]` na liście zamkniętych oraz dodatkowy element bez identyfikatora w rundzie 2. Komenda: `.\.venv\Scripts\python.exe -m pytest -q scripts/tests/test_claude_audit_runner.py -k finding_lists`.

- Po usunięciu zależności z P2-6 uruchomić ten plik testów z katalogu innego niż worktree i potwierdzić, że testy importują walidator spod ścieżki `RUNNER`.

## Zakres przeglądu i ograniczenia

Przeczytano manifest R2, zapis wyników weryfikacji, deltę z pakietu oraz wskazane fragmenty zamrożonych `scripts/audit_task.ps1`, testów, `CROSS_AUDIT.md`, szablonu i taska. Plik `scripts/run_claude_audit.py` odczytano w całości z audytowanego worktree. Zgodność z kopią zamrożoną sprawdzono na dwunastu wierszach obejmujących wszystkie sześć poprawek, które wystąpiły pod identycznymi numerami linii.

Audytor nie uruchamiał testów, shella, realnego CLI, usług ani Desktopu. Nie mógł też obliczyć SHA256, więc hashe z pakietu i manifestu nie zostały niezależnie potwierdzone. Wyniki 34/34 PASS, ruff, mypy, regresja PowerShell i docs/map są deklaracją wykonawcy. Plik wyników przechowuje hashe tylko sprzed pierwszej i po ostatniej grupie, dlatego deklaracji o kontroli przed każdą grupą nie da się z niego odtworzyć. Dla zamknięcia P2-4 wystarcza zgodność stanu początkowego i końcowego.

Zgodnie z zakresem nie audytowano T1–T5, rejestracji planu ani generowanych map. Poza liczonymi znaleziskami warto odnotować, że komunikaty w `scripts/audit_task.ps1:575` i `:591` nadal podpowiadają import Desktop, podczas gdy `ai_docs/process/CROSS_AUDIT.md:92-94` wymaga do tego nowego jawnego polecenia operatora.