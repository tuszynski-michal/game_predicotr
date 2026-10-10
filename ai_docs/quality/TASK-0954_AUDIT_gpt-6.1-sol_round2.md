# Audyt TASK-0954 - Zabezpieczenie repozytorium przed porzuceniem C

Werdykt: REVISE
Audytor: gpt-6.1-sol, medium
Wykonawca: claude-opus-5-5, medium
Zakres: HEAD...cf60805fc8dccd176916429749d43602983254df oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-10
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Poprawki usuwają wcześniej zgłoszone błędy propagowania kodów zakończenia, trybu kopiowania, odczytu baseline i porównywania treści odtworzonych plików. Dostępny inwentarz obejmuje dziewięć worktree’ów, a bundle poprawnie weryfikuje się na D i zawiera aktualne gałęzie C. Pozostają luka w kontroli kompletności manifestów oraz niezgodność formatu baseline z udokumentowaną komendą bramki.

## Znaleziska

### P0

- [P0-4] `scripts/inventory_worktrees.ps1:243` — Weryfikacja kopii ignorowanych przekazuje katalog manifestów do skryptu synchronizacji, ale nie sprawdza, czy manifesty obejmują wszystkie wpisy `IgnoredPreserved`. Skrypt synchronizacji weryfikuje tylko znalezione pliki `*.source.tsv`. Przykładowo usunięcie jednego z trzech manifestów `wt0858` razem z odpowiadającą mu kopią pozostawi dwa poprawne manifesty i pozwoli uzyskać `RESULT: OK`. Dodatkowo linia 250 dopuszcza sukces dla kopii oznaczonej `skipped`, nawet gdy worktree ma dane zachowywane. Poprawka: dla każdego worktree’a objętego kopiowaniem wymagać udanego trybu `Final` i zgodności pełnego zbioru nagłówków `entry` manifestów z `IgnoredPreserved`. Wyjątek dla main powinien pozostać jawnie przypisany do TASK-0953.

### P1

- [P1-2] `scripts/inventory_worktrees.ps1:174` — `-CompareWith` przyjmuje wyłącznie JSON, natomiast `ai_docs/tasks/0954-disk-d-repository-handover.md:147` opisuje porównanie z `INVENTORY.md`. Komenda konsumenta w `ai_docs/tasks/0957-disk-d-cleanup-and-job-paths.md:196` również przekazuje `INVENTORY.md`. Udokumentowana bramka zakończy się błędem `ConvertFrom-Json`, zamiast porównać stan. Poprawka: ujednolicić kontrakt i instrukcje, wskazując `inventory.json` we wszystkich komendach porównania, albo obsłużyć udokumentowany format Markdown.

### P2

- [P2-2] `scripts/inventory_worktrees.ps1:174` — Inwentarz jest zapisywany jako UTF-8 bez BOM, lecz odczytywany przez `Get-Content` bez `-Encoding UTF8`. To samo dotyczy odczytu inwentarza danych ignorowanych w linii 334. Windows PowerShell 5.1 może błędnie odczytać polskie znaki w ścieżkach, powodując fałszywe różnice lub błędy kopiowania. Poprawka: jawnie ustawić UTF-8 w obu odczytach.

