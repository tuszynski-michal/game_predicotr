---
title: Local manual image selection architecture
status: accepted
last_updated: 2026-08-18
---

# Architektura lokalnej ręcznej selekcji

Workspace React działa wyłącznie w przeglądarce Admina. `showDirectoryPicker`
udostępnia dwa uchwyty File System Access API: źródło tylko do odczytu oraz
folder wynikowy z prawem odczytu i zapisu. Rekurencyjne listowanie i naturalne
sortowanie są czystą logiką w `manual-image-selection.ts`. Indeks przechowuje
uchwyty i ścieżki bez otwierania wszystkich Blobów. Workspace utrzymuje
ograniczony cache Object URL dla bieżącego JPEG-a i trzech sąsiadów z każdej
strony, wywołuje `decode()` jako read-ahead oraz zwalnia URL-e poza oknem.

Sesje są przechowywane w osobnej bazie IndexedDB
`game-predictor-manual-image-selection`, w magazynie `sessions` z kluczem
`gameId`. Rekord obejmuje uchwyty folderów i serializowalny stan decyzji, więc
nie wymaga migracji backendowej ani tabel domenowych. Wersja 2 bazy dodaje
magazyn `traceEvents` z kluczem złożonym `(gameId, sessionKey, eventIndex)`;
migracja zachowuje istniejące sesje i uchwyty folderów. LocalStorage służy tylko
do szybkiego odtworzenia kursora diagnostycznego.

Workspace zapisuje dwa jawne artefakty przez wybrany uchwyt folderu wynikowego:
kompaktowy `manual-image-selection-output-v1.json` oraz, na żądanie operatora,
`manual-image-selection-trace-v1.json`. Manifest wyjściowy jest synchronizowany
po każdym Enterze, Tabie i Ctrl+Z, natomiast pełny ślad jest materializowany
poza ścieżką krytyczną sesji. Każdy zapis sprawdza właściciela `sessionKey`, aby
nie nadpisać artefaktu innej sesji.

W aktywnej sesji globalny handler klawiatury obsługuje `Enter`/`F` jako
zatwierdzenie oraz `Ctrl+Z`/`A` jako cofnięcie. Handler ignoruje pola edycyjne,
selecty, przyciski i elementy `contenteditable`, aby skróty nie przejmowały
interakcji formularza.

Zapis pliku jest atomizowany na poziomie uchwytu: źródłowy Blob jest kopiowany
bez transformacji, checksum SHA-256 jest porównywany z istniejącym plikiem,
zapis jest zamykany, a wynik jest odczytywany ponownie i weryfikowany. Usunięcie
przez undo wymaga zgodnego checksumu; plik obcy lub zmieniony nigdy nie jest
nadpisywany ani usuwany automatycznie.

Nie ma endpointu HTTP, joba, workera ani API/OpenAPI dla tego workspace'u.
Kontrakt serwerowy pozostaje właścicielem automatycznej selekcji i importu;
lokalny fallback zapisuje wyłącznie pliki przygotowane do późniejszego,
jawnego importu layoutów. Pełny ekran używa `requestFullscreen` na kontenerze
podglądu. Zoom oblicza rzeczywiste wymiary layoutu z naturalnego rozmiaru JPEG-a
i aktualnego viewportu, dzięki czemu pionowy scroll obejmuje cały obraz;
viewport ukrywa poziomy overflow i centruje nadmiar obrazu bez ingerencji w
Blob.
