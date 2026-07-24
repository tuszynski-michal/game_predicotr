---
title: Delivery roadmap
status: accepted
last_updated: 2026-07-24
---

# Roadmap

Każdy milestone kończy się działającym pionem funkcjonalnym. Mobile działa offline od pierwszego pionu. Nie rozpoczynamy masowego rozpoznawania zdjęć przed ustabilizowaniem modelu danych, ręcznego importu i procesu publikacji.

## M0 — Architecture clarification

### Status

Ukończony 2026-07-24.

### Rezultat

- odpowiedzi właściciela na Q-001–Q-014 i Q-018,
- zaakceptowane decyzje D-001–D-010,
- całkowicie offline model mobilny,
- skala około 500 000 layoutów na grę,
- ustalone matching, duplikaty, payout, joker i Target,
- zaakceptowany monorepo i stos technologiczny,
- trzy próbki zdjęć zinwentaryzowane,
- otwarte pytania obrazowe odłożone do właściwego milestone'u.

## M1 — Offline mocked mobile vertical slice

Szczegóły: [MILESTONE_01_MOCKED_MOBILE.md](MILESTONE_01_MOCKED_MOBILE.md)

Plan wykonania:
[MILESTONE_01_EXECUTION_PLAN.md](MILESTONE_01_EXECUTION_PLAN.md)

M1 jest jednym milestone'em produktowym, ale jest realizowany przez sześć
kolejnych, osobno odbieranych podetapów:

1. **M1.1** — fundament monorepo i offline SQLite spike,
2. **M1.2** — kontrakty domenowe, payout i Target golden tests,
3. **M1.3** — generator danych, snapshot i repozytorium,
4. **M1.4** — wprowadzanie planszy i kompletny matching UI,
5. **M1.5** — pełny Target oraz wirtualizowana tabela,
6. **M1.6** — release APK i odbiór na urządzeniach.

Każdy podetap ma własną bramkę jakości. Nie realizujemy całego M1 w jednym
zadaniu ani jednym dużym zestawie zmian.

### Rezultat

Instalowalne APK z dołączonym SQLite: 3 gry, 1000 layoutów na grę, lokalny prefix/exact matching, duplikaty, zamockowany payout oraz pełny Target obejmujący 999 przyszłych spinów.

## M2 — Admin configuration

Plan wykonania:
[MILESTONE_02_EXECUTION_PLAN.md](MILESTONE_02_EXECUTION_PLAN.md)

M2 jest realizowany przez:

1. **M2.1** — lokalną platformę administracyjną i kontrakt,
2. **M2.2** — gry i symbole,
3. **M2.3** — wersje reguł, paylines i payout rules,
4. **M2.4** — mock datasety, walidację i publikację,
5. **M2.5** — zintegrowany odbiór panelu.

### Zakres

- lokalny Next.js, FastAPI i PostgreSQL,
- CRUD gier i symboli,
- wersje reguł,
- modal edytora paylines z walidacją duplikatów,
- payout rules,
- generator/import mock layoutów,
- walidacja ciągłości sekwencji,
- publikacja wersji reguł i datasetu.

### Rezultat

Konfiguracja i mock data mogą być tworzone w panelu zamiast utrzymywane wyłącznie w fixture M1.

## M3 — Versioned mobile release pipeline

Plan wykonania:
[MILESTONE_03_EXECUTION_PLAN.md](MILESTONE_03_EXECUTION_PLAN.md)

M3 jest realizowany przez:

1. **M3.1** — trwałe jobs i worker,
2. **M3.2** — precomputing payoutów i audyt,
3. **M3.3** — produkcyjny snapshot SQLite,
4. **M3.4** — orkiestrację wydania i panel Android,
5. **M3.5** — benchmark 500 000 layoutów.

### Zakres

- osobny worker/CLI i trwałe jobs,
- payout evaluation z audytem,
- precomputing payoutu każdego layoutu,
- generator oraz walidator SQLite,
- manifest i checksumy,
- panel przygotowania wersji Android,
- lokalny Android build,
- benchmark 500 000 layoutów na grę.

### Rezultat

Zmiana danych w panelu może zostać opublikowana jako nowy, odtwarzalny snapshot i APK do ręcznego sideloadu.

## M4 — Manual data import

Plan wykonania:
[MILESTONE_04_EXECUTION_PLAN.md](MILESTONE_04_EXECUTION_PLAN.md)

M4 jest realizowany przez:

1. **M4.1** — kontrakt pliku i utworzenie importu,
2. **M4.2** — streaming, staging i wznowienie,
3. **M4.3** — raport integralności i UI,
4. **M4.4** — publikację i odbiór dużego importu.

### Zakres

- import CSV/JSON przygotowanego zewnętrznie,
- staging,
- wznawianie i idempotencja,
- walidacja,
- raport luk, numerów i duplikatów sygnatur,
- publikacja datasetu.

