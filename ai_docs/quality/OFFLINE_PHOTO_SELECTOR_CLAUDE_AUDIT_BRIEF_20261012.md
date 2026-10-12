---
title: Brief pełnego audytu selektora Windows dla Claude Code
status: ready_for_review
last_updated: 2026-10-12
---

# Zlecenie audytu dla Claude Code — lokalny selektor zdjęć Windows

## Polecenie operatora

Wykonaj niezależny audyt całego lokalnego selektora: pierwotnej implementacji,
poprawek po raporcie REVISE i ostatniego uproszczenia startu oraz wznowienia.
Sprawdź zgodność kodu, testów, dokumentacji i finalnej paczki 0.1.2. Szczególnie
oceń ochronę zapisanej pracy i wygodę użytkownika, który wybiera tylko folder
zdjęć. Nie ograniczaj audytu do ostatniego commita ani do deklaracji wykonawcy.

Nie implementuj poprawek. Nie zmieniaj źródeł, testów, zależności, tasków,
wcześniejszego raportu ani paczek. Możesz zapisać tylko nowy raport audytu
oraz pomocnicze logi i własne, odizolowane fixture'y kontroli. Nie wykonuj
commitów, push, merge, instalacji zależności ani uruchamiania usług API/Admin/
Reviewera/workera głównej aplikacji. Nie używaj zdjęć ani projektów operatora.
Nie wyłączaj ochrony Windows.

Raport zapisz w:
`ai_docs/quality/OFFLINE_PHOTO_SELECTOR_REAUDIT_CLAUDE_20261012.md`.
Jeśli taki raport już istnieje, zachowaj go i wybierz osobną nazwę z numerem
rundy. Podaj faktyczny model Claude i zakres sprawdzonych rewizji.

## Repozytorium i zamrożony zakres

- Worktree: `D:\game_predicotr\worktrees\offline-photo-selector`.
- Gałąź: `codex/offline-photo-selector`.
- Baza całej implementacji: `bb883b5902cb0934b9732d1bc24361d01085051d`
  (v1.7.316).
- Koniec implementacji i jej dowodów: `21d8c02336d23cd62f21d329d9e4da92577e9564`
  (v1.7.330).
- Kod finalnego ZIP-a: `c4181f7ddc8fca2518c2d9abc363ce3bcd307d5f`
  (v1.7.329). v1.7.330 zawiera dokumentację wyników.
- Baza poprawek po REVISE: `d21f9f3ed6c5739f8fce7fac128cc59a8094330b`
  (v1.7.323).
- Baza nowego startu i historii: `c32fa802597ecaeb3d9ad0b4d15466a730e6bb70`
  (v1.7.327).

Najpierw sprawdź branch, historię i stan worktree. Późniejszy commit z tym
briefem jest oczekiwaną zmianą dokumentacyjną. Sprawdź różnicę od v1.7.330;
jeżeli zmienił się również kod, wskaż to w raporcie i rozdziel rewizję kodu od
rewizji paczki. Nie nadpisuj zastanych zmian. Pracuj w tym worktree, nie w
głównym checkout `D:\game_predicotr`.

## Dokumenty wejściowe i taski

Przestrzegaj `AGENTS.md` i jego kolejności odczytu. W CURRENT_STATE czytaj
ograniczenia selektora, aktywny TASK-0979 i ostatnie dziesięć sekcji done.
W DECISION_LOG sprawdź przede wszystkim D-545 wraz z późniejszymi zgodami
operatora. Nie kopiuj całych dokumentów procesu ani archiwów do promptów.

Źródła zakresu:

1. [Wymagania](../requirements/MANUAL_IMAGE_SELECTION.md), sekcja
   „Lokalny selektor Windows — D-545, zaakceptowany zakres”.
2. [Architektura](../architecture/MANUAL_IMAGE_SELECTION.md), sekcja
   „Lokalny selektor Windows — D-545, zaakceptowana architektura”.
3. [Pierwotny plan](../delivery/OFFLINE_PHOTO_SELECTOR_EXECUTION_PLAN.md),
   sekcje akceptacji, decyzji, pięciu tasków i odbioru.