- [P2-3] `scripts/inventory_worktrees.ps1:235` — Kod zakończenia usuwania tymczasowego worktree’a jest ignorowany. Nieudane sprzątanie może pozostawić katalog i rejestrację worktree’a, mimo końcowego `RESULT: OK`; następna weryfikacja zatrzyma się na istniejącej ścieżce. Poprawka: sprawdzić wynik usunięcia i raportować pozostały katalog oraz niezerowy wynik sprzątania.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Inwentarz obejmuje wszystkie worktree’y, również detached i `.claude/worktrees` | spełnione | Odczyt inwentarza na D i `git worktree list --porcelain`: zgodne dziewięć wpisów. |
| Zmiany mają patche lub kopie; odtworzony status jest równy inwentarzowi | niezweryfikowane | Właściwa kolejność odtwarzania w `scripts/inventory_worktrees.ps1:213`; porównanie statusu i digestu w linii 225. Sukces opisany w `ai_docs/tasks/0954-disk-d-repository-handover.md:275`; audyt nie wykonywał odtworzenia. |
| Dane ignorowane są sklasyfikowane; zachowywane kopie mają równe manifesty SHA-256 | niezweryfikowane | Osiem kopii ma status `exit 0 (Final)`, zgodne liczby wpisów i manifestów oraz logi `RESULT: OK`. Przykładowy manifest `wt0858` ma `kind=sha256`. Nie przeliczano wszystkich hashy; luka w weryfikatorze: P0-4. |
| Bundle weryfikuje się na D i zawiera wszystkie gałęzie i tagi C | spełnione | `git bundle verify`: kod 0, pełna historia. Porównanie `for-each-ref` z `ls-remote` bundle: brak brakujących lub różnych referencji w zbiorze 22 gałęzi/tagów. |
| Cztery gałęzie są na `origin`, z tymi samymi hashami na D | niespełnione | Push pozostaje odroczony: `ai_docs/tasks/0954-disk-d-repository-handover.md:290`. Referencje `refs/remotes/c/*` nie zastępują tego kryterium. |
| Checkout D zawiera plan i skrypty; hash jest zapisany w Outcome | niespełnione | `git -C D:\game_predicotr rev-parse HEAD`: `c504fe70afe0c5fe4de8579c0d277e2093205d44`; aktualizacja odroczona w `ai_docs/tasks/0954-disk-d-repository-handover.md:290`. |
| Hash ewentualnego commita zapisów Outcome jest odnotowany w tasku i CURRENT_STATE | spełnione | Warunek nie ma zastosowania: zmian main nie commitowano, pozostawiono je w patchach; `ai_docs/tasks/0954-disk-d-repository-handover.md:294`. |

## Listy zamknięte i otwarte

Zamknięte:

- P0-1: niezerowe wyniki kopiowania propagowane do wyniku przebiegu; `scripts/inventory_worktrees.ps1:346` i `:377`.
- P0-2: domyślny tryb `Final`; `scripts/inventory_worktrees.ps1:58`. Dostępne kopie ośmiu worktree’ów mają manifesty SHA-256 i logi sukcesu.
- P0-3: baseline odczytywany przed zapisem, kolizja z bieżącym `inventory.json` odrzucana; `scripts/inventory_worktrees.ps1:185`.
- P1-1: wywołania Git mają mechanizm timeoutu; `scripts/inventory_worktrees.ps1:107`.
- P2-1: odtworzenie porównuje również digest treści; `scripts/inventory_worktrees.ps1:224`.

Otwarte: P0-4, P1-2, P2-2, P2-3.

## Proponowane testy

Proponowany plik: `scripts/test_inventory_worktrees.ps1`. Komenda: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test_inventory_worktrees.ps1`.

- Na kopii fixture usunąć jeden manifest i odpowiadający mu zachowywany plik, pozostawiając inne poprawne manifesty. `-VerifyClone` musi zwrócić błąd.
- Wykonać inwentaryzację fixture z `-SkipIgnoredCopy`, następnie weryfikację. Brak wymaganej kopii musi uniemożliwić pełny sukces.
- Sprawdzić dokładną komendę `-CompareWith` zapisaną w TASK-0957.
- W Windows PowerShell 5.1 sprawdzić ścieżki zawierające polskie znaki.
- Wymusić błąd usunięcia tymczasowego worktree’a i sprawdzić raportowanie nieudanego sprzątania.

## Zakres przeglądu i ograniczenia

Przeczytano brief, skrypt, diff dokumentacji, task, odpowiednie fragmenty planu, decyzję D-540 i poprzedni raport. Sprawdzono kontrakt skryptu synchronizacji, udokumentowane użycie `-CompareWith`, inwentarz na D, liczby manifestów, logi zakończenia oraz przykładowy manifest SHA-256.

Niezależnie wykonano odczyty referencji, weryfikację bundle i odczyt HEAD klonu D. Nie uruchamiano testów, kopiowania, odtwarzania worktree’ów, fetch, push ani merge. Nie przeliczano hashy całego backupu.

Push, merge i aktualizacja checkoutu D pozostają jawnie odroczonymi czynnościami operatora. Task nadal ma status `in_progress`; ich odroczenie nie jest zgodą na zamknięcie taska ani wejście do B1.