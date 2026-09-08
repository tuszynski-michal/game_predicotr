---
title: Resumable legacy game deletion
status: active
last_updated: 2026-09-08
---

# TASK-0516 — instrukcja utrzymaniowa

Mechanizm dotyczy wyłącznie `777 v0.1`, UUID
`80f3c7ec-6110-4e20-a263-2675ee5b15d6`. Chroniona gra `new-siedem`:
`03d64bfe-4d29-47dd-9153-76bd99b3b5d9`. Nie jest to ogólny endpoint Admina.

## Przed wykonaniem

1. Osobno zatwierdzić preview TASK-0517 oraz okno wdrożenia migracji.
2. Sprawdzić miejsce na indeksy, WAL i czasowe kopie. 0104 buduje 136 prefiksów
   indeksów; rozmiar zależy od aktualnych tabel. Nie deklarować kosztu bez pomiaru.
3. Zastosować 0103/0104 wyłącznie przez Alembic. Każdy indeks 0104 ma własny
   concurrent commit, statement timeout 120 s i lock timeout 2 s. Nie zwiększać
   timeoutu automatycznie po błędzie. Ustalić przyczynę, pojemność i okno pracy.
4. Zachować istniejące `artifacts/legacy-chat-search/777-v0.1-layouts.sqlite3`.
   Uszkodzone, niepełne lub zmienione archiwum blokuje wykonanie. Nie zastępuj go
   fikcyjnym plikiem, pustym archiwum ani nową deklaracją liczby rekordów.
5. Upewnić się, że legacy nie ma aktywnych jobów. Nowa komenda nie zatrzymuje ich.

## Preview i wznowienie

PowerShell, katalog główny repozytorium (komenda domyślnie tylko czyta):

```powershell
.venv\Scripts\python.exe scripts\delete_legacy_game_resumable.py
```

Przy pierwszym preview zawartość archiwum jest porównywana strumieniowo z bazą.
Przed aktywacją fence porównanie jest powtarzane pod blokadą. Kolejne preview
wymagają tego samego archiwum i receiptu; nie wymagają już usuniętych rekordów.

Dopiero po osobnym potwierdzeniu aktualnego preview:

```powershell
.venv\Scripts\python.exe scripts\delete_legacy_game_resumable.py `
  --execute `
  --expected-preview-sha256 "<sha256 z aktualnego preview>" `
  --confirmation "DELETE 777 v0.1 80f3c7ec-6110-4e20-a263-2675ee5b15d6; PRESERVE new-siedem" `
  --max-steps 100
```

Komenda kończy invokację po najwyżej 100 krokach lub osiągnięciu 90 s między
transakcjami. Bieżąca transakcja jest ograniczona do 30 s; ograniczone retry może
wydłużyć końcówkę invokacji. Wykonać ponownie tę samą zatwierdzoną komendę, aby
wznowić. Nie jest to serwer ani monitor. Nie interpretować wyjścia 0 jako końca
całego purge: sprawdzić raportowany status i etap.

`failed` przechowuje konkretny kod i nie usuwa checkpointu. Lock/statement timeout
oraz deadlock mają najwyżej trzy próby z mniejszą porcją. Blokada zapisów legacy
pozostaje po błędzie; nie usuwać receiptu, żeby ją ominąć. `database_done` jest
atomowo zapisywane wraz z usunięciem rekordu gry. Utrata odpowiedzi po commicie
nie cofa wykonanej pracy ani nie podwaja liczników.

## Pliki i granice zakresu

Dziennik `game_deletion_batches.asset_references` zawiera kandydatury ścieżek,
checksum i wspólnych execution keys. Komenda nie wykonuje fizycznego GC,
`VACUUM FULL`, kasowania źródeł operatora ani kompaktowania VHDX. Uwolnione miejsce
w PostgreSQL nie oznacza automatycznego zmniejszenia pliku dysku WSL.

Przed późniejszym GC trzeba ponownie sprawdzić własność, współdzielone referencje
i katalogi dozwolone. Nie wolno bezpośrednio kasować ścieżek z journalu.
`C:\Users\user\Documents\777`, archiwum SQLite i dane `new-siedem` są chronione.
`game_data_v2`, partycje oraz migracja nowej gry należą do kolejnych zadań.