4. [Plan poprawek](../delivery/OFFLINE_PHOTO_SELECTOR_AUDIT_REMEDIATION_PLAN_20261012.md),
   sekcje „Reguły i decyzje”, „Taski i kolejność”, „Weryfikacja i granice”.
5. [Plan prostego startu](../delivery/OFFLINE_PHOTO_SELECTOR_START_PLAN_20261012.md),
   sekcje „Zakres i rozstrzygnięcia” oraz „Weryfikacja i odbiór”.
6. [Instrukcja operatora](../guides/OFFLINE_PHOTO_SELECTOR_OPERATOR.md),
   [traceability](../project/TRACEABILITY.md) i
   [rejestr odbioru](OFFLINE_PHOTO_SELECTOR_ACCEPTANCE.md).

Przeczytaj poniższe taski, zwłaszcza Scope, Acceptance criteria, Definition
of Done i Outcome. Ukończone taski są tu jawnie wskazanym materiałem audytu.

| Task | Plik | Obszar |
|---|---|---|
| 0975 | [Fundament](../tasks/completed/0975-selector-desktop-foundation.md) | Electron, pakowanie, IPC i bezpieczny dostęp do zdjęć |
| 0976 | [Trwałość](../tasks/completed/0976-selector-desktop-durability.md) | Projekt, manifest, journal, blokady i odzyskiwanie |
| 0977 | [Interfejs](../tasks/completed/0977-selector-desktop-selection-ui.md) | Selekcja, numeracja, skróty, undo i restart |
| 0979 | [Odbiór wydania](../tasks/0979-selector-desktop-release-acceptance.md) | Paczka i osobna, nadal otwarta bramka odbiorcy |
| 0978 | [Stare sesje](../tasks/completed/0978-selector-desktop-legacy-adoption.md) | Walidowane przejęcie v1/v2 bez zmiany oryginału |
| 0980 | [Kontrole natywne](../tasks/completed/0980-selector-desktop-native-checks-and-recovery.md) | Worker, skany, lock i zgodność pominięć |
| 0981 | [Obsługa błędów](../tasks/completed/0981-selector-desktop-audit-ux.md) | Zamknięcie, debounce i komunikaty |
| 0982 | [Poprawiony pilot](../tasks/completed/0982-selector-desktop-remediated-pilot.md) | Paczka 0.1.1 i aktualizacja |
| 0983 | [Start i historia](../tasks/completed/0983-selector-desktop-source-first-start.md) | Jeden folder, nazwa gry, historia, automatyczne wznowienie i 0.1.2 |

TASK-0978 został później wyraźnie uruchomiony przez operatora. Nie traktuj
historycznego odroczenia jako obecnego zakazu jego implementacji. Audyt
operatora został przeniesiony na koniec prac; nie oceniaj wcześniejszych
commitów jako nieautoryzowanych tylko z powodu braku audytu przed każdym.

[Przekazanie implementacji](OFFLINE_PHOTO_SELECTOR_IMPLEMENTATION_HANDOFF.md),
[dowody poprawek](OFFLINE_PHOTO_SELECTOR_AUDIT_REMEDIATION_20261012.md) i
[dowody startu](OFFLINE_PHOTO_SELECTOR_START_VERIFICATION_20261012.md) są
raportami wykonawcy. Są wskazówkami, a nie niezależnym dowodem PASS.
Oryginalny [audyt Claude REVISE](OFFLINE_PHOTO_SELECTOR_IMPLEMENTATION_AUDIT_CLAUDE_20261012.md)
pozostaje niezmieniony.

## Mapa przeglądu kodu

Zacznij od sekcji selektora w `ai_docs/architecture/CODE_MAP.md`, następnie
szukaj symboli w `CODE_MAP_SYMBOLS.md` i czytaj konkretne moduły fragmentami.

- `apps/selector-desktop/src/main.ts`, `preload.ts`, `contracts.ts`:
  granica renderer/native, protokoły, dialogi i zamknięcie.
- `src/native/`: koordynator projektu, źródła, kontrola ścieżek, worker
  Windows, historia widoku i diagnostyka.
- `src/project/`, `src/filesystem/`, `src/manifest/`:
  stan, decyzje, journal, recovery, blokady i własność plików.
