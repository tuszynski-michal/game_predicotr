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
3. Otwórz kolejkę manualną. `ArrowLeft` i `ArrowRight` mają wyłącznie nawigować;
   `Enter` ma zapisać dokładnie jedną decyzję dla wybranego pliku.
4. Wskaż pojedynczy JPEG dla nierozwiązanej grupy, zatwierdź dodatni zakres,
   wróć do pozycji i potwierdź możliwość korekty przed publikacją.
5. Po rozwiązaniu wszystkich grup utwórz output i użyj `Przekaż do Importu
   layoutów`. Import ma otrzymać źródło, ale nie może rozpocząć ciężkiego
   pipeline'u bez osobnego kliknięcia.
6. Potwierdź, że nazwy `seq_<start>-<end>__<checksum>.jpg` są czytelne, a pliki
   w folderze wejściowym pozostały bez zmian.

Po potwierdzeniu tych punktów status zmienia się na `accepted`, TASK-0157 można
przenieść do `completed/`, a wersję 0.4 zamknąć. TASK-0076 pozostaje osobno
zablokowany do bramek dużych rzeczywistych danych i `massImportAllowed` w 0.5.