### Rezultat

System przyjmuje duże dane bez zależności od automatycznego rozpoznawania zdjęć.

## M5 — Image ingestion prototype

Plan wykonania:
[MILESTONE_05_EXECUTION_PLAN.md](MILESTONE_05_EXECUTION_PLAN.md)

M5 jest realizowany przez:

1. **M5.1** — korpus i golden annotations,
2. **M5.2** — discovery i normalizację,
3. **M5.3** — geometrię strony, layoutów i komórek,
4. **M5.4** — OCR numerów i walidację ciągłości,
5. **M5.5** — benchmark oraz decyzję o stosie.

### Zakres

- 20–100 reprezentatywnych zdjęć,
- Pillow/OpenCV/NumPy,
- indywidualna korekta perspektywy mini-layoutów,
- detekcja siatki 3 × 3,
- PaddleOCR ograniczony do cyfr,
- wycięcie komórek 3 × 5,
- pomiary jakości każdego etapu.

### Bramka

Nie przechodzimy do masowego importu, dopóki prototyp nie osiągnie zaakceptowanych metryk i nie potwierdzi stabilności układu zdjęć.

## M6 — Symbol classifier and review workflow

Plan wykonania:
[MILESTONE_06_EXECUTION_PLAN.md](MILESTONE_06_EXECUTION_PLAN.md)

M6 jest realizowany przez:

1. **M6.1** — wersjonowany dataset symboli,
2. **M6.2** — trening, ONNX i confidence,
3. **M6.3** — manual review end to end,
4. **M6.4** — zintegrowany odbiór klasyfikacji.

### Zakres

- oznaczone przykłady symboli,
- trening PyTorch/torchvision,
- eksport do ONNX,
- lokalna inferencja ONNX Runtime,
- confidence i alternatywy,
- manual review,
- zapisywanie korekt jako dataset,
- walidacja dzielona według zdjęcia źródłowego.

## M7 — Large-scale resumable image import

Plan wykonania:
[MILESTONE_07_EXECUTION_PLAN.md](MILESTONE_07_EXECUTION_PLAN.md)

M7 jest realizowany przez:

1. **M7.1** — kontrakt i orkiestrację pipeline’u,
2. **M7.2** — integrację etapów i izolację błędów,
3. **M7.3** — operacje, statystyki i storage,
4. **M7.4** — testy obciążeniowe i jakość operacyjną,
5. **M7.5** — publikację dużej wersji danych.

### Zakres

- pełny wersjonowany pipeline,
- batch processing,
- wznowienia i anulowanie,
- statystyki,
- testy obciążeniowe bazy oraz storage,
- publikacja dużej wersji danych,
- jedno ciężkie zadanie naraz, dopóki pomiary nie uzasadnią kolejki.

## M8 — Private distribution and hardening

Plan wykonania:
[MILESTONE_08_EXECUTION_PLAN.md](MILESTONE_08_EXECUTION_PLAN.md)

M8 jest realizowany przez:

1. **M8.1** — model bezpieczeństwa lokalnej administracji,
2. **M8.2** — stabilny podpis i odtwarzalny build,
3. **M8.3** — backup i restore,
4. **M8.4** — diagnostykę uszkodzonego snapshotu,
5. **M8.5** — macierz urządzeń i regresję offline,
6. **M8.6** — prywatną dystrybucję i odbiór końcowy.

### Zakres

- testy na wszystkich 3–5 urządzeniach docelowych,
- testy kompatybilności wersji Android,
- odtwarzalny podpis/build APK,
- backup lokalnego PostgreSQL i artefaktów,
- diagnostyka uszkodzonego snapshotu,
- instrukcja ręcznej aktualizacji APK,
- decyzja o autoryzacji panelu po Q-019.

Publiczny backend, synchronizacja, Google Play, chmura i infrastruktura wieloużytkownikowa pozostają poza zakresem bez nowej decyzji właściciela.

## Zasady przejścia

- milestone ma własne kryteria akceptacji,
- otwarte błędy krytyczne blokują przejście,
- każda zmiana modelu domenowego aktualizuje dokumentację,
- nowe technologie wymagają wpisu do Decision Log,
- wydajność mierzymy na reprezentatywnych danych,
- wynik benchmarku może zmienić adapter lub bibliotekę, ale nie może po cichu zmienić zachowania produktu,
- rozpoczęcie kolejnego milestone'u wymaga osobnego zadania i polecenia właściciela.

Jeżeli zarezerwowane zadanie okaże się zbyt duże, nie rozszerzamy go ukrycie.
Nowy zakres otrzymuje kolejny wolny identyfikator po ostatnim zarezerwowanym
numerze, a właściwy plan milestone’u i `CURRENT_STATE.md` są aktualizowane.
Pierwotny identyfikator zachowuje dotychczasowy cel i nie jest używany ponownie
dla innego zakresu.
