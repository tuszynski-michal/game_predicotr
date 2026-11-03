# TASK-1125 — audyt Opus 5.5

Metoda: celowany przegląd statyczny po pierwszym timeout 450 s bez werdyktu. Model żądany: claude-opus-5-5; reasoning: high. Modele raportowane przez CLI: claude-opus-5-5. Narzędzia wyłącznie Read/Glob/Grep, MCP wyłączone, limit 480 s; brief 5,6 KB, maksymalnie 16 celowanych odczytów. Zakres i ograniczenia poniżej są częścią raportu audytora.

# Audyt TASK-1125 (A2, readability): przegląd statyczny, Opus 5.5 / high

**Werdykt: PASS.** Nie znalazłem żadnego potwierdzonego błędu P0/P1. Część obszarów nie została sprawdzona i jest wypisana w sekcji „Ograniczenia zakresu” poniżej.

## Co sprawdziłem i wygląda poprawnie

- **Tożsamość wycinka:** `domain/symbol_readability.py:35-62`. `crop_identity` obejmuje source, sha, geometrię, crop, render spec, piksele i render v2, ale nie revision ani nazwę. `identity_is_current` wymaga, żeby geometria była aktualną geometrią planszy i żeby status nie był `rejected`. SQL w `_refresh_stale` (`storage/symbol_readability.py:380-407`) sprawdza te same pola.
- **Selekcja:** `readability_selection.py:53-89`.
  - TEST jest wybierany jako pierwszy, przed etykietami. Kwoty wynoszą po 60 na warstwę, co daje 120/120/360.
  - Ekspozycja na bazę jest blokowana w obu kierunkach: przez aliasy source/sha/rgb do rodzin bazy i przez nagrania.
  - Gdy brakuje danych, jest STOP bez dobierania próby.
  - Audit200 (`workflow.py:389-433`) wyklucza: bazowe TRAIN/VAL, źródła, sha i rgb pilota, klucze rodzin pilota, nagrania wystawione na TRAIN/VAL, `quality_issue`, a także rgb, które wcześniej dostało etykietę.
  - Worker przy fit dodatkowo sprawdza nagrania (`workflow.py:818-828`).
- **Confidence:** `readability_confidence.py:44-107`.
  - Manifest i kalibracja są wiązane po SHA: dataset, klasy, checkpoint i wersja kalibracji. Brak pliku daje `None`, czyli nie jest importowana historyczna pewność.
  - Liczenie idzie przez `eval()` i `inference_mode`, w partiach po 128.
  - `top1` trafia tylko do `snapshot.quality_top1`. Kandydat skanu i `reasons` są liczone wyłącznie z `artifact.score(features)` (`workflow.py:608-629`).
- **Przetwarzanie źródła:** `workflow.py:520-702`.
  - Na każde źródło przypada jedna transakcja. W niej następują po kolei: blokada komórki, ponowne sprawdzenie tożsamości, zapis wyników, `fence` i potem receipt.
  - Checkpoint jest robiony po commicie, więc ponowienie jest idempotentne (warunek `NOT processed`).
  - 135 pól daje dwa wywołania modelu: 128 + 7.
- **Komendy:** `storage:151-192`. Blokada advisory, sprawdzenie SHA polecenia, akcja i wstawienie receiptu dzieją się w jednej transakcji. Utrata odpowiedzi zwraca wcześniej zapisany wynik.
- **Etykiety:** `storage:409-494`.
  - `readable` nie dotyka `quality_issue` ani nie zatwierdza symbolu.
  - `unreadable` używa `mark_unreadable` tylko wtedy, gdy problem nie jest jeszcze ustawiony.
  - Sprawdzane są `expected_identity`, revision oraz aktualność wycinka.
- **Fit i akceptacja:**
  - Revision pilota jest sprawdzana dwa razy: na starcie i pod blokadą po treningu (`workflow.py:787, 847-862`).
  - Akceptacja wymaga PASS, aktualnej revision i braku `stale` (`storage:317-353`).
  - Skan wymaga akceptacji, `fullScanAllowed` i zgodnej revision (`storage:201-211`, `workflow.py:184-194`).
- **Filtr `page()`:** `storage:517-522`. `overlap` filtruje po `overlap=true` lub `overlap_score`, a `unreadable` po `state='unreadable'` lub `unreadable_score`. Filtry są rozdzielone i poprawka leada jest semantycznie poprawna.
- **Migracja:** `0172`.
  - Mechanika jest kompletna: RLS z FORCE na rodzicu i partycjach, granty, FK z `RESTRICT`, manifest v20 kopiowany z v19 i downgrade.
  - W worktree jest jeden head (`0172` → `0169`). Preflight względem main (`0171`) jest znany i nadal otwarty.

## P2 (najwyżej 5)

1. **Artefakt fit zapisywany przed `fence` pod stałą ścieżką:** `workflow.py:841-847`. Ścieżka to `data/readability/{game}/{id}.json` i nie zależy od zawartości.
   - **Scenariusz:** worker A traci lease w trakcie treningu. Worker B kończy fit i zapisuje fingerprint. Potem A robi `os.replace` na tę samą ścieżkę i dopiero wtedy `fence` go odrzuca.
   - **Skutek:** jeśli trening nie jest bitowo deterministyczny, `load_artifact(expected_fingerprint)` przy skanie się nie powiedzie. To błąd zamknięty (fail-closed), ale zaakceptowany model staje się nieużywalny.
   - **Zalecenie:** ścieżka adresowana fingerprintem albo zapis pliku dopiero po udanym `fence`.
   - **Test:** dwa fity z wygasłym lease; po zakończeniu fingerprint pliku musi być równy wartości w DB.
