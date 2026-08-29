# V0.10 — eksperymentalny fallback geometrii keypoint

## Status

TASK-0319 dostarcza wyłącznie bounded eksperyment `shadow-only`. Nie istnieje
ścieżka aktywacji w API, Adminie, Reviewerze ani produkcyjnym workflow. D-261
nadal wymaga kompletnego raportu jakości przed zmianą rolloutu geometrii.

## Dane wejściowe

Manifest datasetu przyjmuje wyłącznie źródła z ręcznie zatwierdzoną geometrią:

- checksumę i bezpieczną ścieżkę JPEG-a w zarządzanym katalogu;
- dokładne wymiary obrazu;
- aktywny prefiks slotów `1..9` wynikający z poświadczonego zakresu `seq_*`;
- po jednym wypukłym quadzie `LT, PT, PD, LD` dla każdego aktywnego slotu;
- source family używane do source-disjoint splitu.

Zamrożenie jest deterministyczne, wymaga co najmniej trzech source families i
nie pozwala, aby rodzina trafiła do więcej niż jednego z `train`, `validation`
i `test`. Loader ponownie sprawdza bezpieczną ścieżkę, brak symlinka, SHA-256,
EXIF transpose oraz wymiary.

## Model i kontrakt ONNX

Mały model konwolucyjny przyjmuje RGB `128 × 128` i zwraca:

- `corner_heatmaps`: `[N, 9, 4, 32, 32]`;
- `slot_presence`: `[N, 9]`.

Trening jest deterministyczny i bounded na CPU. Eksport ONNX używa opsetu 18,
ma stałe nazwy wejść/wyjść oraz raport zgodności z PyTorch. Runtime akceptuje
wyłącznie lokalny plik o oczekiwanej checksumie i provider CPU.

Dekoder stosuje maskę aktywnych slotów. Fałszywa obecność poza maską jest
diagnostyką, ale nie tworzy geometrii. Brak aktywnego slotu, słaby narożnik,
niewłaściwa kolejność albo niewypukły quad kończą się fail-closed.

## Wspólna walidacja geometrii

`KeypointGeometryEngine` dostarcza wyłącznie inicjalne quady. Następnie używa
tego samego lokalnego line refiner oraz tych samych hard gates co Structured
OpenCV. Wspólny wynik pozostaje `SourceGeometryResult`; model nie omija
walidacji ramki, topologii, kolejności row-major ani jakości quada.

`KeypointGeometryShadowRunner` zawsze zwraca wynik poboczny i deklaruje
`canReplacePrimary=false`. Nie zapisuje cropów, nie zmienia rolloutu i nie
mutuje decyzji domenowych.

## Odbiór techniczny

Testy obejmują:

- ręczne pochodzenie quadów i izolację source family;
- deterministyczny manifest i heatmap targets;
- active prefix, nieaktywne sloty i brak aktywnego slota;
- golden dekodowania narożników;
- eksport ONNX i parity z PyTorch;
- bounded pomiar czasu CPU po warm-upie;
- przejście przez wspólny refiner i hard gates;
- brak możliwości promocji wyniku shadow.

Nie uruchomiono operacyjnego treningu ani benchmarku dużego zbioru. Ewentualny
test na danych użytkownika, raport jakości i aktywacja muszą powstać w osobnym,
jawnie zaakceptowanym zadaniu.