- `src/legacy-adoption/`: dowody zgodności i przejęcie starej sesji.
- `src/renderer/`: formularz, historia, skróty i podgląd.
- `apps/selector-desktop/test/`, `scripts/`, `forge.config.cjs`, manifest
  workspace'u i root lockfile: rzeczywiste pokrycie oraz zawartość wydania.

Porównuj reguły z `packages/manual-image-selection-core/src/index.ts` oraz
kontraktem `apps/reviewer/src/features/manual-selection/operator-local-selection-output.ts`.
Punktem odniesienia zachowania jest
`apps/reviewer/src/features/manual-selection/remote-manual-selection-workspace.tsx`.
Desktop ma własny interfejs. Nie przenoś automatycznie odmiennych reguł
browserowego Admina, kolejki treningowej ani trace do tego wydania.

## Kryteria pełnego audytu

### Start, foldery i wygoda pracy

- Pierwszy krok wymaga tylko folderu zdjęć. Dla `D:\Mumie\123` projekt
  powstaje w `D:\Mumie\123 selekcja`, wynik w `D:\Mumie\123 wybrane`.
  Oba są obok źródła. Użytkownik nie wybiera ich osobno.
- Nazwa gry, np. „Mumie”, tworzy etykietę „Mumie — 123”. Nie zmienia nazw
  katalogów ani nie staje się backendowym gameId. Formularz pokazuje pełne
  ścieżki i jasno rozróżnia źródło, projekt oraz wynik.
- Ponowny wybór tego źródła otwiera istniejący projekt bez nowej konfiguracji.
  Wracają decyzje, zdjęcie i kierunek numeracji. Historia ma do dziesięciu
  wpisów, czytelne etykiety i jawne uruchomienie wybranego projektu.
- Sprawdź wznowienie bez cache, starego projektu bez gameName, projektu
  otwartego ręcznie oraz przeniesionego źródła po relink i restarcie procesu.
- Cache nie jest dowodem własności. Sprawdź niejednoznaczne projekty,
  obcy/uszkodzony katalog, niezgodne sourceRoot/projectId i zły journal.
  Weryfikacja tożsamości pod lockiem musi nastąpić przed recovery.
- Anulowanie pickera zachowuje pracę i rozpoczęty formularz. Podwójne
  kliknięcie lub ponowienie create nie tworzy drugiego projektu. Renderer
  używa opaque sourceToken, a nie dowolnej ścieżki do zapisu.
- Oceń etykiety, kolejność działań, stany oczekiwania/błędu i obsługę
  klawiatury. Wskaż konkretny problem utrudniający pracę, bez przebudowy UI
  wynikającej wyłącznie z preferencji stylistycznych.

### Rosnące i malejące pozycje

- Kierunek numeracji nie odwraca naturalnej listy zdjęć. Sprawdź oba kierunki
  po zamknięciu procesu, wyborze źródła i wyborze z historii.
- Zakres pochodzi z `rangeForStart`: dziewięć plansz, krótszy tylko przy
  końcowej granicy. Nie dopuszczaj dowolnych zakresów długości 1–9.
- Sprawdź Enter/F i przejście zdjęcia, Tab z pozostawieniem zdjęcia,
  skoki 1–10/15/20, zmianę zakresu, undo, granicę sesji i otwarcie po undo.
- Pominięty zakres można później wypełnić. Kolizja z zaakceptowanym zakresem
  oraz ponowna akceptacja tego samego źródła nadal muszą blokować zapis.
- Repeat klawisza, podwójny submit i oczekujący zapis nie mogą dublować
  decyzji. Licznik wyborów zmienia się dopiero po trwałym zatwierdzeniu.
- Zoom 100–3000%, fullscreen, scroll w obu osiach i podglądy ±3 działają
  bez narastającej kolejki zapisu widoku. Sprawdź flush przed wyjściem.

### Trwałość, własność i odzyskiwanie

- Projekt jest źródłem prawdy, manifest operator-local v2 jego projekcją.
  Nazwa manifestu to `manual-image-selection-output-v1.json`; nie wolno
  zapisać pod nią odmiennego rdzeniowego formatu `items`.
- JPEG-i zachowują oryginalne bajty i nazwy `seq_<start>-<end>.jpg`.
  Źródło pozostaje tylko do odczytu. Undo/restart mogą usuwać wyłącznie
  udowodnione własne wyniki; restart wymaga preview i potwierdzenia.