2. **Skan nie sprawdza `stale` pilota po akceptacji:** `storage:203-207`, `workflow.py:186-191`. `_refresh_stale` nie podbija revision runu, więc zmiana pikseli pilota po akceptacji nie blokuje startu skanu. Akceptacja i fit to sprawdzają, start skanu nie.
   - Trzeba rozstrzygnąć, czy kontrakt „zmiana crop unieważnia” obejmuje też blokadę skanu.
   - **Test:** akceptacja, potem zmiana geometrii komórki pilota, potem start skanu. Oczekiwany wynik musi zostać jawnie ustalony.
3. **Dekoder przy błędnym źródle:** `workflow.py:580-605`. Gdy `loader.load` rzuca wyjątek, `frame` zostaje `None` i każde kolejne pole tego źródła dekoduje plik od nowa (do 135 razy). Narusza to zasadę „decoder raz/source” na ścieżce błędu. To nie jest błąd danych.
   - **Test:** uszkodzone źródło ze 135 polami; `load` ma być wywołany jeden raz, a wszystkie pola mają mieć stan `error`.
4. **Kolejność blokad między etykietą pilota a trwającym skanem:**
   - `label` blokuje komórki w kolejności `cell_id` (`storage:421-424`).
   - Skan blokuje te same komórki (pilot jest podzbiorem skanu) w kolejności `sequence_number, cell_index` (`workflow.py:545, 562`).
   - Etykieta, która obejmuje co najmniej dwie komórki ze źródła właśnie przetwarzanego przez skan, może dać deadlock w PostgreSQL (40P01). Kończy się to rollbackiem, ale nie sprawdziłem, czy worker traktuje to jako ponowienie, czy jako błąd joba.
   - **Test:** równoległa etykieta i skan tego samego źródła; job ma przetrwać.
5. **`GET page()` wykonuje zapis:** `storage:508`. Wywołuje `_refresh_stale`, czyli UPDATE wszystkich kwalifikujących się pozycji runu, bez wcześniejszych blokad komórek i runu. To ta sama klasa ryzyka co punkt 4, z workerem w trakcie przetwarzania źródła. Dodatkowo `stale` nadpisuje `state` i `overlap` oznaczonej pozycji (`storage:383-384`). Nie potwierdziłem, czy wcześniejsza etykieta jest zachowywana gdzie indziej; jeśli nie, koliduje to z zasadą „historii nie nadpisywać”. To nie jest potwierdzony błąd.

## Ograniczenia zakresu (niesprawdzone, więc bez założenia PASS)

- `readability_detector.py` i `readability_cohort.py`:
  - nie wiem, czy `train_detector` nie używa `top1` jako filtra. Widziałem tylko trafienia grep w `cohort.py:218` i `detector.py:382`, bez kontekstu;
  - nie sprawdziłem bramki kompletności etykiet przed fit: ani API, ani worker nie odrzucają pozycji `pending` (`unreadable=None`); weryfikacja zależy od `evaluate_pilot`.
- `SNAPSHOT_SQL`: nie potwierdziłem, że do pełnego skanu wchodzą też komórki approved i pewne.
- Synchronizacja `storage/symbol_readability_jobs.py` i `worker/jobs/store.py`, routery i schematy API.
- UI: przeczytałem tylko `readability-state.ts:7-91` (outbox w `localStorage`, jedno miejsce na grę, pełne `expectedIdentity`/`expectedRevision`). Nie przeczytałem `retryPending` w `readability-workspace.tsx`.
- Migracja `0172`: przejrzałem tylko wyniki grep. Nie czytałem pełnych definicji kolumn ani indeksów.

Wykorzystałem 16 wywołań Read/Grep/Glob, bez uruchamiania testów i usług.

przegląd statyczny, bez zmian w plikach

## Rozliczenie wykonawcy po audycie — jedna runda P2

Oryginalny PASS i pięć uwag audytora powyżej pozostają bez zmian. Wykonawca
zamknął P2-1 adresowaniem fingerprintem i unikalnym tempem (także długie ścieżki
Windows), P2-2 ponowną kontrolą stale przed nowym skanem, P2-3 cache błędu
źródła, P2-4 wspólną EXCLUSIVE sequence ownership lock przed rowlocks.
Dla P2-5 potwierdzono zachowaną historię w commands.response.command oraz jawny
WRITE intent lazy-stale; ta sama blokada chroni go przed konfliktem z writerami.

Testy: opóźniony writer nie nadpisuje innego fingerprintu; uszkodzone źródło135
pól jest czytane jeden raz; label czeka na source transaction i kończy się po
skanie bez deadlocku; zmiana geometrii pilota po odbiorze blokuje nowy skan.
Pełne wyniki są w Outcome TASK-1125. Nie wykonano drugiego merytorycznego audytu
po poprawkach P2; pierwsza próba bez werdyktu i celowana alternatywa są jawnie
opisane w metodzie raportu.
