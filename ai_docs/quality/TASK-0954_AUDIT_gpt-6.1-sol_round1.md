# Audyt TASK-0954 - Zabezpieczenie repozytorium przed porzuceniem C

Werdykt: REVISE
Audytor: gpt-6.1-sol, medium
Wykonawca: claude-opus-5-5, medium
Zakres: HEAD...cf60805fc8dccd176916429749d43602983254df oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-10
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono skrypt, dokumentację taska, fragment planu oraz dostępne artefakty na D. Inwentarz obejmuje dziewięć worktree’ów, a bundle poprawnie weryfikuje się w klonie D. Zabezpieczenie wymaga poprawek: błędy kopiowania danych ignorowanych nie zatrzymują skryptu, kopie wykonano bez wymaganej weryfikacji SHA-256, a porównanie może nadpisać własny punkt odniesienia.

## Znaleziska

### P0

- [P0-1] `scripts/inventory_worktrees.ps1:258` — Kod zakończenia skryptu kopiującego dane ignorowane jest wyłącznie zapisywany jako tekst. Nawet po błędzie lub timeoutcie wykonanie dochodzi do `exit 0`. `-VerifyClone` również nie sprawdza tych kopii. Skrypt może więc zgłosić sukces przy brakujących danych zachowywanych. Poprawka: propagować niezerowy kod synchronizacji i blokować pozytywny wynik zabezpieczenia do czasu poprawnej weryfikacji wszystkich wymaganych kopii.

- [P0-2] `scripts/inventory_worktrees.ps1:48` — Domyślny tryb `Initial` nie zapewnia wymaganego równego manifestu SHA-256. Dostępny inwentarz wskazuje `exit 0 (Initial)` dla wszystkich ośmiu worktree’ów innych niż main; odczytany manifest `wt0858` zawiera `kind=size` oraz `-` zamiast hasha. To niespełnione kryterium akceptacji, mimo deklaracji „Zabezpieczenie gotowe” w `ai_docs/process/CURRENT_STATE.md:125`. Poprawka: wykonać `Final` lub odpowiednią weryfikację SHA-256 wszystkich zachowywanych wpisów, zapisać dowody i uzależnić deklarację gotowości od ich wyniku.

- [P0-3] `scripts/inventory_worktrees.ps1:273` — Nowy `inventory.json` jest zapisywany przed odczytaniem `-CompareWith` w linii 290. Przy wskazaniu `<OutputRoot>\inventory.json` jako poprzedniego inwentarza skrypt nadpisuje baseline, porównuje nowy stan z nim samym i zwraca `UNCHANGED`. To może przepuścić zmiany przez bramkę przed usunięciem C. Poprawka: odczytać baseline przed jakimkolwiek zapisem i odrzucać kolizję ścieżek albo zapisywać każdy przebieg w osobnym katalogu.

### P1

- [P1-1] `scripts/inventory_worktrees.ps1:71` — Wywołania Git nie mają jawnego timeoutu. Dotyczy to także `fetch`, odtwarzania worktree’ów i nakładania patchy. Skrypt może czekać bez końca, co narusza regułę limitów czasu z `AGENTS.md`. Poprawka: wykonywać komendy przez mechanizm z jawnym limitem, obsługą timeoutu oraz kontrolowanym sprzątaniem rozpoczętego odtworzenia.

### P2

- [P2-1] `scripts/inventory_worktrees.ps1:150` — Weryfikacja odtworzenia porównuje jedynie wpisy statusu. Zmieniona lub uszkodzona kopia pliku nieśledzonego nadal daje identyczny wpis `??`, więc przechodzi kontrolę. Poprawka: porównać również digest treści odtworzonego worktree’a z zapisanym `StatusDigest`; alternatywnie jawnie odnotować ograniczenie w `Outcome`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Inwentarz obejmuje wszystkie worktree’y, detached i `.claude/worktrees` | spełnione | Odczyt `INVENTORY.md` na D i `git worktree list --porcelain`: zgodne dziewięć wpisów. |
| Patche lub kopie zmian; odtworzony status równy inwentarzowi | niezweryfikowane | Poprawna kolejność aplikowania w `scripts/inventory_worktrees.ps1:137`; sukces opisany w `ai_docs/tasks/0954-disk-d-repository-handover.md:243`. Audyt nie uruchamiał odtworzenia. |
| Klasyfikacja danych ignorowanych i równe manifesty SHA-256 zachowywanych kopii | niespełnione | Inwentarze szczegółowe istnieją, lecz manifest odczytany dla `wt0858` ma `kind=size`; P0-2. |
| Bundle poprawny na D, zawiera wszystkie gałęzie i tagi C | spełnione | `git -C D:\game_predicotr bundle verify …`: kod 0, pełna historia. Porównanie referencji nie wykazało brakujących gałęzi ani tagów. |
| Cztery gałęzie na `origin`, zgodne hashe na D | niespełnione | Na D istnieją odpowiednie `refs/remotes/c/*`, brak odpowiadających `refs/remotes/origin/*`; odroczenie zapisano w `ai_docs/tasks/0954-disk-d-repository-handover.md:261`. |
| Checkout D zawiera plan i skrypty; hash zapisany w Outcome | niespełnione | `git -C D:\game_predicotr rev-parse HEAD`: `c504fe70afe0c5fe4de8579c0d277e2093205d44`; aktualizacja odroczona w `ai_docs/tasks/0954-disk-d-repository-handover.md:261`. |
| Hash ewentualnego commita zapisów Outcome odnotowany w tasku i CURRENT_STATE | spełnione | Warunek nie ma zastosowania: zmian main nie commitowano, pozostawiono je w patchach; `ai_docs/tasks/0954-disk-d-repository-handover.md:265`. |

## Listy zamknięte i otwarte

Zamknięte: Brak. Pierwsza runda audytu.

Otwarte: P0-1, P0-2, P0-3, P1-1, P2-1.

## Proponowane testy

Proponowany plik: `scripts/test_inventory_worktrees.ps1`. Komenda: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_inventory_worktrees.ps1`.

- Wymusić błąd i timeout synchronizacji danych ignorowanych; sprawdzić niezerowy wynik skryptu nadrzędnego.
- Zmienić zawartość zachowywanego pliku bez zmiany rozmiaru; weryfikacja SHA-256 musi wykryć różnicę.
- Uruchomić `-CompareWith` ze ścieżką bieżącego `OutputRoot\inventory.json`; zmiana musi zostać wykryta albo kolizja odrzucona bez nadpisania baseline.
- Wymusić zawieszenie komendy Git; sprawdzić zakończenie w limicie i sprzątanie.
- Zmienić zawartość kopii pliku nieśledzonego; weryfikacja odtworzenia powinna wykryć różnicę treści.

## Zakres przeglądu i ograniczenia

Przeczytano brief, skrypt, diff dokumentacji, task, właściwe fragmenty planu i decyzję D-540. Odczytano inwentarz na D, przykładowy manifest i log synchronizacji oraz fragmenty skryptu synchronizującego potrzebne do oceny jego kontraktu.

Nie uruchamiano testów, kopiowania, odtwarzania worktree’ów, fetch, push ani merge. Wyniki odtworzenia zapisane w `Outcome` pozostają deklaracją wykonawcy. Weryfikację bundle i odczyty referencji wykonano niezależnie.

Push, merge i aktualizacja checkoutu D pozostają jawnie odroczonymi czynnościami operatora. Task nadal ma status `in_progress`; nie spełnia jeszcze wszystkich warunków zamknięcia i wejścia do B1.