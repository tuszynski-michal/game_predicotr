# Audyt TASK-0953 — Przyrostowa kopia katalogów danych na D

Werdykt: REVISE
Audytor: gpt-6.1-sol, high
Wykonawca: claude-opus-5-5; reasoning niepodany w Outcome
Zakres: HEAD...f3429d8a50e3f3433f42f72dd62ef2fad919f523 oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-10
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano skrypt synchronizacji, zmiany dokumentacji i konfiguracji npm oraz zgodność z taskiem i planem. Większość wymaganych mechanizmów jest zaimplementowana, a Outcome opisuje wykonane próby. Pozostają dwa problemy: porównanie ścieżek może błędnie zakwalifikować istniejący plik do usunięcia, a weryfikacja zapisanego manifestu nie obejmuje całej pracy kontrolą limitu czasu.

## Znaleziska

### P0

- [P0-1] `scripts/sync_data_directories_to_d.ps1:421` — Manifest używa `StringComparer.Ordinal`, mimo że wcześniejsza lista plików używa `OrdinalIgnoreCase` i skrypt działa na Windows. Źródłowe `work/a.txt` i docelowe `work/A.txt` zostaną więc uznane przez porównanie za plik brakujący i dodatkowy, nawet gdy zawartość jest identyczna. Jeżeli taki docelowy klucz znajduje się na zatwierdzonej liście, gałąź `-Mirror` może usunąć go w linii 814, choć odpowiadający mu plik istnieje również w źródle. Należy ujednolicić identyfikację ścieżek zgodnie z niewrażliwością na wielkość liter na docelowym NTFS, również przy porównaniu i kwalifikowaniu plików do usunięcia. Dodać regresję dla różnicy wyłącznie w wielkości liter.

### P1

- [P1-1] `scripts/sync_data_directories_to_d.ps1:638` — W gałęzi `-VerifyOnly -Manifest` ostatnie sprawdzenia deadline’u odbywają się podczas odczytu plików i hashowania. `Compare-Manifests` nie sprawdza deadline’u, a po porównaniu i zapisaniu raportu nie ma końcowego `Assert-Deadline`. Duży manifest może zatem przekroczyć limit podczas porównania i nadal zakończyć się kodem 0 lub 1 zamiast wymaganym kodem 2. Ponadto `Read-Manifest` w linii 603 wykonuje się przed ustanowieniem deadline’u. Należy rozpocząć budżet przed odczytem manifestu, kontrolować go podczas porównania i zamknąć kontrolą przed ogłoszeniem wyniku.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Inwentarz, domyślny wybór zachowywanych wpisów i wykluczenie worktree’ów | spełnione | `scripts/sync_data_directories_to_d.ps1:320`, `:273`, `:692`, `:704`; bieżący odczyt ignorowanych wpisów C nie wykazał nowych zachowywanych wpisów według reguł skryptu. |
| Kontrakt `Initial`, liczniki i `INCOMPLETE` | spełnione | `scripts/sync_data_directories_to_d.ps1:492`, `:769`, `:773`, `:847`; ocena statyczna. |
| Zapisany manifest ignoruje nowe pliki celu i wykrywa zmienione | spełnione | `scripts/sync_data_directories_to_d.ps1:615`, `:638`, `:649`; porównywane są tylko zapisane klucze. |
| Drugi przebieg kopiuje tylko nowe lub zmienione pliki | niezweryfikowane | Outcome deklaruje trzy skopiowane pliki: `ai_docs/tasks/completed/0953-disk-d-data-directory-sync.md:314`. Nie powtarzano przebiegu. |
| `Final` i wykrywanie brakujących plików | niespełnione | Porównanie istnieje, lecz błędnie interpretuje różnice wielkości liter: `scripts/sync_data_directories_to_d.ps1:471`; P0-1. |
| Odmowa `-Mirror` bez wymaganego trybu i potwierdzenia | spełnione | `scripts/sync_data_directories_to_d.ps1:555`. Bezpieczeństwo samego usuwania pozostaje objęte P0-1. |
| Kopia `.tooling` i kontrola toolchainu z D | niezweryfikowane | Deklaracje wykonawcy: `ai_docs/tasks/completed/0953-disk-d-data-directory-sync.md:311`, `:320`. Nie uruchamiano kontroli środowiska. |
| Ochrona nazw i zawartości kluczy podpisu | spełnione | Mechanizmy redakcji: `scripts/sync_data_directories_to_d.ps1:151`, `:200`, `:500`, `:695`; ocena statyczna. |
| Limit czasu per wpis i kod 2 po przekroczeniu | niespełnione | `scripts/sync_data_directories_to_d.ps1:603`, `:638`, `:654`; P1-1. |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P0-1, P1-1.

## Proponowane testy

- Dla `scripts/sync_data_directories_to_d.ps1` przygotować mały fixture NTFS: źródło `work/a.txt`, cel `work/A.txt`, identyczna zawartość i znaczniki czasu. Uruchomić `-VerifyOnly` oraz `-Mode Final` z jawnymi parametrami `-Source $src -Destination $dst -LogRoot $logs -Directories work`. Oczekiwany wynik: brak fałszywych pozycji `missing` i `extra`. W wariancie `-Mirror -Confirm -MirrorApprovedList $approved` odpowiadający plik źródłowy musi chronić plik celu przed usunięciem.
- Dla tej samej gałęzi skryptu wykonać ograniczony test funkcji z przekroczonym deadline’em podczas porównania. Następnie sprawdzić `-VerifyOnly -Manifest $manifest -Destination $dst -LogRoot $logs -TimeoutSeconds 1`. Przekroczenie budżetu podczas odczytu lub porównania manifestu musi dawać `TIMEOUT` i kod 2.

## Zakres przeglądu i ograniczenia

Przeczytano brief, pełny skrypt zgodny z jego kopią, task z Outcome, wskazane zmiany dokumentacyjne i konfigurację npm oraz właściwe fragmenty planu, stanu projektu i zasad procesu. Wykonano wyłącznie odczyty plików i polecenia git bez zmian stanu; pomocniczo odczytano istniejący inwentarz na D.

Nie uruchamiano synchronizacji, usuwania, testów, usług ani kontroli środowiska. Wyniki przebiegów opisanych w Outcome pozostają deklaracjami wykonawcy. Pełny przebieg `Final` na danych operatora należy do TASK-0955 i nie był wymagany w tym audycie.