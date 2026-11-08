---
title: Trwała procedura audytu krzyżowego
status: active
last_updated: 2026-11-08
---

# Audyt krzyżowy

Reguły zgód, modeli i jednej rundy poprawek zawiera `AGENTS.md`; format raportu
określa [szablon](../quality/AUDIT_REPORT_TEMPLATE.md). Ta procedura jest
wspólnym opisem transportu Claude dla skilli audytu. Audytor ocenia tylko
zakres taska; nie wykonuje testów, nie zmienia plików i nie dostaje sekretów.

## Terminal i przygotowanie pakietu

`scripts/audit_task.ps1` zachowuje istniejący builder briefu i ścieżkę Codex.
Claude odkrywa przez `Resolve-AuditorCli`: PATH, natywny katalog użytkownika,
instalację Desktop oraz fizyczne katalogi pakietu Windows. Nie utrwalaj wersji
ani builda. Brak PATH nie oznacza braku instalacji, a `--version` nie dowodzi
autoryzacji ani wykonania audytu. Nie instaluj i nie loguj CLI za operatora.

Przykład z katalogu worktree (Python musi wskazywać istniejącą instalację):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/audit_task.ps1 `
  -Task 1163 -Auditor claude -Model claude-opus-5-5 -Effort high `
  -Paths scripts/run_claude_audit.py,scripts/audit_task.ps1,scripts/tests `
  -Plan ai_docs/delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md `
  -Python D:/game_predicotr/.venv/Scripts/python.exe -TimeoutSec 480 -DryRun
