---
title: Protokół pomiaru pilota narzędzi tokenowych
status: active
last_updated: 2026-10-09
---

# Protokół pomiaru: narzędzia oszczędzania tokenów (TASK-0939)

Protokół przygotowany przez TASK-0939; **przebiegi wykonuje operator** w
niezależnych, świeżych sesjach (agent wykonujący task nie może ich uruchomić ani
odczytać cudzych raportów zużycia). Wynik trafia do
`ai_docs/quality/TOKEN_TOOLING_PILOT_<data>.md` (tabela z sekcji 8 + decyzje).

Zasada: narzędzie wchodzi do stałego użytku (`AGENTS.md`) tylko po werdykcie
„zostaje”. Dane producentów (Graphify „71,5×”, Serena „znacznie”) są
nieweryfikowane; liczy się pomiar na tym repozytorium.

## 1. Koszt i zgoda

36 sesji (6 wariantów × 3 zadania × 2 przebiegi) to zużycie, którego nie da się
wiarygodnie oszacować z góry. Zgodnie z `AGENTS.md` („Budżet tokenów i zgoda na
kosztowne prace”) najpierw wykonaj kalibrację: jeden przebieg zadania A w wariancie
`baseline`, odczytaj zużycie (sekcja 6) i dopiero z tej liczby oszacuj całość.
Przerwanie po kalibracji jest dopuszczalne.

## 2. Warunki stałe

- **Commit bazowy:** `f150b06c` (HEAD gałęzi `feat/mumie-super-game-plan` tuż
  przed TASK-0939). Wszystkie warianty startują z tego commita; zmienia się
  wyłącznie zestaw plików narzędzia (sekcja 3). Zapisz hash w raporcie.
- **Model i poziom rozumowania:** ten sam we wszystkich sesjach, zalecany
  `claude-sonnet-5-5` / `high` (ustaw `/model` i `/effort`, zapisz w raporcie).
  Subagenci dziedziczą ustawienia; nie zmieniaj ich w trakcie pilota.
- **Świeża sesja na przebieg:** nowy proces `claude`, brak `--continue`/`--resume`,
  pusty kontekst, osobny worktree na przebieg (usuwany po pomiarze).
- **MCP dokładnie wg wariantu:** `claude --strict-mcp-config --mcp-config <plik>`;
  plik `{"mcpServers":{}}` dla wszystkich wariantów poza Serena. Wyłącz pozostałe
  serwery MCP, wtyczki i skille spoza repozytorium (ich definicje zawyżałyby koszt
  stały jednakowo, ale zaciemniają różnice).
- **Kolejność przebiegów:** przeplataj warianty (A-baseline, A-serena, …), nie
  uruchamiaj wszystkich przebiegów jednego wariantu pod rząd; cache promptu z
  poprzedniej sesji mógłby zafałszować odczyt cache.
- **Zakazy:** brak commitów, serwerów, migracji, benchmarków i testów poza
  wskazanymi w zadaniu; operatorskie PostgreSQL i usługi nie są używane
  (zadanie B uruchamia wyłącznie testy bez bazy).
- **Limit:** przebieg przerwij po 45 minutach albo 400 tys. tokenów wyjścia i
  oznacz jakość jako `FAIL` (powód w notatce).

## 3. Warianty

`<PILOT>` to commit dostarczający narzędzia pilota, czyli commit TASK-0939 w
wersji `v1.7.284` (hash zapisuje lead w sekcji taska po commicie; zapisz go w
raporcie). Commit zamykający task powstaje dopiero po raporcie z pomiaru, więc nie
jest używany do przygotowania wariantów.

Każdy wariant to osobny worktree z commita bazowego. Kroki 1–4 wykonaj dla każdego
worktree osobno (nic nie jest współdzielone przez `.tooling` głównego checkoutu):

```powershell
# katalog głównego checkoutu, timeout 120 s; <V> = wariant, <N> = numer przebiegu
# 1. worktree z commita bazowego
git worktree add worktrees\pilot-<V>-<N> f150b06c --detach
# 2. dowiązanie do .venv głównego checkoutu (zadanie B i hook używają jego Pythona)
cmd /c mklink /J worktrees\pilot-<V>-<N>\.venv .venv
# 3. pliki narzędzia z <PILOT> (wg tabeli poniżej)
git -C worktrees\pilot-<V>-<N> checkout <PILOT> -- <pliki z tabeli>
```

4. Tylko warianty `serena` i `graphify`: przygotuj izolowane narzędzia w tym worktree
   (timeout instalacji 600 s, indeks około 50 s, graf około 80 s):

