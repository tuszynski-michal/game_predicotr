---
title: Legacy game cleanup inventory
status: inventory_complete_cleanup_blocked
last_updated: 2026-09-07
---

# Inwentarz odchudzenia starej gry

## Zakres

Raport został wykonany wyłącznie odczytowo dla przypiętych tożsamości:

- stara gra: `80f3c7ec-6110-4e20-a263-2675ee5b15d6`, `777`, `777 v0.1`;
- chroniona gra: `03d64bfe-4d29-47dd-9153-76bd99b3b5d9`, `new-siedem`, `777`;
- zakres przeznaczony do późniejszego usunięcia: `1–45162`;
- katalog operatora `C:\Users\user\Documents\777` nie był skanowany ani
  modyfikowany.

Kanoniczny raport maszynowy ma fingerprint
`2250d49f71cd937218222dae3dd62f108ffd7cc5992f3eb4a315a69ad19d19e4` i
znajduje się w `legacy-game-cleanup-preview-2026-09-07.json`.

## Wynik bazy

- Wykryto 7 769 571 rekordów starej gry w tabelach posiadających bezpośrednie
  `game_id`.
- Największa grupa to 6 304 230 komórek `image_symbol_review_cells`.
- `image_review_items` zawiera 580 105 rekordów, a obie projekcje wyszukiwania
  po 414 705 rekordów.
- Stara gra nie ma jobów w aktywnych statusach `created` lub `processing`.
- Inwentarz schematu objął 193 relacje FK oraz 36 kolumn ścieżek. Zależności
  bez bezpośredniego, rozstrzygniętego właściciela są jawnie `blocked`, a nie
  domyślnie uznane za dane do usunięcia.

Cała bieżąca baza zajmowała podczas odczytu 44 851 844 799 bajtów. Jest to
rozmiar źródła kopii bazy, a nie prognoza rozmiaru skompresowanego backupu.

## Zakresy wyszukiwania plansz

| Zakres | Klasyfikacja | Dokumenty |
|---|---|---:|
| `1–45162` | `delete` po osobnym zatwierdzeniu cleanupu | 45 151 |
| `45163–499995` | `preserve` przez migrację do archiwum | 369 554 |

Jedenaście numerów w pierwszym zakresie nie ma bieżącego fast documentu; plan
nie zakłada sztucznego uzupełniania tych pozycji. Dla zachowywanego zakresu nie
wykryto brakujących linków review, linków plansz, ścieżek ani rozbieżności
checksum w metadanych.

## Pełna kontrola obrazów

Skrypt odczytał każdy z 369 554 zachowywanych plików i przeliczył SHA-256:

- obecne i zgodne: 369 554;
- brakujące lub niebezpieczne ścieżki: 0;
- niezgodne checksumy: 0;
- łączny rozmiar: 25 989 394 598 bajtów, około 24,2 GiB.

Minimalna przestrzeń przejściowa na niezależną kopię obrazów archiwum wynosi
więc 25 989 394 598 bajtów. Przed destrukcyjnym etapem nadal jest wymagana
spójna kopia PostgreSQL oraz ponowne wygenerowanie preview.

## Blokada dalszego cleanupu

Jedyną blokadą końcową jest `ARCHIVE_MIGRATION_REQUIRED`. Dzisiejsze wyniki
wyszukiwania rozwiązują obraz przez operacyjne rekordy `image_review_items` i
`recognized_boards`. Najpierw trzeba zbudować niezależne archiwum zawierające
symboliczny dokument wyszukiwania, obraz całej planszy i checksumę. Dopiero po
jego pełnym odbiorze wolno klasyfikować operacyjne review, cropy symboli,
modele, stagingi i raporty starej gry jako zasoby do fizycznego usunięcia.

Preview nie jest zgodą na cleanup. Wymaga niezależnego review w
`gpt-6-astra high`, a wykonanie usunięcia wymaga osobnego preview i jawnego
potwierdzenia użytkownika.

## Polecenie odtworzenia

```powershell
$env:PYTHONPATH = 'services/api/src;.'
.venv\Scripts\python.exe scripts\preview_legacy_game_cleanup.py `
  --output ai_docs\quality\legacy-game-cleanup-preview-2026-09-07.json `
  --file-workers 8 `
  --quiet
```

Polecenie nie wykonuje DML, DDL, migracji, restartu ani skanowania katalogu
operatora.