- Oceń intent przed zmianą JPEG-a, fazy journalu, backup, temp/sync/replace,
  awarie każdej fazy, utratę odpowiedzi i retry tego samego operationId.
  Potwierdzona decyzja nie może zniknąć ani pojawić się podwójnie.
- Recovery kończy się przed nową mutacją. Sprawdź ENOSPC, rename failure,
  uszkodzony stan, niezgodny manifest, brak folderu oraz złą checksumę.
- Lock powstaje atomowo. Heartbeat nie wystarcza do przejęcia; oceń host,
  PID i tożsamość procesu, drugą instancję oraz output lease dwóch projektów.
- LOCK_LOST blokuje zapis, lecz pozwala zamknąć program. Zamknięcie nie
  usuwa obcej blokady. Brak folderu nigdy nie resetuje projektu.
- Brak własnego JPEG-a ma jasną diagnostykę i opisaną drogę przywrócenia
  zgodnej kopii oraz wznowienia. Automatyczny repair ze źródła nie jest
  częścią zaakceptowanego zakresu. Obce pliki pozostają chronione.

### Bezpieczeństwo i koszt operacji

- Sprawdź sandbox, contextIsolation, brak nodeIntegration, CSP, blokadę
  sieci, zewnętrznej nawigacji i nowych okien oraz walidację nadawcy IPC.
- Opaque ID obrazu nie może pozwolić na dowolny odczyt. Protokół strumieniuje
  JPEG-i bez base64 całej kolekcji. Sprawdź traversal, ADS, junction/reparse
  pointy, katalogi nadrzędne i zmianę ścieżki między sprawdzeniem a użyciem.
- Worker Windows wykonuje świeże kontrole, nie zastępuje ich starym cache.
  Oceń typowane JSONL, limity kolejki, timeout, awarię procesu i zamknięcie.
  Normalny krok nie powinien tworzyć nowych procesów PowerShell.
- Otwieranie używa pojedynczego zweryfikowanego skanu źródła. Pełne SHA
  wyników i koszt pełnego stanu/historii pozostają jawnym ograniczeniem.
  Oceń, czy pozostawiony koszt nadal narusza cel użytkowy z P1-1.
- Debounce widoku nie może zgubić ostatniego widoku ani wstrzymywać decyzji.
  Mały fixture nie dowodzi wydajności dla 15 000 JPEG-ów. Nie uruchamiaj
  benchmarku ani dużych sztucznych kolekcji bez osobnego zlecenia operatora.

### Stare sesje, aktualizacja i paczka

- Przejęcie v1/v2 wymaga zgodnej tożsamości źródła i sum wyników, preview
  oraz jawnego utworzenia nowego projektu/wyniku. Oryginał pozostaje
  niezmieniony. Brak dowodów, sprzeczne dane i nieobsługiwana historia
  kończą się odmową, a nie cichą naprawą.
- Sprawdź wieloplikowy journal v2 i recovery wcześniejszego journal v1,
  zachowanie generacji, anulowanie/token oraz wznowienie po nowym procesie.
- Sprawdź rzeczywistą aktualizację ZIP 0.1.0 → 0.1.2 na własnej kopii projektu:
  decyzje, zapisany relativePath, kierunek i checksumy muszą przetrwać.
  Opaque image ID może zmieniać się po otwarciu; porównuj ścieżkę i ordinal.
- Zweryfikuj SHA ZIP-a i app.asar, build-info, sourceCommit, flagi dirty,
  zawartość asar oraz brak źródeł monorepo i niepotrzebnych zależności runtime.
- Root workspace/lockfile uwzględnia pobieranie Electron i wyłącznie niezbędne
  install scripts. Brak globalnego wyłączenia kontroli i ELECTRON_MIRROR.
- Nie ma uploadu, generowania linków, synchronizacji ani integracji Proton
  Drive. Nie ma zmian komponentów Admina/Reviewera, API, OpenAPI i bazy.

## Każde ustalenie poprzedniego REVISE wymaga osobnej odpowiedzi

Poniższa tabela opisuje deklaracje wykonawcy do sprawdzenia, nie zamknięcie uwag.
Zachowaj identyfikatory starego raportu nawet wtedy, gdy nowa ocena ważności
będzie inna. Osobno wypisz nowe znaleziska.

