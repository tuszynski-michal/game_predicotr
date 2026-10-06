---
title: Mumie — current approvals, iteration 5 and the human review boundary
status: active
last_updated: 2026-10-05
---

# TASK-0850 — wynik pracy na 31 zatwierdzonych zdjęciach

## Wykonany zakres

Operator zlecił pracę do pierwszej potrzebnej interakcji. Wykonano brakujące
doszkolenie na 11 nowych zatwierdzeniach, domknięto jego ocenę, sprawdzono
wcześniejsze wyniki obu folderów i przygotowano aktualne wycinki. Nie
utworzono ani nie importowano plansz w głównej grze Mumie.

Run `5bc981568c3f42bd96f6f9238e57aedc`, iteracja/próba 5, preset F,
dotychczasowy budżet 14 400 s. Wejście: rewizja 591, 31 kompletnych zdjęć,
25 treningowych i 6 odłożonych. Dotychczasowe przydziały 20 źródeł zachowane;
11 nowych dodano według istniejącej reguły, bez `--allow-same-data`.

Eksport wejścia `3f26e0db75abb283f232c1a9b414d869da4f3a80c6667792809b2940b493670a`,
snapshot iteracji `c0d5666b10de5226f677f242a5fbd8c2d7121baef1d9763a736b44ae17750fbf`.
Trening GPU: 900,75 s, 1831 kroków; zużycie runu 4718,62 s, pozostało 9681,38 s.

## Ocena i zachowanie modelu

| Stan | Mumie image-macro, mniej = lepiej | Poprawne kompletne zdjęcia | Strażnik 777 |
|---|---:|---:|---|
| Początkowy | 0,0022076230 | 6/6 | Dotychczasowy model |
| Kandydat 1 | 0,0024969857 | 6/6 | PASS |
| Kandydat 2 | 0,0025462181 | 6/6 | PASS |
| Kandydat 3 | 0,0025018425 | 6/6 | PASS |

Każdy kandydat był gorszy od stanu początkowego na tych samych sześciu
zdjęciach. Reguła F zachowała poprzedni model:
`previous_state_kept_no_holdout_improvement`. Brak nowego ONNX, nowych
propozycji lub aktywacji. Nie wykonano iteracji 6.

Wszystkie 99 plansz z 11 nowych zdjęć człowiek przyjął bez zmian propozycji
iteracji 3. To zatwierdzenia operatora, ale nie niezależny dowód trafności
ani zbiór przykładów wcześniej błędnego cięcia. Nowe liczności holdoutu
uniemożliwiają bezpośrednie porównanie jego średniej z iteracją 4.

Oba wcześniejsze testy folderów pozostają aktualne: po 200 unikalnych
zdjęć folderu oraz 11 osobnych kontroli, 211 wyników każdego modelu na
folder. Zweryfikowano modele, źródła i zapisane wyniki w nowych procesach;
nie powtarzano inferencji, skoro nowy model nie powstał. 400 zdjęć nie ma
niezależnych referencji, więc nie podaje się na nich accuracy.

## Komórki, słownik i faktyczna blokada

