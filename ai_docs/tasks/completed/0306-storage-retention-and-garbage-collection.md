---
title: TASK-0306 — Storage retention and garbage collection
status: done
last_updated: 2026-08-29
---

# TASK-0306 — Storage retention and garbage collection

## Goal

Ograniczyć wzrost lokalnego image storage, zachowując fail-closed ochronę
oryginałów, cropów z referencjami, modeli, danych treningowych, audytu oraz
artefaktów potrzebnych aktywnym jobom i retry.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

- deterministyczna polityka retencji 24 h i progi pressure per wolumin,
- normalizacja obrazu bez trwałych pełnowymiarowych PNG,
- trwały lifecycle browserowego stagingu po verified handoffie,
- preview oraz wznawialny GC z niezmiennym manifestem,
- capacity guard przed uploadem i jobami obrazowymi,
- panel Admina do inwentarza i jawnego czyszczenia,
- bounded kompakcja odtwarzalnych payloadów etapów PostgreSQL,
- kontrolowany pierwszy cleanup w trybie `observe_only`.

## Invarianty

- GC nie usuwa `data/originals`, referencjonowanych cropów, modeli, kohort,
  snapshotów, release'ów, eksportów audytowych ani danych ręcznej selekcji.
- Staging bez kompletnego, checksumowanego handoffu do managed originals jest
  chroniony.
- Artefakt zależny od joba `created` lub `processing` jest chroniony.
- Symlinki, ścieżki absolutne, traversal i ścieżki spoza zarządzanych rootów
  są blokowane.
- Kandydat zmieniony od preview nie jest usuwany.
- Pierwsze czyszczenie istniejących danych wymaga jawnego potwierdzenia.
- Nie uruchamiamy automatycznie `VACUUM FULL` ani kompaktowania VHDX.

## Plan commitów

1. `v0.9.16` — domena retencji i trwały model GC.
2. `v0.9.17` — normalizacja bez trwałych bitmap.
3. `v0.9.18` — bezpieczne wycofanie przejętego stagingu.
4. `v0.9.19` — trwały, wznawialny GC.
5. `v0.9.20` — capacity guard i automatyczny GC.
6. `v0.9.21` — panel pamięci i czyszczenia.
7. `v0.9.22` — kompakcja odtwarzalnego stanu pipeline'u.
8. `v0.9.23` — kontrolowany cleanup i odbiór.

## Outcome

TASK 1 wprowadza czystą domenę kwalifikacji, deterministyczny manifest/token,
`JobType.STORAGE_GC` oraz migrację `0076` z tabelami runów GC, snapshotów
inwentarza i trwałego stanu retencji stagingu. Fizyczne usuwanie pozostaje
poza tym commitem.

TASK 2 wprowadza `image-normalization-v2-in-memory-source-v1`. Nowe joby
przypinają wersję adaptera i zapisują tylko checksumę znormalizowanych pikseli;
pełnowymiarowy PNG nie jest tworzony. Brak snapshotu wersji oznacza historyczny
v1, który przy retry odbudowuje brakujący PNG z managed original i wymaga
identycznej checksummy.

TASK 3 utrwala lifecycle browser stagingu: finalizacja zapisuje `ready`, start
preflightu/importu zapisuje `in_use`, a worker zapisuje `ingested` i termin
retencji dopiero po checksumowanym handoffie wszystkich źródeł. Kopiowanie
poprzedza canonical/deferred filtering, więc rerun nie zależy od zachowania
browserowej kopii.

TASK 4 dodaje API preview/start/status i general-lane `storage_gc`. Manifest
jest content-addressed i zawiera dokładną obserwację każdego kandydata. Worker
ponownie sprawdza zależności i tożsamość źródła, przetwarza partie 250 ścieżek
lub 512 MiB, korzysta z same-volume trash i trwałych markerów recovery. Kod nie
uruchamia żadnego cleanupu automatycznie ani nie usuwa istniejących danych bez
jawnego, zgodnego preview.

TASK 5 dodaje konfigurowalny capacity guard. Upload jest oceniany stałoczasowo
per unikalny wolumin z konserwatywną estymacją 8× i marginesem 20%. Poniżej
60 GiB powstaje co najwyżej jeden automatyczny run GC, a operacja, która
naruszyłaby rezerwę 30 GiB, jest blokowana. Worker sprawdza miejsce pomiędzy
źródłami, zapisuje `waiting_for_storage`, oddaje lease i wznawia dopiero po
osiągnięciu celu 80 GiB. Job GC ma pierwszeństwo w general lane.

