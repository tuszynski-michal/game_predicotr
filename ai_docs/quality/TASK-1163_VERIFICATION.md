---
title: Weryfikacja trwałego runnera audytu TASK-1163
status: active
last_updated: 2026-11-08
---

# Weryfikacja TASK-1163

Implementacja T0 po jednej rundzie poprawek jest gotowa do focused review R2. Ten dokument opisuje
weryfikację wykonawcy; nie jest raportem audytora ani zastępczym PASS Opus.
Wykonawca używał tylko fake CLI, bez płatnego API, logowania, zmian ustawień
i usług. Koordynator wykonał następnie jedną próbę CLI (OAuthblocked)
i rzeczywisty niezależny DesktopR1: REVISE. Raport R1 zachowano oddzielnie.

## Zmienione zachowanie

`scripts/audit_task.ps1` pozostaje wejściem i builderem briefu, zachowując
transport Codex. Claude używa wersjonowanego `scripts/run_claude_audit.py`:
Read/Glob/Grep bez MCP, prompt stdin, 480s total/60s idle według stream events,
atomowe receipt i hashe, blokada duplikatu i jawne próby transportowe.

Receipt zakończenia powstaje przed publikacją. Identyczne żądanie po restarcie
odtwarza raport bez nowego audytora. Windows job kill-on-close zamyka własne
drzewo, a zapis czasu utworzenia procesu chroni przed pomyleniem użytego
ponownie PID. Po zablokowanej próbie numer kolejnej próby jest jawny, a jej
historia pozostaje w artifacts. Nie ma retry, pętli logowania ani zmian auth.

Raport jest publikowany tylko po weryfikacji system.init głównego modelu,
pojedynczego udanego result, exitcode/is_error, pełnych sekcji, taska/rundy/SHA,
werdyktu i spójnych otwartych P0/P1. Modele pomocnicze są dozwolone w
modelUsage i nie są używane jako dowód głównego modelu. Ograniczone stdout
błędów i stderr podlegają redakcji przed zapisem diagnostyki.

Import Desktop przechodzi ten sam walidator; wymaga zaobserwowanego
modelu/effort/sesji i zgodnego SHA również w samym raporcie. Dowód jest
opisany jako obserwacja UI, a effort CLI jako wartość żądana. Żaden z tych
zapisów nie jest deklarowany jako kryptograficzny dowód backendu.

## Testy wykonane

- Fake CLI: 21 różnych przypadków sprawdzonych w grupach, w rzeczywistym
  jednorazowym git worktree należącym wyłącznie do fixture. Każde wywołanie
  runnera jest nowym procesem, bez płatnego API i bez zmian operatorgit.
- PowerShell `scripts/tests/test_auditor_cli.ps1`: PASS, 13 asercji; wykrywanie
  PATH/native/Desktop/package, aktualizacja wersji i regresja Codex.
- Ruff check i format obu nowych plików: PASS.
- Mypy strict obu nowych plików: PASS.
- Dwukrotny DryRun: identyczne bajty/SHA briefu, pełny wiersz T0 modelu
  z planu i brak wywołania CLI. Ścieżka DryRun jest niezależna od Get-FileHash,
  którego nie udostępnia używany host PowerShell; SHA wylicza stdlib .NET.
- Końcowy pełny scoped pytest i kontrola docs/map: wynik dopisany poniżej.

Scenariusze obejmują PASS/REVISE, P1 kontra PASS, niezgłoszone P0/P1,
błędny model/brak init i dozwolony helper, OAuth/rate-limit, brak result,
exitcode/is_error i niepełny/sprzeczny raport, zmieniony SHA, timeout,
malformed noise, zabicie wnuka, stream events przedłużające aktywność,
aktywny duplikat, śmierć ownera i restart, replay po utracie publikacji,
import UI z błędnym SHA i prawidłowym pochodzeniem oraz uszkodzony stored report.

