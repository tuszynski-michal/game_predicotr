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

### Zakres

- pełny wersjonowany pipeline,
- batch processing,
- wznowienia i anulowanie,
- statystyki,
- testy obciążeniowe bazy oraz storage,
- publikacja dużej wersji danych,
- jedno ciężkie zadanie naraz, dopóki pomiary nie uzasadnią kolejki.

## M8 — Private distribution and hardening

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