TASK 6 dodaje lokalny workspace `Pamięć i czyszczenie`. Bounded pomiar jest
trwałym, idempotentnym jobem `storage_inventory`; odczyt strony korzysta z
ostatniego snapshotu i nie skanuje synchronicznie milionów plików. Panel
pokazuje rozmiary przestrzeni, woluminy i presję, uruchamia dry-run oraz wymaga
jawnego potwierdzenia przed startem GC. Polityka nadal raportuje
`automaticDeletion = false`, ponieważ pierwszy cleanup nie został zatwierdzony.

TASK 7 dodaje migrację `0079`, wersjonowany manifest terminalny i osobny job
`storage_pipeline_compaction`. Dry-run jest keysetowy i zapisuje niezmienny
JSONL bez binariów. Wykonanie rewaliduje status, aktywne zależności, nierozwiązaną
geometrię oraz checksumy każdego etapu przed bounded usunięciem. Kompaktowane
są wyłącznie ciężkie payloady `board_cell_geometry`, `board_crops`,
`sequence_ocr` i `symbol_inference`; `board_detection` pozostaje dostępne dla
operacyjnych kolejek geometrii i kalibracji. Po partiach wykonywany jest tylko
`VACUUM (ANALYZE)`, nigdy `VACUUM FULL`. Operator uruchamia dry-run przez
`scripts/compact_image_pipeline_state.py preview`; start wymaga jawnej frazy i
checksummy dokładnie tego raportu. Na danych użytkownika wykonano wyłącznie
migrację schematu, bez kompakcji i bez usuwania payloadów.

Dry-run TASK 8 ujawnił, że serializowanie JSONB po stronie Pythona nie mieści
się w limicie operacyjnym 120 sekund. Migracje `0080–0081` włączają serwerowy
SHA-256 przez `pgcrypto` i manifest v2, dzięki czemu przez granicę procesu
przechodzą wyłącznie digesty i liczniki. Powtórzony dry-run zakończył się w
około 71 sekund i wskazał 25 899 wykonań, 89 639 payloadów oraz 3 095 375 375
bajtów logicznego JSON. Nadal nie uruchomiono destrukcyjnej kompakcji.

Pełny inwentarz zakończył się bez usuwania danych. Snapshot wskazał około
85 995 384 923 B w `working`, 65 904 043 884 B w chronionych cropach,
11 141 120 426 B w stagingu, 10 211 507 189 B w originals i
16 524 498 623 B logicznego PostgreSQL. Wznawialny skan zapisuje odtąd każdy
namespace osobno; niekompletny snapshot nie jest publikowany jako ostatni
gotowy pomiar.

Aktualny checksum-bound preview GC `9e67b906-b04f-48c7-9719-1d608ade7511`
kwalifikuje 39 515 historycznych bitmap normalizacji o łącznym rozmiarze
62 193 128 932 B. Chroni 13 073 obserwacje o rozmiarze 34 943 376 417 B.
W tej grupie 16 historycznych stagingów (11 141 120 426 B) nie ma trwałego,
zweryfikowanego handoffu, więc są jawnie raportowane jako chronione, a nie
pomijane. Pierwszy delete i kompakcja PostgreSQL nadal wymagają zgody
użytkownika; zgoda została następnie udzielona i wykorzystana wyłącznie dla
opisanych niżej manifestów.

TASK 8 wykonał zatwierdzony GC z preview
`9e67b906-b04f-48c7-9719-1d608ade7511`. Run usunął 39 514 z 39 515
kandydatów i odzyskał 62 191 682 889 B; jeden plik zmieniony po preview
pozostał na dysku jako konflikt, a liczba błędów wyniosła zero. Końcowy
inwentarz potwierdził niezmienione rozmiary originals, cropów, modeli, training
i stagingu oraz około 97,54 GiB wolnego miejsca.

Kompakcja PostgreSQL objęła 25 899 wykonań i 89 639 późnych payloadów o
logicznym rozmiarze 3 095 375 375 B. Powstało 25 899 terminalnych manifestów,
nie pozostał żaden disposable stage result dla tych wykonań, a końcowe
`VACUUM (ANALYZE)` zakończyło się bez błędu. Fizyczny rozmiar bazy nie został
zmniejszony przez `VACUUM FULL`; zwolnione strony pozostają dostępne do
ponownego użycia przez PostgreSQL.

Odbiór potwierdził działanie API kolejki geometrii, Weryfikacji Symboli oraz
checksum-bound assetu cropa. Historyczny plik z usuniętą bitmapą normalizacji
został odtworzony w pamięci z managed original z identyczną checksumą. Dwa
błędy pierwszego uruchomienia (pusty checkpoint kompakcji oraz wersja
checkpointu resumowalnego inwentarza) zostały naprawione i zabezpieczone
testami regresyjnymi. Po odbiorze domyślny `observe_only` został wyłączony;
można go nadal jawnie włączyć zmienną środowiskową.