Dwa zbiorcze wywołania przekroczyły limit120s, więc wykonawca przerwał
kosztowną paczkę i sprawdził własne procesy. Żaden żywy PID nie miał tożsamości
utworzenia własnego audytora; ponownie użytych PID nie dotykano. Wczesne
limity fixture0,5/2/5s nie obejmowały rozruchu Windows i tworzenia wnuka.
Wydłużono wyłącznie testowy idle do5s (15s dla wnuka); seria stream events
trwa6s, więc asercja resetowania idle nadal ma znaczenie. Produkcyjny limit
60s nie zmienił się. Testy końcowe mają własne bounded subprocess timeouty.

## Definition of Done i ograniczenia

Kryteria taska1–7 potwierdzają kod i testy. Kryterium8 ma rzeczywisty
Opus5.5/high focusedR2 terminalowy PASS, bez otwartychP0/P1. Raport i receipt
są w `ai_docs/quality/TASK-1163_AUDIT_claude-opus-5-5.*`; R1REVISE zachowany
osobno z sufiksem_R1. Ostateczne metadane zamyka koordynator.

Nie można zagwarantować niewygasania OAuth ani dostępności zewnętrznego
modelu. Procedura odróżnia CLI od Desktop i blokuje błędny/niekompletny wynik,
a nie naprawia poświadczeń operatora. Wykonawca sprawdzał import z fake raportu; koordynator następnie wykonał
i udokumentował rzeczywisty DesktopR1 oraz import jego odpowiedzi.

## Weryfikacja przed R1 (historyczna)

- Scoped grupy fake CLI (każda komenda timeout120s):
  - `-k 'completed_replay or auth_rate or tampered_completed'`: 5 PASS / 6,21s.
  - `-k 'fail_closed'`: 10 PASS / 30,66s.
  - `-k 'timeout or active_duplicate or desktop or stream_activity'`: 6 PASS,
    jeden błąd zbyt krótkiego rozruchu wnuka; jeden parametr OAuth nakłada
    się na pierwszą grupę.
  - `-k 'timeout_stops_owned_tree and child'` po testidle15s: 1 PASS / 26,40s.
  - Daje21różnych przypadków PASS. Pełna końcowa paczka przerwana po120s
    po16testach bez FAIL nie jest raportowana jako pełny pytest PASS.
- Po ostatnim timeout read-only sprawdzenie wszystkich zachowanych receipts:
  `live_owned_auditors: []`. Nie kończono cudzych ani ponownie użytych PID.
- Końcowe doprecyzowanie kompletności wymaga także podsekcjiP0/P1/P2 oraz
  jednej listy zamkniętych. Focused `-k 'incomplete or completed_replay or desktop'`:
  5 PASS / 13,68s po tej zmianie (w tym parametr OAuth nakładający się przez
  nazwę kategorii Desktop).
- `ruff format/check`: PASS. `mypy` strict obu nowych modułów: PASS.
- PowerShell resolver i regresja Codex: PASS, 13 asercji.
- `scripts/generate_code_map.py` i `--check`: PASS.
- `npm.cmd run docs:check`: PASS; 7 aktywnych tasków, okno16312B,
  startup44436B/45000B, wszystkie11budżetów i2pary skilli zgodne.

Weryfikacja pełnej paczki jest ograniczona czasem polecenia. Wymagane
scenariusze mają wyniki w rozłącznych logicznie grupach; nie rozszerzano
limitu, nie zmieniano produkcyjnego zachowania i nie osłabiano asercji.


## Jedyna runda poprawek po audycie R1

Źródło: `TASK-1163_AUDIT_claude-opus-5-5_R1.md` i receipt koordynatora.
Werdykt R1: REVISE, otwarte P0=0/P1=1 oraz5P2. Poniżej opis wdrożonych
poprawek wykonawcy; uwagi nie są deklarowane jako zamknięte przez audytora.