```powershell
cd worktrees\pilot-<V>-<N>
New-Item -ItemType Directory -Force artifacts | Out-Null
python -m venv .tooling\venv-tokens
.\.tooling\venv-tokens\Scripts\python.exe -m pip install serena-agent==1.7.0 graphifyy==0.9.82 uv==0.12.24
# serena: indeks wstępny; log zawiera zainstalowane wersje (zachowaj go do raportu)
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_serena_mcp.ps1 -Index *>&1 | Out-File artifacts\serena-index.log -Encoding utf8
# graphify: graf samego kodu (polecenia z ai_docs/guides/TOKEN_TOOLING.md, sekcja 4)
```

**Kontrola dostępności przed każdą sesją** (przerwij, gdy którykolwiek punkt nie
przechodzi; nie uruchamiaj sesji „na pół”):

```powershell
# w worktree przebiegu
Test-Path .venv\Scripts\python.exe                                   # wszystkie warianty: True
Test-Path .tooling\venv-tokens\Scripts\serena.exe                    # serena: True
Select-String -Path artifacts\serena-index.log -Pattern 'serena-agent==1.7.0','Indexed files per language'   # serena: 2 trafienia
Test-Path artifacts\graphify\api-src\graphify-out\graph.json         # graphify: True
Test-Path .claude\settings.json                                      # hook: True; pozostałe warianty: False
Test-Path ai_docs\architecture\CODE_MAP.md                           # codemap: True; pozostałe warianty: False
```

Po kontroli nałóż podpowiedź do promptu zgodnie z tabelą:

| Wariant | Pliki nałożone na commit bazowy | Dodatek do promptu | MCP |
|---|---|---|---|
| `baseline` | brak | brak | puste |
| `codemap` | `pliki z <PILOT>: ai_docs/architecture/CODE_MAP.md ai_docs/architecture/CODE_MAP_SYMBOLS.md scripts/generate_code_map.py` | „Mapa kodu: `ai_docs/architecture/CODE_MAP.md` (indeks do `rg`: `CODE_MAP_SYMBOLS.md`). Zacznij od niej.” | puste |
| `serena` | `pliki z <PILOT>: .serena scripts/start_serena_mcp.ps1 .gitignore`; krok 4 (venv, indeks) | „Masz narzędzia Serena (`find_symbol`, `find_referencing_symbols`, `get_symbols_overview`); preferuj je zamiast czytania całych plików.” | Serena (`start_serena_mcp.ps1` z worktree) |
| `graphify` | krok 4 (venv, graf `services/api/src` wg `ai_docs/guides/TOKEN_TOOLING.md`, sekcja 4); plik `scripts/start_serena_mcp.ps1` niepotrzebny | „Graf kodu: `artifacts/graphify/api-src/graphify-out/graph.json`; zapytania: `.tooling\venv-tokens\Scripts\graphify.exe query \"...\" --graph <graph.json> --context call`.” | puste |
| `hook` | `pliki z <PILOT>: .claude/settings.json scripts/hooks` | brak | puste |
| `rules` | `pliki z <PILOT>: AGENTS.md`, potem usuń z `AGENTS.md` akapit poprzedzony komentarzem `<!-- [mapa kodu] -->` | brak | puste |

W wariancie `graphify` graf obejmuje tylko `services/api/src`, więc zadanie A (Admin) nie może na nim w pełni polegać; to ograniczenie narzędzia jest częścią wyniku, nie błędem protokołu.

Brak łączenia wariantów w pilocie. W wariantach `graphify` i `serena` model dostaje
tylko wskazaną podpowiedź; w pozostałych nie wolno dopisywać nic ponad prompt
zadania.

## 4. Zadania pomiarowe (prompty)

Treść promptu jest identyczna we wszystkich wariantach (poza „dodatkiem” z
sekcji 3, doklejanym na końcu). Odpowiedź końcowa agenta jest oceniana wg klucza.

### Zadanie A: lokalizacja miejsca zmiany w Adminie (tylko odczyt)

> W Adminie (`apps/admin`) znajdź, gdzie obsługiwany jest zapis super symbolu
> serii supergry. Wskaż: (1) komponent i funkcję w UI, która wywołuje zapis,
> (2) metodę wrappera klienta API, (3) endpoint HTTP w API (metoda i ścieżka)
> oraz (4) metodę warstwy `application`, która go wykonuje. Nie zmieniaj kodu i
> nie uruchamiaj testów. Odpowiedz czterema pozycjami `plik:linia` i jednym
> zdaniem o przepływie.

