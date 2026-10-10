# Audyt TASK-0954 - Zabezpieczenie repozytorium przed porzuceniem C

Werdykt: REVISE
Audytor: gpt-6.1-sol, medium
Wykonawca: claude-opus-5-5, medium
Zakres: HEAD...cf60805fc8dccd176916429749d43602983254df oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-10
Runda: 4

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Poprawki zamykają uwagi z rundy 3 dotyczące referencji, zachowywanych danych i flagi `-CreateRefs`. Bundle na D jest poprawny i zawiera zgodne referencje wszystkich 22 gałęzi/tagów C. Pozostają dwie luki: weryfikacja nie wiąże manifestów z zapisanym digestem, a nazwy katalogów backupu mogą kolidować między worktree’ami.

## Znaleziska

### P0

- [P0-7] `scripts/inventory_worktrees.ps1:287` — `-VerifyClone` wybiera najnowszy katalog manifestów i sprawdza pokrycie wpisów oraz zgodność kopii z tymi manifestami, ale nie porównuje ich digestu z `IgnoredDigest` zapisanym w inwentarzu. Skrócenie manifestu do poprawnego nagłówka zachowuje pokrycie `entry=`, a weryfikacja sprawdza wtedy zero plików. Brakujące pliki kopii mogą pozostać niewykryte i przebieg może zakończyć się `RESULT: OK`. Poprawka: przed weryfikacją kopii wymagać zgodności `Get-ManifestDirDigest $finalRun.FullName` z `$r.IgnoredDigest`; brak lub rozbieżność powinny blokować sukces.

- [P0-8] `scripts/inventory_worktrees.ps1:326` — Rozwiązywanie kolizji nazw wykonuje tylko jedną próbę, dopisując osiem znaków HEAD. Trzy detached worktree’y o tej samej nazwie końcowego katalogu i tym samym HEAD otrzymają nazwy `task`, `task-<hash>`, `task-<hash>`. Trzeci zapisze dane do katalogu drugiego, nadpisując jego patche, pliki lub manifesty. Narusza to wymóg osobnego zabezpieczenia każdego worktree’a. Poprawka: użyć identyfikatora opartego na pełnej ścieżce i sprawdzić jego unikalność przed jakimkolwiek zapisem oraz utworzeniem referencji.

### P1

Brak.

### P2

- [P2-4] `scripts/sync_data_directories_to_d.ps1:769` — Nowy tryb `-ManifestOnly` pomija kontrolę `$listing.Exists`, obecną w ścieżce kopiowania w linii 798. Nieistniejący wybrany wpis otrzymuje pusty manifest i wynik `OK`. Może to ukryć literówkę albo zniknięcie źródła pomiędzy inwentaryzacją a tworzeniem manifestu. Poprawka: brak wybranego wpisu zgłaszać jako błąd; istniejący pusty katalog nadal może mieć pusty manifest.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Inwentarz obejmuje wszystkie worktree’y, również detached i `.claude/worktrees` | spełnione | Odczyt backupu: dziewięć rekordów; `git worktree list --porcelain`: dziewięć wpisów. |
| Zmiany mają patche lub kopie; odtworzony status jest równy inwentarzowi | niezweryfikowane | Kolejność odtwarzania i kontrola digestu: `scripts/inventory_worktrees.ps1:249`. Wyniki wykonawcy zapisano w Outcome; audyt nie wykonywał odtwarzania. Ogólną gwarancję narusza P0-8. |
| Dane ignorowane są sklasyfikowane; zachowywane kopie mają równe manifesty SHA-256 | niezweryfikowane | Osiem kopii ma zapis `exit 0 (Final)`; nagłówki manifestów obejmują wszystkie zachowywane wpisy. Nie przeliczano hashy plików kopii. P0-7 osłabia weryfikację. |
| Bundle weryfikuje się na D i zawiera wszystkie gałęzie i tagi C | spełnione | `git bundle verify`: kod 0, pełna historia. Porównanie referencji C z `git ls-remote <bundle>`: 22 referencje, zero różnic. |
| Cztery gałęzie są na `origin`, z tymi samymi hashami na D | niespełnione | Push jawnie odroczono: `ai_docs/tasks/0954-disk-d-repository-handover.md:214`. |
| Checkout D zawiera plan i skrypty; hash jest zapisany w Outcome | niespełnione | `git -C D:\game_predicotr rev-parse HEAD`: `c504fe70afe0c5fe4de8579c0d277e2093205d44`. Aktualizacja checkoutu pozostaje odroczona. |
| Hash ewentualnego commita zapisów Outcome jest odnotowany w tasku i CURRENT_STATE | spełnione | Warunek nie ma zastosowania: zmian main nie commitowano, pozostawiono je w patchach; `ai_docs/tasks/0954-disk-d-repository-handover.md:218`. |

## Listy zamknięte i otwarte

Zamknięte:

- P0-5: zapis i porównanie referencji repozytorium; `scripts/inventory_worktrees.ps1:202` oraz `scripts/inventory_worktrees.ps1:454`.
- P0-6: digest manifestów zachowywanych danych i jego porównanie z baseline; `scripts/inventory_worktrees.ps1:398` oraz `scripts/inventory_worktrees.ps1:450`.
- P1-3: obowiązkowa flaga `-CreateRefs` w instrukcjach; `ai_docs/tasks/0954-disk-d-repository-handover.md:170` oraz `ai_docs/tasks/0957-disk-d-cleanup-and-job-paths.md:198`.

Otwarte: P0-7, P0-8, P2-4.

## Proponowane testy

Proponowany plik: `scripts/test_inventory_worktrees.ps1`. Komenda: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_inventory_worktrees.ps1`. Scenariusze wykonywać wyłącznie na tymczasowych fixture’ach.

- Po poprawnym backupie usunąć wiersz pliku z manifestu i odpowiadający plik kopii. `-VerifyClone` powinien zakończyć się błędem zgodności z `IgnoredDigest`.
- Utworzyć trzy detached worktree’y na tym samym HEAD, w różnych katalogach nadrzędnych, z identyczną nazwą końcową. Każdy powinien otrzymać osobny katalog backupu i zachować własne dane.
- Wywołać `-ManifestOnly` dla nieistniejącego wpisu. Oczekiwany kod 1; istniejący pusty katalog powinien zakończyć się kodem 0.

## Zakres przeglądu i ograniczenia

Przeczytano brief, raport rundy 3, skrypt inwentaryzacji, zmiany skryptu synchronizacji i powiązane funkcje manifestów, taski 0954 i 0957 oraz właściwe fragmenty planu i dokumentacji procesu. Sprawdzono inwentarz backupu na D, pokrycie wpisów nagłówkami manifestów, bundle, referencje gałęzi/tagów i HEAD checkoutu D.

Wykonano wyłącznie odczyty oraz polecenia Git służące weryfikacji. Nie uruchamiano testów, kopiowania, odtwarzania, fetch, push ani merge. Nie przeliczano hashy całego backupu. Znaleziska opisują ścieżki błędnego działania; nie stwierdzono utraty danych w dostępnej kopii.

Odroczenie push, merge i aktualizacji checkoutu D jest jawne; task pozostaje `in_progress`. Jego zamknięcie i wejście do B1 wymagają spełnienia pozostałych kryteriów oraz usunięcia otwartych P0.