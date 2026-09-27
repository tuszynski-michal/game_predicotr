# Uzupełnienie pozycji niepełnych plansz — instrukcja operatora

Zakres: zaakceptowane T4 / TASK-0711, gra 777
`bfc4f949-5c14-4850-b02a-db99610bcfa5`, dokładne 70 numerów z planu.
Implementacja narzędzia nie jest wykonaniem migracji, wdrożenia ani apply.

Stan operacyjny2026-09-27: osobno zlecony rollout i apply70 zakończono
w TASK-0712;1050 pozycji,70 receiptów, liczniki ready/v2 i odbiór API/UI PASS.
Dowody oraz zakres pozostawionych13 braków poza pilotem opisuje
`ai_docs/quality/PARTIAL_BOARD_SYMBOL_REVIEW_ROLLOUT.md`, a Outcome:
`ai_docs/tasks/completed/0712-partial-board-production-rollout.md`.
Poniższa procedura pozostaje instrukcją przyszłych jawnie zlecanych operacji;
nie stanowi zgody na rozszerzenie zakresu danych.

## Kolejność wdrożenia

1. Zakończyć aktywne zapisy importu i korekt; wykonać i sprawdzić backup.
2. Po osobnym zleceniu wdrożenia zastosować migracje rozszerzające 0126–0128
   oraz zgodne API, worker i Admin. Nie uruchamiać starego writera.
3. Skontrolować nowy zapis i dostępność 15 pozycji, odrębnie od fizycznej
   kompletności zdjęcia. Plansza `pending_partial` może nadal wymagać źródła.
4. Wykonać preview. Przejrzeć blokery oraz właściciela, import, SHA źródła,
   rewizje, brakujące indeksy i klasyfikację każdej planszy. Historyczne
   985/1050 i 20 outside nie są wymaganymi wynikami klasyfikacji.
5. Dopiero po osobnym zleceniu kroku danych wykonać apply w partiach do 5.
6. Odbudować liczniki istniejącym ograniczonym mechanizmem, skontrolować
   marker semantyki v2, wykonać ponowny preview i odbiór 1050 pozycji.
7. Po odebranym pilocie odczytowo audytować wskazane inne gry stronami.
   Narzędzie audit nie naprawia danych innych gier.

## Polecenia PowerShell z katalogu repozytorium

Użyć projektowego interpretera i zainstalowanych zależności. Konfiguracja
API określa połączenie lokalnej bazy i `artifact_root`. Źródła są sprawdzane
w `artifact_root/data`; opcjonalny `--source-root` wskazuje inny jawny
katalog bazowy zarządzanych źródeł, bez zmiany zapisanych ścieżek w bazie.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'services/api/src') + ';' + (Join-Path (Get-Location) 'services/worker/src')
.venv\Scripts\python.exe scripts\reconcile_partial_board_symbol_review.py preview --output artifacts\partial-board-review\pilot70-preview.json
```

Preview działa na schemacie 0125 i nowszym w transakcji READ ONLY / REPEATABLE
READ. Nie inicjuje projekcji i nie stosuje migracji. Nieobecna kolumna
widoczności oznacza brak historycznej oceny. Źródło jest rzeczywiście
odczytywane i porównywane z SHA oraz wymiarami po EXIF.

Przykład **wyłącznie dla osobno zleconego apply**, po przeglądzie manifestu:

```powershell
$preview = Get-Content artifacts\partial-board-review\pilot70-preview.json -Raw | ConvertFrom-Json
.venv\Scripts\python.exe scripts\reconcile_partial_board_symbol_review.py apply --preview artifacts\partial-board-review\pilot70-preview.json --preview-sha256 $preview.previewSha256 --limit 5 --output artifacts\partial-board-review\apply-batch.json
```

Powtórzenie tego samego polecenia odczytuje wcześniejsze pokwitowania i
próbuje następnych, jeszcze niewykonanych pozycji. Sukces planszy i receipt
są jednym commitem. Restart lub utrata raportu nie powiela pozycji, eventów
ani decyzji. Po późniejszej ręcznej zmianie retry zwraca wcześniejszy wynik
operacji bez nadpisywania tej zmiany.

Konflikt wycofuje całą transakcję danej planszy i trafia do raportu. Aby
kontynuować za konfliktową partią, użyć jawnego `--after-sequence` z jej
ostatnim numerem. Konfliktowe plansze wymagają nowego preview i przeglądu;
nie wolno edytować SHA ani guardów w starym pliku. Wyjściowy raport nie może
nadpisywać wejściowego preview. Trwałym checkpointem są receipty w bazie.
Plansze zablokowane już w preview są jawnie raportowane w `skippedBlocked`;
ich obecność oraz konflikty apply powodują kod zakończenia 2.

## Liczniki i ograniczenia

Apply deklaruje potrzebę kontroli liczników, ale jej nie uruchamia.
Po wszystkich 70 pokwitowaniach tego samego preview, w osobno zleconym
kroku danych uruchomić:

```powershell
.venv\Scripts\python.exe scripts\reconcile_partial_board_symbol_review.py rebuild-counts --preview artifacts\partial-board-review\pilot70-preview.json --preview-sha256 $preview.previewSha256 --limit-batches 1 --batch-size 5000 --output artifacts\partial-board-review\counts-batch.json
```

Powtarzać ograniczoną komendę do `complete: true`. Wznowienie korzysta
z trwałego kursora, nie rozpoczyna odbudowy od nowa. Jeśli aktualne liczniki
mają już prawidłowy marker v2, komenda kończy się bez skanowania. Wywołuje
istniejące `start_count_rebuild` / `rebuild_count_projection_next_batch`.
Każda partia ma własną transakcję, domyślnie 5000 rekordów, maksymalnie
10000; jedna komenda dopuszcza najwyżej trzy partie. Współbieżna zmiana zakresu
unieważnia checkpoint i powoduje ponowne rozpoczęcie bez opublikowania
starych sum. Dopiero pełny wynik z `_semantics.version = 2` jest gotowy.
Nie zastępować go sumą samych 70 plansz: katalog gry jest szerszy.

Apply zachowuje ręczne symbole, oznaczenia i zatwierdzenia; jeśli wspólny
writer nie potrafi zachować konkretnej decyzji, cała plansza zostaje
wycofana i zgłoszona. Nie zmienia manifestów, nie wykonuje ponownego
rozpoznawania ani treningu. Nie renderuje cropów i nie fabrykuje checksum.

## Audyt innych gier po odebranym pilocie

```powershell
.venv\Scripts\python.exe scripts\reconcile_partial_board_symbol_review.py audit --game-id <UUID-gry> --limit 25 --after-sequence 0 --output artifacts\partial-board-review\audit-page.json
```

Następną stronę wyznacza `nextAfterSequence`. Limit wynosi najwyżej 50
plansz; każda ocena używa tych samych zasad właściciela, źródła i geometrii.
Przed przejściem do następnej strony zachować raport. Dalszy zakres apply
wymaga wskazania i osobnego zlecenia; komenda apply jest przypięta do pilota.