Klucz: (1) `apps/admin/src/features/super-games/super-game-series-workspace.tsx`
(handler zapisu wywołujący `setSuperGameSeriesSuperSymbol`; pomocnicze
`beginSuperSymbolSave` w `super-game-series-state.ts`); (2)
`packages/admin-api-client/src/index.ts`, `setSuperGameSeriesSuperSymbol`; (3)
`PUT /{game_id}/super-game-series/{series_id}/super-symbol`,
`services/api/src/game_predictor_api/api/super_game_series.py`, `set_super_symbol`;
(4) `SuperGameSeriesService.set_super_symbol` w
`services/api/src/game_predictor_api/application/super_game_series.py`.

### Zadanie B: zmiana domeny w API z testem

> W API (`services/api`) kursor listy serii supergry (`_parse_cursor` w
> `application/super_game_series.py`) przyjmuje dziś każdy ciąg cyfr do 9 znaków.
> Zmień walidację tak, aby kursor w postaci niekanonicznej, czyli z wiodącymi
> zerami (np. `007`), był odrzucany błędem `SUPER_GAME_SERIES_CURSOR_INVALID`;
> kursor `0` pozostaje dozwolony. Dodaj test w istniejącym pliku testów serii
> supergier w `services/api/tests` i uruchom ten plik testów oraz `ruff check` i
> `mypy --strict` dla zmienionych plików. Nie commituj. W odpowiedzi podaj listę
> zmienionych plików i wynik poleceń.

Klucz: zmiana wyłącznie w `_parse_cursor` (warunek kanoniczności) i jeden nowy
przypadek testowy (np. w `services/api/tests/test_super_game_series_api.py`,
obok `test_service_rejects_bad_cursor_and_limit`); żadnych innych plików poza
testem i funkcją.

### Zadanie C: analiza błędu w workerze (tylko odczyt)

> Operator zgłasza, że job typu `SUPER_GAME_SERIES_DERIVE` kończy z
> `JOB_HANDLER_NOT_REGISTERED` albo nie jest podejmowany przez worker lane
> `image-selection`. Ustal na podstawie kodu (`services/worker`): (1) gdzie i
> jak buduje się mapę handlerów dla danej lane, (2) jak `claim_next` wybiera typy
> jobów do podjęcia, (3) w którym miejscu ustawiany jest błąd
> `JOB_HANDLER_NOT_REGISTERED` i czy da się go osiągnąć przy tej konfiguracji,
> (4) który zbiór typów jobów obsługuje lane `general`. Nie zmieniaj kodu i nie
> uruchamiaj testów. Odpowiedz czterema pozycjami `plik:funkcja` i krótkim
> wnioskiem o przyczynie.

Klucz: (1) `services/worker/src/game_predictor_worker/cli.py` (słownik
`handlers` z `JobType.SUPER_GAME_SERIES_DERIVE: SuperGameSeriesDeriveHandler(...)`,
wybór według `options.lane`); (2) `jobs/store.py` `claim_next` z filtrem
`allowed_job_types`, przekazywanym przez `LocalJobWorker.run_once` jako
`frozenset(self._handlers)` w `jobs/runtime.py`; (3) `jobs/runtime.py`
`run_once` (gałąź `handler is None`), z zaznaczeniem, że przy filtrze według kluczy
handlerów jest to gałąź obronna; (4) `GENERAL_JOB_TYPES` w `jobs/store.py`
(oraz zdublowana definicja w `jobs/runtime.py`).

## 5. Rubryka jakości (stała, przed uruchomieniem przebiegów)

Ocena binarna `PASS`/`FAIL` na zadanie i przebieg; oceniający nie zna wariantu
(zasłoń nazwę worktree i listę narzędzi).

| Zadanie | `PASS` wymaga |
|---|---|
| A | wszystkie 4 pozycje wskazują właściwy plik i symbol z klucza; ścieżki istnieją; brak zmian w repozytorium; opis przepływu zgodny z kodem |
| B | zmiana zgodna z kluczem (tylko `_parse_cursor` + test); test odtwarza przypadek `007` i `0`; docelowy plik testów zielony, `ruff check` i `mypy --strict` zielone na zmienionych plikach; brak innych zmian (`git status`); audyt drugiej rodziny modeli (Codex albo `claude-opus-5-5` jako zastępca) = PASS na samym diffie |
| C | pozycje (1)–(4) zgodne z kluczem; wniosek poprawnie odróżnia gałąź obronną od faktycznej przyczyny; brak zmian w repozytorium |

Wynik gorszy od bazy dyskwalifikuje wariant niezależnie od tokenów (`quality`
inne niż `PASS` w którymkolwiek przebiegu tego wariantu i zadania).

## 6. Metryka i zbieranie danych

