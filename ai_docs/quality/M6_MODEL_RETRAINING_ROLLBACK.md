---
title: M6 model retraining, promotion and rollback
status: accepted
last_updated: 2026-07-29
---

# Ponowne trenowanie, promocja i rollback modelu M6

## Cel

Model symboli jest niezmiennym artefaktem batchowym. Decyzja administratora
nie aktualizuje wag online. Każdy retraining tworzy nowy dataset, split,
checkpoint, ONNX, kalibrację i raport odbioru, a rollback wybiera wcześniejszy
kompletny łańcuch zamiast nadpisywać pliki.

## Warunki rozpoczęcia retrainingu

Retraining można rozpocząć dopiero, gdy:

1. batch manual review nie ma elementów `pending`,
2. utworzono niezmienny `review_feedback_export`,
3. eksport wskazuje dokładne rewizje, `sampleId`, `modelVersion` i checksumy,
4. accepted/corrected mają zaakceptowaną geometrię i 15 komórek,
5. rejected nie są traktowane jako próbki,
6. kod nowej iteracji jawnie nadaje nowe wersje datasetu i modelu.

Aktualny raport TASK-0067 ma decyzję
`retraining_required_before_auto_accept`. Nie wolno obniżać progów tylko po to,
aby zmienić tę decyzję.

## Procedura retrainingu

1. Zamrozić eksport feedbacku i zapisać jego `version`, `sourceStateSha256`
   oraz `payloadSha256`.
2. Zmaterializować nowy label source, łącząc wcześniejsze zaakceptowane próbki
   z nowym feedbackiem po dokładnym `cropSampleId`. Konflikt klasy lub checksumy
   blokuje operację.
3. Uruchomić eksport do nowego namespace'u `labeled-symbol-dataset-vN`.
   Historyczne assety i raporty pozostają read-only.
4. Utworzyć nowy source-aware split po zdjęciu źródłowym. Validation i test nie
   mogą współdzielić source image ani binarnych assetów z train.
5. Uruchomić batchowy trening ze stałym seedem. Checkpoint wybiera validation;
   test jest odczytywany dopiero po zamrożeniu wyboru.
6. Wyeksportować nowy ONNX i wykonać pełny test parytetu PyTorch–ONNX.
7. Dopasować temperaturę wyłącznie na validation i policzyć progi per symbol.
8. Uruchomić `accept_m6_classifier_vertical_slice.py` dla nowego kompletnego
   łańcucha. Promocja jest dozwolona tylko po przejściu checksum, jakości,
   review i odtwarzalności.

Każda iteracja wymaga nowych identyfikatorów wersji w kodzie i nowych ścieżek
artefaktów. Nie wolno używać `--check` jako sposobu aktualizacji istniejącego
raportu.

## Promocja

Promowany jest jeden spójny manifest:

```text
datasetSha256
splitSha256
classifierVersion
checkpointSha256
onnxModelVersion
onnxArtifactSha256
calibrationReportSha256
confidencePolicyVersion
verticalSliceReportSha256
```

Nie istnieje „aktywny plik wag” modyfikowany w miejscu. Nowe batche review
zapisują dokładny manifest modelu w snapshotach. Stare batche nadal renderują
wyniki modelu, z którym zostały utworzone.

## Rollback

Rollback wybiera ostatni wcześniej zaakceptowany manifest i jego istniejące
artefakty:

1. zatrzymać tworzenie nowych batchy dla wadliwej wersji,
2. wskazać poprzedni manifest jako źródło kolejnego batcha/job,
3. ponownie sprawdzić wszystkie checksumy i lokalny provider ONNX,
4. nie zmieniać historycznych batchy, resolution ani feedback exportów,
5. zapisać powód rollbacku i wersję wycofaną w Decision Log lub zadaniu
   operacyjnym,
6. uruchomić pion odbioru dla przywróconego manifestu.

Usunięcie albo podmiana wadliwego artefaktu nie jest rollbackiem. Artefakt
pozostaje zachowany jako dowód; jedynie nie może być wybierany dla nowych
batchy.

## Obecna wersja

- model: `bootstrap-symbol-cnn-onnx-v1`,
- ONNX SHA-256:
  `e03f66f2ab092b6049920fee6fb2839900a95eb94af42fbd5ef7e35c473b5fb8`,
- polityka: `symbol-confidence-policy-v1`,
- auto-accept: wyłączony,
- auto-reject: wyłączony,
- wynik TASK-0067: pion techniczny zaliczony, retraining wymagany przed
  auto-accept i przed masowym importem.
