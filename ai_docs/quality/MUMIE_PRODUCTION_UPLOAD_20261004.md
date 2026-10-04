---
title: Mumie — odbiór wgrania do głównej aplikacji
status: done
last_updated: 2026-10-04
---

# Mumie — wgranie źródeł i preflight

## Wynik i granica wykonania

Gra „Mumie”, kod `mumie`, status draft, profil `grid_profile_mumie_v1`, została
utworzona przez istniejące API 8000. Wgrano i sfinalizowano 225/225 źródłowych
JPEG-ów, 61 768 538 bajtów. Wgranie trwało 13,62 s. Wszystkie pliki zachowują
oryginalne nazwy i zakresy sekwencji; nie przenumerowano nieciągłego materiału.

Preflight geometrii zakończył 225 źródeł: 0 failed, 225 review. Preflight importu
wykazuje 2025 nowych pozycji, 0 reused, pierwszą nierozstrzygniętą 10 i ostatnią
381573. `geometryPreflightArtifactReady=false`, blocker
`IMAGE_PAGE_GEOMETRY_REVIEW_REQUIRED`. Nie uruchomiono joba importu plansz.
Zdjęcia są w stagingu, nie w ukończonym katalogu plansz.

TASK-0830 wdrożył rejestr oraz wybór profilu, lecz jawnie wykluczył inferencję
sieci w pipeline importu. Wybór profilu nie oznacza użycia sieci do cięcia.
Model Mumii działa w laboratorium; podłączenie go do głównej aplikacji pozostaje
osobnym zakresem V3-D, wymagającym wyraźnego polecenia operatora. Nie obchodzono
przeglądu siatek, nie zatwierdzano propozycji ani symboli za operatora.

## Identyfikatory i integralność

| Element | Wartość |
|---|---|
| gameId | `fea55cc1-ebf4-4cee-b3ab-a520017ed1be` |
| uploadId | `becad72f-200d-4ba1-8d35-464b19d8f299` |
| geometryJobId | `3e0151c8-b9ff-4da1-b96d-72af4cb01912` |
| Input fingerprint | `9b84d47bf530faa9f97e63952d5d7a16e713241b7d15a1d21af9f0ccac15a0a3` |
| Input manifest SHA-256 | `6a9070fe8518b5d19795f3f3357c008081a7e70b7894798e35a1b29184e06a8e` |
| Geometry manifest SHA-256 | `c296ff28daf0024a83cb2087080e4b526c43feb4c44b266e708a0f1fe70924b5` |

Źródło: `C:\Users\tuszy\Documents\game_predictor_traning_set\mumie`.
Raport trwały: `C:\Users\tuszy\Documents\game_predicotr\artifacts\mumie-import-20261004\state.json`.

## Trwałość i kontrakt

CLI `scripts/run_mumie_image_import.py` używa istniejącego kontraktu API,
obsługiwanego trybu `structured_lattice_v3` oraz fingerprintów serwera. Nie
uruchamia historycznego CLI przypinającego `verified_v19`. Kontekst `gameId`
w query routuje żądania do storage właściwej gry, także przy odczycie joba.
Pierwsza nieudana próba preflightu bez tego kontekstu została poprawiona w CLI;
nie wymagała zmian backendu ani migracji.

Raport zapisuje identyfikatory przed kolejnymi krokami. Zmiana bajtów, nawet
przy tej samej liczbie i wielkości plików, blokuje wznowienie. Utracona odpowiedź
nieidempotentnego tworzenia stagingu blokuje automatyczne ponowienie, gdy brak
znanego uploadId. Blokada pliku ogranicza równoległe uruchomienia CLI.

Nowy proces ponowił upload w 1,25 s: ten sam gameId i uploadId, bez nowego
transferu. Ponowne advance w 1,59 s odzyskało ten sam geometryJobId i ponownie
zatrzymało się na wymaganym przeglądzie, bez nowego joba. Odczyt status w nowym
procesie potwierdził draft, profil, 225 plików i 61 768 538 bajtów.

## Weryfikacja i Definition of Done

5 testów requestów PASS: SHA wejścia, konflikt profilu bez zapisu, przypięty
tryb i bramka review, utracona odpowiedź tworzenia stagingu, routing gameId
przed odczytem joba. Ruff check/format PASS, Mypy strict nowego CLI PASS
(`--follow-imports skip`, 1 moduł; nie jest to kontrola typów całego backendu).
Pierwsza próba z MYPYPATH ograniczonym do workera wykazała brak importów API
i timeout; runner zakończył drzewo procesów. Poprawiono ścieżki i sprawdzono CLI.
Nie zmieniono kontraktu API, schematu ani UI; regeneracja klientów i build
frontendów nie są wymagane dla tego zakresu.

Kryteria TASK-0843 rozliczone: odrębna gra i odczyt trwałości, 225/225 staging,
preflight z jawnym blockerem, wznowienie bez duplikatów, raport i dokumentacja.
Warunkowe przetwarzanie plansz pozostaje niewykonane z powodu 225 review.
Nie wykonano migracji, usuwania danych, aktywacji modelu, wypłat ani shadow.

## Następny krok

Przegląd geometrii albo osobno zlecony V3-D. Dla dalszego uczenia siatek
pozostaje kolejka laboratorium `http://127.0.0.1:8105`: 236 zdjęć, 216
niekompletnych. TASK-0842 przygotował 5 partii i 2700 wycinków z zatwierdzonych
siatek. Trening symboli i złotej ramki „Super” wymaga osobnych etykiet.
