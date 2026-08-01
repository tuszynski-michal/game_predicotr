---
title: Delivery roadmap
status: accepted
last_updated: 2026-08-01
---

# Roadmap

Każdy milestone kończy się działającym pionem funkcjonalnym. Mobile działa offline od pierwszego pionu. Nie rozpoczynamy masowego rozpoznawania zdjęć przed ustabilizowaniem modelu danych, ręcznego importu i procesu publikacji.

## Podział wydań 0.1, 0.2, 0.3 i 0.4

- **Wersja 0.1** zamyka kompletny demonstracyjny przepływ mobilny dla jednej
  gry i dokładnie 500 000 layoutów. Ponad 100 layoutów zatwierdzonych przez
  człowieka pozostaje kanonicznym podzbiorem, a pozostałe rekordy powstają
  deterministycznie jako dane testowe. Zakres i bramki opisuje
  [VERSION_0_1_RELEASE_PLAN.md](VERSION_0_1_RELEASE_PLAN.md); TASK-0118 jest
  ukończony, a odbiór urządzeniowy TASK-0119 pozostaje otwarty.
- **Wersja 0.2** zaczyna od czystej bazy i obejmuje przebudowę Admina,
  folderowy import oraz pełny workflow na małym testowym zbiorze jednej gry.
  Nie jest bramką pełnych danych ani skali. Zakres i kolejność opisuje
  [VERSION_0_2_EXECUTION_PLAN.md](VERSION_0_2_EXECUTION_PLAN.md).
- **Wersja 0.3** dostosowuje aplikację mobilną: upraszcza ekran, dodaje `Next`,
  wybierany zasięg Targetu, kompaktowy wynik i powrót na górę. Zakres opisuje
  [VERSION_0_3_EXECUTION_PLAN.md](VERSION_0_3_EXECUTION_PLAN.md).
- **Wersja 0.4** obejmuje pełny rzeczywisty dataset, kolejne gry, wielogrowe
  wydanie, końcowe testy dużych zbiorów, pełny hardening i szerszą regresję.
  Zakres opisuje
  [VERSION_0_4_EXECUTION_PLAN.md](VERSION_0_4_EXECUTION_PLAN.md).
- Ukończone zabezpieczenie lokalnego Admina i zdalnego Reviewera pozostaje
  częścią 0.1. Reset danych 0.2 nie cofa tych zabezpieczeń ani nie usuwa
  artefaktów wydania 0.1.

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

### Status

Ukończony i zaakceptowany przez właściciela 2026-07-26. Test zmiany snapshotu
oraz dokładne pomiary urządzeniowe przeniesiono do M3 zgodnie z D-020.

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

### Status

Ukończony 2026-07-27. Końcowa bramka G2 przeszła na izolowanym fizycznym
PostgreSQL przez publiczne Admin API, bez ręcznej mutacji danych SQL.

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
- wersjonowane minimum wygranej per symbol, domyślnie 3,
- payout rules dla każdej długości od minimum symbolu,
- generator/import mock layoutów,
- walidacja ciągłości sekwencji,
- publikacja wersji reguł i datasetu.

### Rezultat

Konfiguracja i mock data mogą być tworzone, walidowane, przeglądane i
publikowane w panelu zamiast utrzymywane wyłącznie w fixture M1. Opublikowane
wersje reguł i datasetów są niezmienne.

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

Status: `completed_calibrated_manual_review_only_ocr`. Detekcja strony i
pozycji plansz pozostaje zaakceptowana, OCR pozostaje `manual_review_only`,
a TASK-0094–0096 zakończyły niezależny golden, cropper v2 i wersjonowane
profile. Skalibrowany wariant przeszedł bramkę z P95 linii `1.8337 px`.

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
- detekcja strony z 1–9 layoutami w siatce do 3 × 3,
- lokalny model recognition-only PP-OCRv5 przez PaddlePaddle CPU i dekoder cyfr,
- wycięcie komórek 3 × 5,
- pomiary jakości każdego etapu.

### Bramka

Nie przechodzimy do masowego importu, dopóki prototyp nie osiągnie zaakceptowanych metryk i nie potwierdzi stabilności układu zdjęć.

## M6 — Symbol classifier and review workflow

Status: `passed_with_retraining_required`; pion manual review działa, a
TASK-0104 wybrał `spatial-symbol-cnn-v1` z test accuracy `0.96166134` i macro
recall `0.95484094`. Checkpoint wymaga jeszcze productionization, ONNX i
kalibracji przed zmianą aktywnego modelu.

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
- pełnolayoutowe review 5 × 3,
- batchowe uczenie i active-learning review selection bez uczenia online,
- walidacja dzielona według zdjęcia źródłowego.

## M6.5 — Supervised verification workbench

Plan wykonania:
[MILESTONE_06_5_EXECUTION_PLAN.md](MILESTONE_06_5_EXECUTION_PLAN.md)

M6.5 jest realizowany przez:

1. **M6.5.1** — productionization wybranego modelu,
2. **M6.5.2** — operacyjną kolejkę review,
3. **M6.5.3** — minimalistyczne stanowisko jednej planszy,
4. **M6.5.4** — sterowanie klawiaturą i szybkie korekty,
5. **M6.5.5** — korektę geometrii i immutable recrop,
6. **M6.5.6** — zamrożoną kohortę oraz ochronę decyzji człowieka,
7. **M6.5.7** — odbiór ergonomii i skali.

### Zakres

- pełna siatka 5 × 3 z podpisami nad foldem,
- oryginalne zdjęcie i 3–4 sugestie dla wybranej komórki,
- nawigacja strzałkami i skróty `1`–`0`, następnie `QWERTY`,
- pojedyncze zatwierdzenie przez `Enter` lub kliknięcie bez dodatkowego modala,
- ponowna edycja accepted/corrected z historią rewizji,
- ręczna korekta czterech narożników i wersjonowane cropy,
- ręcznie zweryfikowane kohorty 1000/3000+ uruchamiane na polecenie właściciela,
- retraining bez nadpisywania zaakceptowanych plansz.

### Rezultat

Jeden operator może lokalnie i szybko budować kanoniczny, ręcznie
zweryfikowany zbiór oraz publikować jego ciągłe podzbiory bez czekania na
perfekcyjny auto-accept. Automatyczny masowy import nadal podlega osobnej
bramce jakości.

## M6.6 — Iterative supervised model improvement

Plan wykonania:
[MILESTONE_06_6_EXECUTION_PLAN.md](MILESTONE_06_6_EXECUTION_PLAN.md)

M6.6 jest realizowany przez TASK-0143–0150 i domyka pętlę ręcznej weryfikacji,
skumulowanego treningu, bramki kandydata, jawnej aktywacji oraz bezpiecznej
ponownej inferencji.

### Zakres

- niezmienne kohorty pełnych `accepted` i `corrected` plansz per gra,
- trening od początku na skumulowanym zbiorze z podziałem według źródła,
- ONNX, kalibracja i regresja względem aktywnego modelu,
- wersjonowany rejestr, jawna aktywacja i rollback,
- przypięcie modelu do importu w chwili utworzenia joba,
- nowe sugestie wyłącznie dla aktualnego `pending`.

### Nienaruszalna bramka

Automatyczny proces nie może przeliczyć ani zmienić `accepted`, `corrected` lub
`rejected`. Milestone przechodzi dopiero po dwóch iteracjach potwierdzających
identyczne checksumy wszystkich decyzji człowieka przed i po operacjach modelu.

M6.6 należy do toru przygotowania danych 0.4 i musi zakończyć się przed pełnym
automatycznym importem M7.

## M7 — Large-scale resumable image import

Plan wykonania:
[MILESTONE_07_EXECUTION_PLAN.md](MILESTONE_07_EXECUTION_PLAN.md)

### Status wydania

M7.1–M7.4 są ukończone w zakresie fundamentów i kontrolowanego review.
TASK-0076 pozostaje zablokowany bramką `massImportAllowed = false` i został
zaplanowany dla wersji 0.4; nie blokuje wersji 0.1, małego workflow 0.2 ani
dostosowania mobilnego 0.3.

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

### Status wydania

M8.1 oraz M8.7 są ukończone i zachowane w 0.1. M8.2–M8.6, czyli TASK-0080–0089,
zostały świadomie przeniesione do wersji 0.4. Odbiór TASK-0119 na Pixelu jest
bramką 0.1, ale nie zastępuje pełnej bramki G8 planowanej dla 0.4.

M8 jest realizowany przez:

1. **M8.1** — model bezpieczeństwa lokalnej administracji,
2. **M8.2** — stabilny podpis i odtwarzalny build,
3. **M8.3** — backup i restore,
4. **M8.4** — diagnostykę uszkodzonego snapshotu,
5. **M8.5** — macierz urządzeń i regresję offline,
6. **M8.6** — prywatną dystrybucję i odbiór końcowy,
7. **M8.7** — opcjonalny, zabezpieczony zdalny dostęp do samego review.

### Zakres

- testy na wszystkich 3–5 urządzeniach docelowych,
- testy kompatybilności wersji Android,
- odtwarzalny podpis/build APK,
- backup lokalnego PostgreSQL i artefaktów,
- diagnostyka uszkodzonego snapshotu,
- instrukcja ręcznej aktualizacji APK,
- decyzja o autoryzacji panelu po Q-019,
- odwoływalna, game-scoped sesja z linkiem i kodem dla zdalnego recenzenta,
  wdrażana dopiero po lokalnym G6.5 i threat modelu M8.1.

Pełny publiczny backend, synchronizacja, Google Play, chmura i zdalny dostęp do
funkcji administracyjnych innych niż jawnie ograniczone review pozostają poza
zakresem bez nowej decyzji właściciela.

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