| Uwaga | Wdrożona poprawka i regresja |
|---|---|
| P1-1 | Jednowierszowe Zamknięte w rzeczywistym szablonie i prompcie. Test renderuje prawdziwy blok szablonu i importuje go przez nowy proces. |
| P2-1 | Runda1 nie zamyka ID; listy są rozłączne; treść P0/P1 wymaga ID albo Brak. Testy sprzecznych raportów i prawidłowego zamknięcia R2. |
| P2-2 | Kategoria auth/rate tylko dla nieudanej odpowiedzi i wyłącznie ze stderr lub result z is_error. OAuth w udanym raporcie oraz nieudanym exit z udanym reportem nie stają się auth. |
| P2-3 | Parser błędów kończy kodem1. PowerShell odrzuca puste parametry importu przed runnerem; testy procesowe. |
| P2-4 | Wszystkie grupy uruchomiono sekwencyjnie po ostatnich bajtach kodu i sprawdzano SHA przed każdą i po ostatniej grupie. |
| P2-5 | Import UTF8-SIG; parametry, odczyt i raport walidowane przed próbą. Test BOM i literówek bez zużycia numeru transportu. |

### Wynik po ostatnich bajtach

34/34PASS w6grupach. Każda skończona komenda ma timeout120s; timing testy
nie pracowały równolegle. Nie wykonywano kolejnej pełnej paczki ani realnego
CLI/auth/audytu. Pełne wyniki i kontrola niezmienności hashów:
`artifacts/audits/TASK-1163_R2_VERIFICATION.json`.

| Grupa | Wynik | Czas pytest |
|---|---|---|
| standard | PASS | 5 passed, 29 deselected in 5.55s |
| fail_closed | PASS | 10 passed, 24 deselected in 7.79s |
| audit_regressions | PASS | 13 passed, 21 deselected in 3.95s |
| desktop | PASS | 1 passed, 33 deselected in 1.46s |
| timeouts | PASS | 3 passed, 31 deselected in 27.45s |
| activity_duplicate | PASS | 2 passed, 32 deselected in 13.25s |

### SHA256 zweryfikowanych plików

| Plik | SHA256 |
|---|---|
| `scripts/run_claude_audit.py` | `b5bc5d1756a2e965780d28b83140621ae76f50c02d61e5ed32796d380c4a0fa2` |
| `scripts/audit_task.ps1` | `16aad15677e6d6b8ab6a5b57560c815b1c932088f0305c70102897d98bc3facf` |
| `scripts/tests/test_claude_audit_runner.py` | `2fbb0ed7ae1e0d49bc516e66d1d7b7340955f667eacd2de9dc44a8f36e77b6c2` |
| `scripts/tests/test_auditor_cli.ps1` | `2e020260fd13dce4e695547f05932647553f0e7a13dc8bedb0e9fd3c005cf9f5` |
| `ai_docs/quality/AUDIT_REPORT_TEMPLATE.md` | `5fd1dcfc7446a06104d2dc8494f6b2e0a9d62e5000dfc9aa9893b493e64e8b94` |

Ruff i mypy obu modułów po poprawkach: PASS. Ostateczne docs/map i regresję
PowerShell wykonano bez zmiany powyższych bajtów; wynik przekazano koordynatorowi.


## Rzeczywisty terminalowy odbiór koordynatora

Operator wykonał logowanie wykrytego CLI przez `auth login --claudeai`.
Nowy proces `auth status --json` potwierdził loggedIn:true/authMethod:claude.ai.
Nie wypisywano tokenów ani danych konta. CLI wykrywano aktualnym resolverem,
bez przypinania numeru instalacji; kolejne audyty są terminalowe.

FocusedR2 przez wspólny runner zakończył się PASS, otwarteP0=0/P1=0.
Raport `TASK-1163_AUDIT_claude-opus-5-5.md` i sąsiedni receipt potwierdzają
transportcli, model główny system.init=claude-opus-5-5 i SHA pakietu
bef9a747b56c9cbb0deb3002600f52f2c1ee201a24ce1e024e957f4962fb3520.
High jest zapisane jako żądane; nie udajemy backendowego dowodu effort.
R1REVISE z Desktop zachowano osobno, bez późniejszego używania UI.

ResidualP2-1 zaakceptowano z obowiązkowym pełnym odczytem raportu przed
commitem; walidator nie zastępuje interpretacji sprzecznej odpowiedzi audytora.
P2-6 ograniczono w tasku jawnym cwd worktree; nie zmieniano testowego importu.
Pełny zapis34przypadków i hashów jest również wersjonowany w
`ai_docs/quality/TASK-1163_TEST_RESULTS.json`, niezależnie od ignorowanych artefaktów.
