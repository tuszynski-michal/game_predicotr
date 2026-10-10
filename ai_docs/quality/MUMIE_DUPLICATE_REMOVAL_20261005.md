---
title: Accidental Mumie duplicate removal evidence
status: completed
last_updated: 2026-10-05
---

# Usunięcie omyłkowej gry Mumie — TASK-0849

Operator jawnie polecił zarchiwizować i usunąć utworzony przez siebie duplikat.
Wyłącznie `mumie-1`, UUID `12180d9f-6c1a-43a9-a480-4056d2da81a9`, został
zarchiwizowany i trwale usunięty 2026-10-05. Oryginalne `mumie` i `777`
pozostały bez zmian.

## Preview i wykonanie

Pierwszy preview: `draft`, magazyn `migrating`, 9/64 partycji, brak symboli,
zasad, jobów, danych partycji i ścieżek plików. Log tworzenia wskazał
`LockNotAvailable`; przy kontroli nie było już blokad parent. Wznowiono
istniejący receipt provisioning do 64/64 bez przestawiania statusów SQL.

DELETE Admin API dokładnego UUID zwrócił 204; GET potwierdził `archived`.
Preview po archiwizacji miał zero blockerów i jedną domyślną politykę geometrii
zapisaną przez provisioning. Żadnych zdjęć ani danych użytkownika.

`scripts/delete_archived_v2_game.py --execute` zweryfikował fingerprint
`81eb8dcf941dfd77dc02c18c436dff034a534b18eb064a9ca1d9c2106ce7cfaa` oraz
frazy potwierdzenia dokładnego code i UUID. Delete receipt
`d328ae9d-880d-43b0-8871-03054f482294` zakończył 64/64 kroków ze statusem
`done`. Każda partycja miała osobną transakcję; operacja trwała 12,70 s.

## Weryfikacja w nowym procesie

2026-10-05T12:46:40Z: PASS. Zero rekordów katalogu, magazynu, symboli, zasad,
jobów i partycji duplikatu. API odpowiada 404 `GAME_NOT_FOUND`; lista gier
zawiera wyłącznie oryginalne `mumie` i `7` (`777`). Oba receipts zakończone.

Snapshot katalogów, registry, liczby symboli i fingerprinty wszystkich jobów
oryginalnych gier przed operacją i po operacji są identyczne. Operacja nie
dotykała plików, więc źródłowe zdjęcia oraz 225 zdjęć wcześniejszego stagingu
Mumii są zachowane. Nie restartowano usług i nie anulowano cudzych transakcji.

Lokalny helper audytu wymagał agregowanego fingerprintu dla ponad 500 jobów
777 oraz poprawienia odczytu listy API. Są to poprawki narzędzia odczytu;
nie zmieniono implementacji produktu ani żadnego kontraktu.

## Artefakty

`C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-duplicate-removal-20261005\`:

- `initial-preview.json`: read-only preview, receipt, chronione snapshoty.
- `before-resume.json` i `provision-result.json`: kontrola i wznowienie.
- `archive-result.json` i `archived-game.json`: archiwizacja i odczyt.
- `ready-preview.json`: zakres zatwierdzonego trwałego usunięcia.
- `delete-result.json`: wynik istniejącego CLI.
- `verification.json`: wynik w świeżym procesie i katalog po usunięciu.

Limity całych kroków: odczyt 45 s, provisioning 90 s, archiwizacja 30 s,
usunięcie 120 s. SQL i HTTP mają własne krótkie limity. Brak timeoutów
wykonania i osieroconych procesów. Zachowano zastane zmiany dokumentacji
innych tasków; osobny commit zawiera wyłącznie dokumentację TASK-0849.