```

Dostosuj `-Paths` do pełnego zakresu taska; przykład nie jest jego listą plików.
`-DryRun` zapisuje tylko pakiet i wypisuje SHA256, bez płatnego wywołania.
Sprawdź brak danych spoza zatwierdzonego zakresu. Uruchomienie bez `-DryRun`
wykonuje jedną próbę. Host audytu ma limit 600 s, runner najwyżej 480 s,
bezczynność strumienia najwyżej 60 s. Codex domyślnie zachowuje `medium`,
Claude używa `high`; tabela planu jest nadrzędna wobec domyślnych ustawień.

Runner `scripts/run_claude_audit.py` przekazuje cały zamrożony pakiet na stdin
CLI, w cwd worktree: `-p --permission-mode plan`, wybrany model/effort,
`--tools Read,Glob,Grep --allowedTools Read,Glob,Grep`,
`--strict-mcp-config --mcp-config '{"mcpServers":{}}'`,
`--no-session-persistence --output-format stream-json --verbose
--include-partial-messages`. Nie zmienia `setting-sources`, ustawień konta ani
auth. Tryb narzędzi ogranicza czynności, nie jest izolacją odczytu systemu
plików; audytor otrzymuje dodatkowo jawne ograniczenie zakresu.

## Wynik, trwałość i błędy

Pakiet i parametry task/model/effort/runda identyfikuje SHA żądania. Receipts,
PID, historia prób i ograniczone, zredagowane ogony stdout/stderr są wyłącznie
w `artifacts/audits/requests/<requestSHA>/`. Systemowa blokada odrzuca aktywny
duplikat przed startem drugiego procesu. Runner ma własne drzewo procesów
(Windows job z kill-on-close); nie przejmuje portów ani cudzych procesów.

Prawidłowy `system.init.model` potwierdza główny model. `modelUsage` może
zawierać modele pomocnicze i nie służy temu sprawdzeniu. Effort CLI jest
zapisany jako żądany, bez obietnicy potwierdzenia przez backend. Błąd procesu,
`is_error`, brak pojedynczego końcowego `result`, błędny model lub niepełny
raport nie publikują nowego raportu. Wcześniejszy raport nie jest dowodem
nowego żądania; zawsze porównaj jego receipt z SHA aktualnego pakietu.

Raport musi mieć dokładnie jeden werdykt, poprawny task/rundę/SHA pakietu,
wszystkie sekcje szablonu, jawne liczniki otwartych P0/P1 oraz zgodną listę
identyfikatorów. W rundzie1 lista `Zamknięte:` ma `Brak.`; identyfikator
nie może być jednocześnie otwarty i zamknięty. SekcjeP0/P1 mają `Brak.`
albo znaleziska z identyfikatorami. `PASS` wymaga obu liczników równych zero. Prawidłowy `REVISE`
jest zakończonym audytem, ale blokuje commit. Raport i ograniczone metadane
pochodzenia zapisują się w `ai_docs/quality/TASK-NNNN_AUDIT_<model>.md` oraz
sąsiednim `.receipt.json`; oba pliki należy zachować w commicie audytu.

Zakończone żądanie o identycznych bajtach odtwarza raport z receipt także
po restarcie i utracie odpowiedzi/publikacji, bez kolejnego CLI. Numer próby
transportowej nie zmienia tożsamości żądania. Po timeout/auth/rate-limit
nie ma automatycznego retry. Najpierw odczytaj ograniczoną diagnostykę i
sprawdź stan własnego procesu. Jawne kolejne wywołanie tego samego żądania
używa `-TransportAttempt 2`; historia poprzedniej próby pozostaje. Nie zmieniaj
rundy, aby ukryć nieukończony transport. Żywy osierocony proces o potwierdzonej
tożsamości blokuje nowy start do wyjaśnienia. Niejasna tożsamość też blokuje.
`-ReviewRound 2` oznacza osobny, skupiony review po jednej rundzie poprawek,
z wcześniejszym raportem i deltą w pakiecie; nie służy ponawianiu transportu.

Kody runnera: 0 zweryfikowany PASS lub REVISE/replay; 1 błędne wejście;
2 timeout; 3 błąd CLI/modelu/procesu lub uszkodzony zapis; 4 nieprawidłowy
raport; 6 duplikat albo brak jawnego numeru kolejnej próby. Kod 0 sam nie
uprawnia do commita: przeczytaj werdykt i dopasuj receipt. Brak Claude CLI
zapisuje brief i kończy się kodem 3, bez werdyktu. `-DryRun` kończy się 0
wyłącznie jako przygotowanie. Ścieżka Codex zachowuje dotychczasowe kody.

## Niezależna sesja Desktop i jawny import

Operator wybrał audyty wyłącznie terminalowe (2026-11-08). Desktop jest
opcjonalną metodą zastępczą tylko po nowym jawnym poleceniu operatora dla
konkretnego audytu. Błąd CLI nie uruchamia automatycznie tej metody.

Wygasłe OAuth standalone CLI nie oznacza wylogowania z aplikacji Claude.
Sesja Desktop Code może działać niezależnie. Jedna nieudana próba CLI nie
uzasadnia pętli logowania, kopiowania tokenów ani zmiany źródeł ustawień.
Rate-limit i brak odpowiedzi pozostają brakującym audytem. Wyjątek pozwalający
kontynuować implementację kolejnych tasków musi pochodzić od operatora;
oczekujący task nie otrzymuje zastępczego PASS.

Dopiero po takim poleceniu operatora i potwierdzeniu działania Desktop użyj
dostępnego narzędzia computer-use i jego instrukcji. Nie twórz własnego UIA ani skryptu omijającego
aplikację. W niezależnej nowej sesji wybierz rzeczywisty model/effort z planu,
przekaż dokładne bajty briefu wraz z SHA i instrukcją pełnego szablonu.
Zapisz faktycznie zaobserwowane model/effort, identyfikator lub opis sesji oraz
wynik. Jeżeli ustawień nie da się potwierdzić, nie deklaruj ich jako dowodu.

Sprawdzona obsługa Desktop (2026-11-08): przed `click` pobierz `sky.get_window_state` z `include_screenshot:true`, aby ustalić geometrię wejścia.
Dla pola Prompt użyj `sky.set_value`; `type_text` miał problem z fokusem. Pakiet można odczytać lokalnie przez `node:fs/promises` i przekazać do `set_value`, bez wypisywania treści.
Wyniki zawierające obrazy emituj jako obrazy, zamiast serializować cały obiekt narzędzia do JSON/tekstu.
Nowa niezależna sesja ma mieć Plan i rzeczywiste Opus5.5/High; wszystkie odczyty wskazują absolutne ścieżki audytowanego worktree, bo domyślne środowisko UI może wskazywać main.
Zachowaj odpowiedź z dostępności UI w `.ui-tree.txt` i znormalizuj do Markdown bez zmiany znaczenia. Raw odczyt jest zapisem odpowiedzi audytora, nie alternatywnym autorem audytu.

Zapisz odpowiedź do pliku roboczego w `artifacts/audits/`, a następnie importuj
ją tym samym walidatorem. Brief nie może zostać zmieniony między sesją a
importem. Ponowne `audit_task.ps1` odtwarza go deterministycznie przy tych
samych danych; opcjonalnie wywołaj runner bez ponownego budowania pakietu:

```powershell
D:/game_predicotr/.venv/Scripts/python.exe scripts/run_claude_audit.py `
  --repo . --task TASK-1163 --brief artifacts/audits/TASK-1163_BRIEF_claude.md `
  --model claude-opus-5-5 --effort high --transport-attempt 2 `
  --import-report artifacts/audits/TASK-1163_DESKTOP.md `
  --payload-sha '<SHA256-briefu>' --observed-model claude-opus-5-5 `
  --observed-effort high --session-ref '<zaobserwowana-sesja>'
```

Próba 2 jest właściwa, jeżeli próba 1 tego samego pakietu nie dała wyniku.
Dla pierwszego transportu użyj domyślnej próby 1. Alternatywą są parametry
PS `-ImportReport`, `-PayloadSha`, `-ObservedModel`, `-ObservedEffort`,
`-SessionRef` i `-TransportAttempt`. Import nie uruchamia CLI i wymaga SHA w
samym raporcie oraz metadanych. Odczyt UTF-8 obsługuje BOM z PowerShell.
Parametry i raport przechodzą preflight przed zapisaniem nowej próby;
błędny SHA/model/sesja, nieczytelny plik lub niepoprawny raport nie zużywają
numeru transportu. Receipt oznacza dowód jako
`operator-ui-observation`, a effort jako obserwację UI. Nie jest to
kryptograficzne potwierdzenie wykonania backendu; nie przyjmuj własnej
opinii wykonawcy jako niezależnego raportu audytora.