| Ustalenie | Co ocenić w obecnym kodzie |
|---|---|
| P1-1: 1,7–2,6 s na interakcję | Worker usuwa starty procesów; retencja receiptów i pełny journal nadal rosną. Oceń obie przyczyny, nie tylko worker. |
| P2-1: brak wyjścia po LOCK_LOST | Zamknięcie rzeczywistego okna, ostatni zapis widoku, log i brak unlink obcego locka. |
| P2-2: brak seq JPEG | Stop nowych decyzji, dobra/zła kopia, jawne wznowienie i użyteczna instrukcja. Brak automatycznego repair jest granicą zakresu. |
| P2-3: skipped range | Powrót do pominiętego zakresu działa; accepted overlap i duplikat źródła nadal blokują. |
| P2-4: koszt open | Jeden scan zamiast dwóch; pełne SHA wyników pozostają. Oceń prawdziwość opisanych ograniczeń. |
| P3-1: recovery guard | Nieznany właściciel nadal blokuje; brak heartbeat-only takeover. Diagnostyka ma wyjaśniać blokadę. |
| P3-2: scroll | Debounce 250 ms, flush i brak zaległych zapisów przed accept/close. |
| P3-3: USB | USB pozostaje poza pilotem; właściwy kod REMOVABLE_STORAGE i komunikat. |
| P3-4: pickSource | Martwy kanał usunięty; nowe begin/picker nie kasuje aktywnej pracy przy anulowaniu. |
| P3-5: drobne | Komunikat NAV nie udaje akceptacji; nowe commity mają TASK ID. Oceń również uwagi o esbuild, retry UI i obcych plikach wynikowych. |

## Tożsamość finalnej paczki

Ścieżki poniżej są względne wobec wskazanego worktree:

- Finalny ZIP: `apps/selector-desktop/out/releases/pilot-0.1.2-c4181f7d/Selektor zdjec-win32-x64-0.1.2.zip`.
- Obok są `.zip.sha256` i `.zip.release.json`.
- Rozmiar: **149402003 bajtów**; Windows 11 x64, wersja **0.1.2**.
- ZIP SHA-256: `9426704949dd8ab7d16f9d9743e2254257805a8ed1cc5dce38eecd2c37442e27`.
- app.asar SHA-256: `0e2c2bf2894bd519ceea96e957e564dbe02f54d0963f3d381085396815c323c0`.
- sourceCommit: `c4181f7ddc8fca2518c2d9abc363ce3bcd307d5f`.
- dirty=false; applicationSourceDirty=false.
- Historyczny ZIP aktualizacji: `apps/selector-desktop/out/releases/pilot-0.1.0-abe8e645/Selektor zdjec-win32-x64-0.1.0.zip`;
  SHA-256 `2dcfe275cd7af44519c126272ad7df0e3354faed74366663ad7126480da21bea`.

ZIP `pilot-0.1.2-9ade6a85` jest historyczny, sprzed poprawki historii po
relink. Nie używaj go jako finalnego. Nie przebudowuj wydania w celu audytu:
zmieniłoby to przedmiot kontroli. Artefakty ZIP są lokalne i ignorowane przez
Git; ich brak po samym klonowaniu repo nie dowodzi błędu implementacji.

## Kontrole z ograniczonym czasem

Najpierw wykonaj przegląd statyczny. Potem uruchom istniejące kontrole
selektora na własnych fixture'ach. Każdy krok ma oddzielny timeout i zapisany
wynik. Nie uruchamiaj głównego repozytoryjnego `quality` ani jego testów
API/bazy. Nie sumuj powtórzonych grup jako dodatkowych unikalnych testów.
Poniższe polecenia są instrukcją do wykonania, nie twierdzeniem o ich wyniku.

Konfiguracja PowerShell:

```powershell
Set-Location -LiteralPath 'D:\game_predicotr\worktrees\offline-photo-selector'
$selectorAuditNode = 'C:\Program Files\nodejs\node.exe'
$selectorAuditBounded = Join-Path (Get-Location) 'apps/selector-desktop/scripts/run-bounded.mjs'
$selectorAuditZip = Join-Path (Get-Location) 'apps/selector-desktop/out/releases/pilot-0.1.2-c4181f7d/Selektor zdjec-win32-x64-0.1.2.zip'
$selectorAuditOldZip = Join-Path (Get-Location) 'apps/selector-desktop/out/releases/pilot-0.1.0-abe8e645/Selektor zdjec-win32-x64-0.1.0.zip'
```

