---
id: TASK-0607
title: Responsywność i ergonomia kalibracji etykiet V7
status: done
owner: Codex
---

# TASK-0607 — Responsywność i ergonomia kalibracji etykiet V7

## Goal

Usunąć opóźnienie widocznego zaznaczania i przełączania zdjęć, uprościć oznaczanie oraz zmierzyć czas wyboru reprezentantów na rzeczywistych korpusach.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/delivery/V7_DYNAMIC_LABEL_VIEWPORT_V2_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md`

## User feedback to implement

1. Marker po kliknięciu pojawia się od razu po trwałym wpisie lokalnym, bez czekania na odpowiedź serwera; szybkie kolejne kliknięcia też pozostają widoczne.
2. Wybór pozycji 1–9, ocena cropa i checkbox zasłoniętego numeru są nad obrazem. Gotowość profilu jest poza główną ścieżką oznaczania.
3. Grupa ujęć to select `A/B/C`, nie pole dowolnego tekstu.
4. Podstawowa sesja wybiera pełne kadry. Trudne/przycięte/zasłonięte zdjęcia nie są automatycznie proponowane do podstawowej kalibracji.
5. Asset bieżący i sąsiady używają ograniczonego cache/prefetch w pamięci, bez blobów w IndexedDB; source drift pozostaje bezpiecznie wykrywany.
6. Benchmark raportuje osobno manifest/hash, decode, lokalizację/OCR, finalizację i zapis dla 100/300/500 niezależnych źródeł. Brak wystarczającej liczby plików daje `not_evaluable`.

## Scope and safety

Trwała kolejka serwera zachowuje kolejność i idempotency; optymistyczny marker nie jest potwierdzoną anotacją. Zmiana źródła, konflikt, porzucenie kolejki oraz restart muszą usunąć lub odtworzyć wyłącznie lokalne zamiary zgodnie z dotychczasową polityką. Nie utrwalać obrazów, ich ścieżek ani binariów w IndexedDB.

## Acceptance criteria

- [x] Interakcje z zaznaczeniem nie czekają wizualnie na HTTP, a kolejka po reloadzie nadal zachowuje porządek.
- [x] Interfejs realizuje wszystkie sześć punktów feedbacku powyżej.
- [x] Cache ma ograniczenie liczby/rozmiaru oraz nie omija serwerowej kontroli tożsamości źródła.
- [x] Benchmark nie używa holdoutu i nie powiela obrazów dla wyniku 500.
- [x] Testy obejmują opóźnioną pierwszą odpowiedź, szybkie dwa kliknięcia, reload, zmianę assetu i pusty wariant benchmarku.

## Outcome

Wykonano. Nowa sesja domyślnie wybiera wyłącznie `small_777`; materiał
zasłonięty jest opcjonalnym, jasno oznaczonym testem trudnym. Marker powstaje
po trwałym wpisie lokalnym, przed HTTP, lecz nie liczy się do server-confirmed
readiness. Grupa ma zamknięty wybór `A/B/C`, a checkbox niedostępnego numeru
jest obok oceny cropa nad obrazem.

Canonical PNG używa checksum-bound cache RAM: maksymalnie trzy wpisy, 64 MiB i
trzy równoległe pobrania. Spóźniona odpowiedź po unmount nie tworzy URL, a LRU
nigdy nie odwołuje aktualnie renderowanego URL. Zmiana źródła zatrzymuje
zapisywanie odpowiedzi poza oknem bezpośrednich sąsiadów.

Skrypt benchmarku obsługuje 100/300/500 bez sztucznego powielania. Deduplikuje
źródła po SHA-256 i zwraca `not_evaluable`, gdy niezależnych zdjęć jest za
mało. Jego raport mówi wprost, że obejmuje historyczny lokalizator V1 oraz
read-only runtime, bez rankingu reprezentanta V2 i writera. Nie wykonano
rzeczywistego benchmarku sprzętu: operator polecił nie uruchamiać zbędnych
testów, więc nie powstały liczby wydajnościowe ani raport JSON.

Walidacja: Admin typecheck; lint wyłącznie zmienionego pliku; sześć testów
interakcyjnych workspace'u; osiem testów benchmarku Python. Astra Medium
znalazła kolejno sześć P2 (późny URL po unmount, ewikcja aktywnego obrazu,
kopie JPEG w pomiarze, pętla retry, luka indeksów, reset błędu/uncached assetu);
wszystkie poprawiono. Końcowy re-audyt Astra nie ma P0–P2.
