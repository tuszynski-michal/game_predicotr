---
title: Image selection acceptance
status: pending_owner_acceptance
last_updated: 2026-08-03
---

# Odbiór selekcji zdjęć 0.4

## Decyzja techniczna

`ready`

Profile smoke, 10 000 i 30 000 przeszły kontrolowany benchmark na komputerze
właściciela. Pomiar uruchamiał produkcyjny tani skan JPEG, miniatury, geometrii i
fingerprintu, a niezależne adnotacje deterministyczne dostarczały oczekiwane
granice, zakresy i bezpieczne reprezentanty. Sparse range verification było
liczone, ale nie ładowało prywatnego modelu OCR; jego liczba wyniosła dokładnie
`grupy × top-k`, a nie liczbę wszystkich zdjęć.

| Profil | Czas selektora | Limit | Przepustowość | Peak RSS delta | Wynik |
|---|---:|---:|---:|---:|---|
| smoke / 240 | 6,11 s | 120 s | 39,28 pliku/s | 17,6 MiB | pass |
| 10 000 | 252,51 s | 900 s | 39,60 pliku/s | 76,2 MiB | pass |
| 30 000 | 792,43 s | 2700 s | 37,86 pliku/s | 194,0 MiB | pass |

Każdy profil uzyskał `groupingPrecision = 1`, `groupingRecall = 1`,
`automaticSelectionPrecision = 1`, pełne coverage i zero fałszywych scaleń.
Checksum całego źródłowego inventory był identyczny przed i po każdym
przebiegu. Fixture i proces były objęte twardym timeoutem oraz cleanupem; nie
pozostał katalog roboczy ani częściowy manifest.

Raporty maszynowe:

- `image-selection-smoke-report.json`,
- `image-selection-10000-report.json`,
- `image-selection-30000-report.json`,
- `image-selection-acceptance-report.json`.

## Odbiór właściciela — oczekuje

TASK-0157 pozostaje otwarty wyłącznie do krótkiego odbioru zachowania produktu.
Nie należy powtarzać benchmarków 10k/30k.

1. Uruchom lokalny PostgreSQL, API, worker i Admin, a następnie wybierz szkic lub
   aktywną grę.
2. W `Selekcji zdjęć` wskaż mały folder JPEG, rozpocznij run i potwierdź, że
   postęp oraz końcowe liczniki są czytelne.
3. Jeżeli są wyjątki, potwierdź, że główna akcja
   `Kontynuuj z wybranymi zdjęciami` nie wymaga wpisania numerów ani JPEG-a,
   pomija nierozpoznane zestawy i wznawia ten sam job.
4. Opcjonalnie otwórz ręczne uzupełnienie. `ArrowLeft` i `ArrowRight` mają
   wyłącznie nawigować, a `Enter` zapisać dokładnie jedną decyzję. Techniczne
   `#N` nie może być jedyną informacją o wyjątku.
5. Po opublikowaniu outputu kliknij `Zapisz wybrane zdjęcia do folderu`, wskaż
   katalog i potwierdź nazwy `seq_<start>-<end>.jpg`, np. `seq_1-9.jpg`.
   Folder wejściowy musi pozostać bez zmian. Backend mapuje także starsze
   wewnętrzne nazwy content-addressed na ten publiczny format; nie wolno w tym
   celu przepisywać istniejącego manifestu.
6. Użyj `Przekaż do Importu layoutów`. Import ma otrzymać to samo,
   zweryfikowane źródło, ale nie może rozpocząć ciężkiego pipeline'u bez
   osobnego kliknięcia `Rozpocznij import`.

Po potwierdzeniu tych punktów status zmienia się na `accepted`, TASK-0157 można
przenieść do `completed/`, a wersję 0.4 zamknąć. TASK-0076 pozostaje osobno
zablokowany do bramek dużych rzeczywistych danych i `massImportAllowed` w 0.5.