Historia i zakres (każde polecenie do 30 s):

```powershell
& $selectorAuditNode $selectorAuditBounded 30 git status --short
& $selectorAuditNode $selectorAuditBounded 30 git log -15 --oneline
& $selectorAuditNode $selectorAuditBounded 30 git diff --name-status 21d8c02336d23cd62f21d329d9e4da92577e9564 HEAD
& $selectorAuditNode $selectorAuditBounded 30 git diff --stat bb883b5902cb0934b9732d1bc24361d01085051d 21d8c02336d23cd62f21d329d9e4da92577e9564
& $selectorAuditNode $selectorAuditBounded 30 git diff bb883b5902cb0934b9732d1bc24361d01085051d 21d8c02336d23cd62f21d329d9e4da92577e9564 -- apps/selector-desktop package.json package-lock.json .prettierignore scripts/generate_code_map.py
```

Czytaj duży diff partiami i per moduł; nie wklejaj go w całości do kontekstu.
Nie pomijaj zmian dokumentacji wskazanych w sekcji źródeł. Kontrole kodu
(120 s na testy, po 60 s na lint i typecheck):

```powershell
& $selectorAuditNode $selectorAuditBounded 120 npm run test --workspace apps/selector-desktop
& $selectorAuditNode $selectorAuditBounded 60 npm run lint --workspace apps/selector-desktop
& $selectorAuditNode $selectorAuditBounded 60 npm run typecheck --workspace apps/selector-desktop
& $selectorAuditNode $selectorAuditBounded 60 npm run docs:check
& $selectorAuditNode $selectorAuditBounded 60 npm run code-map:check
& $selectorAuditNode $selectorAuditBounded 30 git diff --check
```

Zapisz wynik każdej komendy i kod wyjścia. Po timeout lub błędzie ustal stan
własnych procesów; nie uruchamiaj drugiej kopii w ciemno. Przestrzegaj reguły
AGENTS dotyczącej 60 s bez nowego wyniku. Nie naprawiaj testów podczas audytu.

Smoke używa `out/make/zip/win32/x64`, dlatego najpierw porównaj jego SHA
z finalną stabilną kopią i tabelą powyżej. Każdy wariant smoke ponownie
sprawdza ZIP, app.asar i metadane, rozpakowuje własną kopię i sprząta fixture.

```powershell
$env:SELECTOR_AUDIT_ZIP = $selectorAuditZip
$env:SELECTOR_AUDIT_MAKE_ZIP = Join-Path (Get-Location) 'apps/selector-desktop/out/make/zip/win32/x64/Selektor zdjec-win32-x64-0.1.2.zip'
& $selectorAuditNode $selectorAuditBounded 30 powershell.exe -NoProfile -NonInteractive -Command 'Get-FileHash -Algorithm SHA256 -LiteralPath @($env:SELECTOR_AUDIT_ZIP, $env:SELECTOR_AUDIT_MAKE_ZIP)'
& $selectorAuditNode $selectorAuditBounded 30 powershell.exe -NoProfile -NonInteractive -Command 'Get-Content -Raw -LiteralPath ($env:SELECTOR_AUDIT_ZIP + ".release.json")'
```

Jeśli `out/make` ma inną sumę albo brakuje paczki, nie wykonuj poniższych
smoke na przypadkowym buildzie. Użyj istniejących skryptów smoke na własnej
rozpakowanej kopii finalnego ZIP-a, podając jawnie ścieżkę EXE i jego
`.release.json`. Jeśli finalnej paczki nie ma, odnotuj brak weryfikacji.
Nie nadpisuj żadnej paczki. Przy zgodności wykonaj kolejno, do 120 s każdy:

