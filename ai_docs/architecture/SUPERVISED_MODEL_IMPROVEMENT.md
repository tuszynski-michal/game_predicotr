---
title: Supervised symbol model improvement architecture
status: accepted
last_updated: 2026-08-01
---

# Architektura iteracyjnego ulepszania modelu symboli

## Granica odpowiedzialności

Ten pion obejmuje model rozpoznawania symboli. Nie zmienia wersji geometrii,
croppera ani OCR numerów sekwencji. Właścicielem reguł produktowych jest
`requirements/SUPERVISED_MODEL_IMPROVEMENT.md`; ten dokument opisuje sposób ich
realizacji.

## Przepływ

```mermaid
flowchart LR
    A["Ręcznie rozwiązane plansze"] --> B["Niezmienna kohorta gry"]
    B --> C["Deterministyczny dataset"]
    C --> D["Trening od początku"]
    D --> E["ONNX, kalibracja i bramka"]
    E --> F["Kandydat"]
    F -->|"jawna aktywacja"| G["Aktywny model gry"]
    G --> H["Nowe importy z przypiętą wersją"]
    G --> I["Jawne przeliczenie tylko pending"]
    I --> J["Nowe rewizje predykcji"]
```

## Planowane encje PostgreSQL

Zmiany schematu są wykonywane wyłącznie migracją Alembic. Szczegółowe pola
należą do `DATA_MODEL.md`.

### `verified_training_cohorts`

Niezmienny manifest pełnych, ręcznie zweryfikowanych plansz jednej gry.
Zawiera co najmniej `game_id`, numer iteracji, checksumę manifestu, liczności,
identyfikatory źródeł oraz czas i aktora zamrożenia.

### `symbol_model_iterations`

Opisuje niezmienną wersję kandydata: kohortę, fingerprint konfiguracji,
status, wersje kodu i bibliotek, ścieżki artefaktów, checksumy, metryki,
kalibrację i powód odrzucenia lub błędu.

### `game_symbol_model_activations`

Historia jawnych aktywacji i rollbacków per gra. Jeden rekord wskazuje wersję,
aktora i przyczynę. Bieżący aktywny model jest jednoznaczną projekcją ostatniego
skutecznego zdarzenia.

### `symbol_prediction_revisions`

Append-only wynik inferencji dla konkretnego cropu i wersji modelu. Zawiera
ranking klas, confidence, checksumę cropu oraz pochodzenie joba. Decyzja review
nie jest przechowywana w tej tabeli.

## Ochrona decyzji człowieka

Warstwa aplikacyjna kwalifikuje do przeliczenia wyłącznie elementy `pending`.
Sam zapis stosuje warunek porównujący oczekiwany status, rewizję review i
checksumę cropu. Jeżeli użytkownik rozwiązał element po pobraniu partii, zapis
nie dochodzi do skutku i raportuje `skipped_human_resolved`.

Operacja nie wykonuje `UPDATE` ani `DELETE` na tabelach zdarzeń rozstrzygnięć,
zatwierdzonych geometriach i stagingu. Test integracyjny porównuje ich checksumy
przed oraz po treningu, aktywacji i masowej inferencji.

## Budowa skumulowanego datasetu

Builder czyta wyłącznie pełne rozstrzygnięcia `accepted` i `corrected` z
zaakceptowaną geometrią oraz kompletem komórek. Zamrożony manifest wiąże:

- identyfikator i rewizję planszy,
- `cropSampleId` oraz checksumę każdego cropu,
- kod symbolu ustalony przez człowieka,
- zdjęcie źródłowe i import,
- wersję geometrii oraz pipeline'u.

Grupą podziału jest co najmniej zdjęcie źródłowe. Builder generuje stabilny
train/validation/test i osobny stały zestaw regresyjny. Ta sama grupa nie może
wystąpić w kilku częściach. Kolejna iteracja trenuje od początku na całej
skumulowanej kohorcie, co ogranicza dryf i pozwala dokładnie odtworzyć wynik.

## Artefakty

Artefakty są content-addressed, nie są zapisywane jako duże BLOB-y w tabelach:

```text
data/
  training/<game-code>/<cohort-sha256>/
  models/<game-code>/<iteration-id>/<manifest-sha256>/
  exports/model-quality/<game-code>/<iteration-id>/
```

Manifest modelu zawiera co najmniej checksumę kohorty, konfiguracji, checkpointu
i ONNX, wersję kodu, kalibrację, progi, katalog symboli oraz pełne metryki.

## Trwały job

Jedna iteracja ma kontrolowane etapy:

```text
cohort_freeze -> dataset_build -> training -> onnx_export
              -> calibration -> evaluation -> candidate_ready
```

Każdy etap zapisuje checkpoint. Retry potwierdza fingerprint wejścia i nie
tworzy drugiej wersji z tym samym kluczem idempotencji. Początkowo blokada per
gra dopuszcza najwyżej jeden ciężki trening albo masową ponowną inferencję.

## Bramka kandydata

Kandydat musi przejść:

- integralność artefaktów i zgodność katalogu symboli,
- parytet PyTorch–ONNX na ustalonej tolerancji,
- kalibrację confidence na validation,
- metryki ogólne i per klasa na rozłącznym test/regression,
- brak niedopuszczalnej regresji względem aktywnego modelu,
- smoke test CPU w środowisku workera.

Dokładne progi są wersjonowaną konfiguracją bramki. Przejście bramki nadaje
status `candidate_ready`, ale nie aktywuje modelu.

## Aktywacja, rollback i przypięcie importu

Aktywacja jest osobną, audytowalną komendą i atomowo zmienia aktywny wskaźnik
danej gry. Poprzednie wersje pozostają niezmienne, więc rollback jest kolejnym
zdarzeniem aktywacji.

Tworzenie image import joba zapisuje `symbolModelIterationId`, manifest SHA-256
i fingerprint inferencji. Worker zawsze używa tego snapshotu do końca joba.
Aktywacja w trakcie importu wpływa dopiero na następny import.

## Przeliczenie oczekujących

Jawna komenda tworzy job z listą elementów kwalifikujących się w momencie
startu. Worker ponownie sprawdza warunki przy każdym zapisie. Wyniki są nowymi
rekordami `symbol_prediction_revisions`, a projekcja bieżącej sugestii wybiera
najnowszą zgodną rewizję dla elementu nadal `pending`.

Raport końcowy rozdziela:

- przeliczone,
- pominięte jako rozwiązane przez człowieka,
- pominięte z powodu zmiany cropu lub geometrii,
- nieudane technicznie.

## Planowany kontrakt API

Kontrakty OpenAPI będą właścicielsko opisane w `API_CONTRACT.md`. Planowane
grupy operacji:

- odczyt stanu jakości aktywnej gry,
- preview i zamrożenie kohorty,
- utworzenie oraz odczyt iteracji modelu,
- jawna aktywacja, odrzucenie i rollback,
- preview oraz uruchomienie przeliczenia oczekujących.

Frontend korzysta z generowanego klienta; nie utrzymuje ręcznych kopii typów.

## Obserwowalność i odtwarzalność

Każda iteracja i inferencja zapisuje czas etapów, liczności, wersje, checksumy,
aktora oraz stabilne kody błędów. Diagnostyka nie zawiera obrazów ani ścieżek
absolutnych. Aktywna wersja i wersja przypięta do importu są widoczne w Adminie.