Metryka kosztu: **suma tokenów wszystkich wywołań** sesji, czyli agent główny +
subagenci + wywołania narzędzi modelowych, z rozbiciem na: wejście (bez cache),
wyjście, zapis cache, odczyt cache; kolumna `total` to suma czterech, kolumna
`ekw.` to tokeny ważone cenowo (1 / 1,25 / 0,1 / 5; przybliżenie proporcji cen).
Koszt stały definicji narzędzi MCP i reguł z `AGENTS.md` jest już w tych liczbach
(wchodzi do prefiksu cache), więc nie dodawaj go osobno.

Źródło danych (zweryfikowane): transkrypt sesji Claude Code
`%USERPROFILE%\.claude\projects\<slug projektu>\<session-id>.jsonl` — każda linia
`assistant` ma `message.id` i `message.usage` (`input_tokens`, `output_tokens`,
`cache_creation_input_tokens`, `cache_read_input_tokens`); wywołania subagentów
leżą w `<session-id>\subagents\agent-*.jsonl`. Skrypt
`scripts/token_pilot_collect.py` deduplikuje wielokrotne linie jednej wiadomości,
sumuje sesję z subagentami i renderuje tabelę. Slug projektu dla worktree
`worktrees\pilot-...` to jego ścieżka z `-` zamiast separatorów; `session-id`
odczytasz z nazwy najnowszego pliku w tym katalogu. Gdyby transkrypt był
niedostępny, wpisz wartości ręcznie do CSV (te same kolumny) — `render` działa
na samym CSV.

```powershell
# katalog repozytorium, timeout 120 s
.\.venv\Scripts\python.exe scripts/token_pilot_collect.py usage --session-id <session-id>
```

Manifest `sessions.csv` (kolumny `variant,task,run,session_id,quality,notes`; wiersz
z `task=indexing` opisuje jednorazowy koszt indeksowania wariantu):

```csv
variant,task,run,session_id,quality,notes
baseline,A,1,00000000-0000-0000-0000-000000000000,PASS,
serena,A,1,11111111-1111-1111-1111-111111111111,PASS,
```

```powershell
.\.venv\Scripts\python.exe scripts/token_pilot_collect.py collect --manifest sessions.csv --out results.csv
.\.venv\Scripts\python.exe scripts/token_pilot_collect.py render --results results.csv --out artifacts\token-pilot-table.md
```

**Koszt jednorazowy** raportuj osobno i amortyzuj na założoną liczbę sesji
(zapisz założenie, np. 100): Serena — czas 47 s zimnego indeksu (12 s
odświeżenia), 160 MB cache; Graphify — 45 s + 12 s + 22 s budowy dla
`services/api/src`, 70 MB; oba bez tokenów modelu. Jeżeli indeksowanie wymaga
sesji modelowej, dopisz ją jako wiersz `task=indexing`. Amortyzowany koszt =
koszt jednorazowy / liczba sesji, doliczany do średniej wariantu.

## 7. Reguła decyzyjna

Narzędzie `zostaje`, gdy jednocześnie: (a) `quality = PASS` we wszystkich
przebiegach wszystkich trzech zadań, (b) średnia kolumny `ekw.` jest niższa od
bazy o co najmniej 15% uśredniona po zadaniach, (c) w żadnym zadaniu średnia nie
jest gorsza od bazy o więcej niż 5%, (d) po uwzględnieniu amortyzowanego kosztu
jednorazowego nadal jest zysk. W przeciwnym razie `wypada`. Gdy dwa przebiegi tego
samego wariantu i zadania różnią się o więcej niż 30% w `total`, wykonaj trzeci
przebieg i oznacz rozrzut w raporcie. Do `AGENTS.md` wchodzi wyłącznie narzędzie ze
statusem `zostaje`; hook i mapa kodu, jeśli wypadną, są usuwane w osobnym tasku.

## 8. Szablon tabeli wyników

Skrypt `render` generuje tabele „Przebiegi”, „Średnie i różnica względem bazy” oraz
koszt indeksowania. Raport pilota dopełnij decyzjami:

| Wariant | Zadanie A (Δ ekw.) | Zadanie B (Δ ekw.) | Zadanie C (Δ ekw.) | Jakość | Koszt jednorazowy | Decyzja |
|---|---:|---:|---:|---|---|---|
| `codemap` | | | | | | zostaje / wypada |
| `serena` | | | | | | zostaje / wypada |
| `graphify` | | | | | | zostaje / wypada |
| `hook` | | | | | | zostaje / wypada |
| `rules` | | | | | | zostaje / wypada |

Oraz: commit bazowy i pilota, model i poziom rozumowania, data, wersje narzędzi
(`serena-agent` 1.7.0, `graphifyy` 0.9.82), odchylenia od protokołu.