```powershell
& $selectorAuditNode $selectorAuditBounded 120 npm run smoke:release:start --workspace apps/selector-desktop
& $selectorAuditNode $selectorAuditBounded 120 npm run smoke:release --workspace apps/selector-desktop
& $selectorAuditNode $selectorAuditBounded 120 npm run smoke:release:shortcuts --workspace apps/selector-desktop
& $selectorAuditNode $selectorAuditBounded 120 npm run smoke:release:legacy --workspace apps/selector-desktop
& $selectorAuditNode $selectorAuditBounded 120 npm run smoke:release:ux --workspace apps/selector-desktop
Set-Location -LiteralPath 'D:\game_predicotr\worktrees\offline-photo-selector\apps\selector-desktop'
& $selectorAuditNode $selectorAuditBounded 120 $selectorAuditNode scripts/smoke-update.mjs $selectorAuditOldZip $selectorAuditZip
```

Przy rozszerzeniu kontroli stosuj mały, odizolowany przypadek odtwarzający
konkretny problem. Nie zapisuj nowych testów w źródłach. Nie powtarzaj całego
zestawu po każdej obserwacji. Brak zależności/CLI lub przekroczenie timeout
jest ograniczeniem dowodów, nie pretekstem do ukrytej instalacji lub zmiany
konfiguracji. Jeśli audyt ma wymagać długiej, kosztownej pracy, uprzedź
operatora i uzyskaj zgodę zgodnie z AGENTS. Ten dokument nie upoważnia do
nieograniczonego kosztu audytu ani benchmarków.

## Wymagany raport i granice werdyktu

Stosuj [szablon raportu](AUDIT_REPORT_TEMPLATE.md), dostosowując tytuł do
całego selektora. Wiersz werdyktu musi mieć dokładnie `Werdykt: PASS` albo
`Werdykt: REVISE`. PASS oznacza brak otwartych P0/P1; nie oznacza odbioru
na komputerze odbiorcy. Dla nowych P2 wybierz najwyżej pięć najważniejszych.
Niezależnie od tego odpowiedz na każde stare ustalenie z tabeli REVISE.

Raport musi zawierać:

1. Faktyczny model, datę, base/HEAD, stan worktree i tożsamość sprawdzonego
   ZIP-a. Wskaż różnicę między źródłem paczki a późniejszą dokumentacją.
2. Znaleziska z ważnością, `plik:linia`, skutkiem, scenariuszem odtworzenia
   i propozycją poprawki. Rozdziel potwierdzony błąd od przypuszczenia.
3. Pokrycie każdego obszaru i kryteriów tasków: spełnione, niespełnione albo
   niezweryfikowane; zawsze z dowodem lub przyczyną braku dowodu.
4. Status każdego starego ustalenia: zamknięte, otwarte albo pozostawione
   jako jawna granica zakresu. Podaj dowód i oceń, czy granica jest akceptowalna.
5. Faktycznie uruchomione komendy, kody wyjścia, liczbę testów, timeouty
   i istotne logi. Wyników wykonawcy nie opisuj jako własnych testów.
6. Listę potrzebnych poprawek i brakujących testów oraz osobne ograniczenia
   odbioru. Zakończ informacją, czy kod może przejść do pilotażu.

Przegląd źródeł jest tylko do odczytu. Jeśli uruchamiasz kontrole, napisz:
„Przegląd kodu bez zmian w źródłach; dodatkowo wykonano wskazane kontrole
na odizolowanych fixture'ach”. Jeśli nie uruchamiasz, napisz:
„Przegląd statyczny, bez zmian w plikach; testów nie uruchamiano”. Jedynym
dokumentem wynikowym audytora jest nowy raport; nie zmieniaj starego REVISE.

Fizyczny odbiór TASK-0979 nadal jest osobną bramką: prawdziwy komputer
odbiorcy, rzeczywista droga dostarczenia ZIP-a, brak narzędzi deweloperskich,
restart Windows, aktualizacja u odbiorcy i reakcja ochrony Windows.
Lokalny smoke ani restart procesu nie dowodzą tych punktów. Niepodpisana
paczka może być zablokowana; wtedy odbiór jest wstrzymany.

Nie obiecujemy odporności na zanik zasilania/uszkodzenie dysku, blokad między
komputerami przez synchronizację, obsługi USB, automatycznego odtworzenia
JPEG-a ani stałego czasu dla 15 000 zdjęć. Oceń zgodność tych granic z
zaakceptowanym zakresem i ich jasność w instrukcji, bez dopisywania funkcji.
