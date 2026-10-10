# Audyt TASK-0954 - Zabezpieczenie repozytorium przed porzuceniem C

Werdykt: REVISE
Audytor: gpt-6.1-sol, medium
Wykonawca: claude-opus-5-5, medium
Zakres: HEAD...cf60805fc8dccd176916429749d43602983254df oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-10
Runda: 3

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Poprawki zamykają wszystkie otwarte uwagi z rundy 2. Dostępny backup obejmuje dziewięć worktree’ów, a bundle weryfikuje się na D i zawiera zgodne referencje wszystkich 22 gałęzi/tagów C. Pozostają luki w bramce wykrywania zmian po zabezpieczeniu oraz brak wymaganej flagi w instrukcji tworzenia backupu.

## Znaleziska

### P0

- [P0-5] `scripts/inventory_worktrees.ps1:398` - `-CompareWith` porównuje wyłącznie HEAD i digest plików poszczególnych worktree’ów. Nie zapisuje ani nie porównuje referencji repozytorium. Dodanie lub przesunięcie gałęzi niewybranej w żadnym worktree albo dodanie tagu może pozostawić wynik `COMPARE: UNCHANGED`, mimo że wcześniejszy bundle nie zabezpiecza nowej referencji lub jej commitów. TASK-0957 używa tego wyniku jako bramki przed usunięciem C. Poprawka: zapisywać pełny zbiór referencji i ich hashy oraz wykrywać jego zmianę; brak takiego zbioru w starszym baseline powinien wymagać ponownego zabezpieczenia.

- [P0-6] `scripts/inventory_worktrees.ps1:398` - Porównanie pomija `IgnoredPreserved` i treść zachowywanych plików ignorowanych. Dla main kopiowanie jest dodatkowo pomijane w linii 348. Nowy lub zmieniony ignorowany plik na C, np. profil w `.runtime/` po przebiegu B1, nie zmienia `StatusDigest`; ponowna inwentaryzacja może zwrócić `UNCHANGED`, pozostawiając ten plik bez aktualnej kopii. Kontrola manifestu B1 opisana w TASK-0957 sprawdza zachowane pliki na D, więc nie wykrywa takiej zmiany źródła C. Poprawka: bramka powinna porównywać również zbiór i hashe zachowywanych danych C z ostatnim zabezpieczonym stanem, z jawnymi wyłączeniami danych odtwarzalnych.

### P1

- [P1-3] `ai_docs/tasks/0954-disk-d-repository-handover.md:168` - Udokumentowana komenda inwentaryzacji nie zawiera `-CreateRefs`, a następny krok tworzy bundle przez `--all`. W świeżym przebiegu detached HEAD nie ma gwarantowanej referencji i może zostać pominięty. Istniejące `refs/c-migration/*` maskują ten brak tylko dla wcześniej zabezpieczonych HEAD. Poprawka: dodać `-CreateRefs` do komendy wykonywanej przed tworzeniem bundle i wskazać obowiązek ponownego tworzenia tych referencji przy odświeżaniu backupu.

### P2

Brak.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Inwentarz obejmuje wszystkie worktree’y, również detached i `.claude/worktrees` | spełnione | Odczyt `inventory.json` na D i `git worktree list --porcelain`: zgodne dziewięć wpisów. |
| Zmiany mają patche lub kopie; odtworzony status jest równy inwentarzowi | niezweryfikowane | Kolejność staged → unstaged → untracked i kontrola digestu: `scripts/inventory_worktrees.ps1:213`. Sukces opisany w `ai_docs/tasks/0954-disk-d-repository-handover.md:297`; audyt nie wykonywał odtwarzania. |
| Dane ignorowane są sklasyfikowane; zachowywane kopie mają równe manifesty SHA-256 | niezweryfikowane | Osiem kopii ma `exit 0 (Final)`; odczyt nagłówków manifestów wykazał zero brakujących wpisów. Nie przeliczano hashy kopii. |
| Bundle weryfikuje się na D i zawiera wszystkie gałęzie i tagi C | spełnione | `git bundle verify`: kod 0, pełna historia. Porównanie `for-each-ref` z `ls-remote` bundle: 22 referencje, zero różnic. |
| Cztery gałęzie są na `origin`, z tymi samymi hashami na D | niespełnione | Push jawnie odroczony: `ai_docs/tasks/0954-disk-d-repository-handover.md:310`. |
| Checkout D zawiera plan i skrypty; hash jest zapisany w Outcome | niespełnione | `git -C D:\game_predicotr rev-parse HEAD`: `c504fe70afe0c5fe4de8579c0d277e2093205d44`; aktualizacja odroczona w `ai_docs/tasks/0954-disk-d-repository-handover.md:310`. |
| Hash ewentualnego commita zapisów Outcome jest odnotowany w tasku i CURRENT_STATE | spełnione | Warunek nie ma zastosowania: zmian main nie commitowano; pozostawiono je w patchach, `ai_docs/tasks/0954-disk-d-repository-handover.md:314`. |

## Listy zamknięte i otwarte

Zamknięte:

- P0-4: wymagany udany tryb `Final` i pokrycie wszystkich zachowywanych wpisów nagłówkami manifestów; `scripts/inventory_worktrees.ps1:250`.
- P1-2: instrukcje wskazują baseline `inventory.json`; `ai_docs/tasks/0954-disk-d-repository-handover.md:147` oraz `ai_docs/tasks/0957-disk-d-cleanup-and-job-paths.md:196`.
- P2-2: jawny odczyt UTF-8; `scripts/inventory_worktrees.ps1:174` i `:346`.
- P2-3: nieudane usunięcie tymczasowego worktree’a zwiększa liczbę błędów; `scripts/inventory_worktrees.ps1:235`.

Otwarte: P0-5, P0-6, P1-3.

## Proponowane testy

Proponowany plik: `scripts/test_inventory_worktrees.ps1`. Komenda: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_inventory_worktrees.ps1`.

- Po zapisaniu baseline dodać lub przesunąć referencję gałęzi niewybranej w żadnym worktree oraz dodać tag. `-CompareWith` powinien wykryć zmianę.
- Po zabezpieczeniu main zmienić istniejący i dodać nowy ignorowany plik zachowywany. Bramka powinna wykryć oba przypadki.
- W świeżym repozytorium utworzyć detached HEAD z osobnym commitem i wykonać dokładną sekwencję z sekcji `Verification`. Bundle musi zawierać referencję do tego HEAD.

## Zakres przeglądu i ograniczenia

Przeczytano brief, poprzedni raport, skrypt inwentaryzacji, diff dokumentacji, taski 0954 i 0957 oraz odpowiednie fragmenty planu, CURRENT_STATE i decyzji D-540. Sprawdzono kontrakt weryfikacji manifestów skryptu synchronizacji, inwentarz backupu oraz pokrycie zachowywanych wpisów manifestami.

Wykonano wyłącznie odczyty plików i polecenia Git służące sprawdzeniu worktree’ów, referencji, bundle i HEAD klonu D. Nie uruchamiano testów, kopiowania, odtwarzania, fetch, push ani merge. Nie przeliczano hashy całego backupu.

Odroczenie push, merge i aktualizacji checkoutu D jest jawne; task pozostaje `in_progress`. Zamknięcie taska i wejście do B1 wymagają spełnienia pozostających kryteriów oraz usunięcia otwartych P0/P1.