Nowy create-only pakiet:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-current-approvals-20261005\batches\a427bdd2076fd6a271edbded961af427d2ffb288b99db2debd08f0f731ee1ed9`.

Zawiera 236 zdjęć z nakładkami, 31 complete, 205 pending, 4185 wycinków
wyłącznie z kompletnych zdjęć, partie 50/50/50/50/36. Wszystkie 225 plików
znanego folderu pasują SHA do katalogu. Wycinki nie otrzymały klas ani
etykiet złotej ramki. Sprawdzono wszystkie opublikowane sumy kontrolne.

Laboratoryjna gra `local-7a0650634c7a607f30c93774` ma zatwierdzony słownik v1:
10, J, Q, K, A, Ra, Sarkofag, Mumia, Faraon, Sfinks. Magazyn symboli:
rewizja 46, 706 historycznych decyzji wszystkich gier; **zero decyzji dla
obecnych 31 zdjęć**. Definicje 10 symboli w Adminie nie są etykietami cropów.

Zbudowano istniejący UI laboratorium i uruchomiono nowe procesy 8102/3102.
HTTP stron i słownika działał. Poczekalnia oraz podgląd aktualnych komórek
są jednak blokowane przez `HOLDOUT_POLICY_UNRESOLVED`:

- Dawny split `lab-geometry-whole-game-pilot-v1` jest `split_stale=true`
  po korektach geometrii. To udokumentowane zachowanie, nie brak symboli.
- `symbol_labels.holdout_reason` odrzuca nieaktualną politykę przed
  pokazaniem pikseli. Nie wyłączono tej ochrony ani nie ustawiono stale=false.
- Drugi freeze jest zabroniony, a rebase jawnie odrzuca split, rodziny,
  kwalifikacje oraz assisted photos. Nie użyto go jako obejścia.
- Potrzebny jest jawny kontrakt nowej wersji zbioru. Draft:
  `ai_docs/delivery/MUMIE_SYMBOL_DATASET_VERSION_20261005.md`.

Nie przedstawia się panelu etykiet jako gotowego. Po diagnostyce zatrzymano
wyłącznie nowe, własne procesy 8102/3102 i przywrócono istniejącą stronę
8105 z tą samą rewizją 591 i tymi samymi 31/236 zatwierdzeniami.
Root PID 42788, tożsamość i logi w artefaktach tego zadania.

## Interakcja potrzebna do następnego zakresu

Wysłano pytanie, czy foldery `1 - 23175 cut` i `481537- 500000 cut`
pochodzą z jednego nagrania. Wszystkie 31 obecnych zdjęć ma zachowane
deklaracje rodzin z provenance `unresolved`. Nie oznaczono ich jako verified.
Różne foldery i różne zakresy sekwencji nie potwierdzają niezależnych filmów.

Przed implementacją nowej wersji trzeba zaakceptować jej kontrakt i ustalić
pochodzenie. Potem człowiek przypisuje symbole do przygotowanych wycinków
oraz osobno ocenia złote ramki. Brak etykiet blokuje trening klasyfikatora;
brak pochodzenia blokuje wiarygodny niezależny test symboli.

Działająca korekta geometrii: `http://127.0.0.1:8105`.
Zachowane porównanie obu folderów: `http://127.0.0.1:8108/review.html`
oraz `http://127.0.0.1:8108/second-481537-500000/case-review.html`.

## Weryfikacja i ograniczenia

- Nowy proces potwierdził: niezmieniony fingerprint widoku anotacji
  `0986dec898bbbd9bbb97e7ae8ed8f18ea1e5d5b286a3772b24b902a0ae6503e0`,
  wszystkie dawne role, niezmienione decyzje symboli, iterację 5 `done`.
- GET preview danych głównej gry: 10 symboli, 0 layouts, 0 source_images,
  0 recognized_boards, 0 dataset_versions. Wykonano tylko odczyt preview.
- Build istniejącego Vision Lab UI i jego kontrola TypeScript: PASS.
  Pozostaje wcześniejsze ostrzeżenie Next o dwóch lockfile'ach; bez zmiany
  konfiguracji innych aplikacji.
- Testy reguł fine-tune, eksportu Mumii i folderów: 31 PASS (32,59 s).
  Środowisko treningowe nie ma pytest; użyto istniejącego środowiska testowego.
- Nie modyfikowano kodu aplikacji ani kontraktu API. Nie wykonywano DB writes,
  migracji, importu/materializacji, shadow, aktywacji, push lub merge.

Źródło dowodów:
`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-current-approvals-20261005`:
input-audit, source-provenance-audit, ledger-before, iteration5-report,
final-verification, main-game-empty-read oraz logi kontrolowanych procesów.
