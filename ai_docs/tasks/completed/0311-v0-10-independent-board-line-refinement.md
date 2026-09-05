---
title: TASK-0311 — niezależne dopracowanie i walidacja geometrii plansz
status: done
version: 0.10.4
last_updated: 2026-08-29
---

# Cel

Zamienić początkowe ROI z TASK-0310 na niezależny, evidence-bound wynik
każdego aktywnego slotu. Lokalny etap ma wykrywać uporządkowane rodziny sześciu
linii pionowych i czterech poziomych siatki 5 × 3, dopasować odporną
homografię i zwrócić finalny quad wyłącznie wtedy, gdy przejdą jawne bramki.

# Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DECISION_LOG.md` — D-254–D-257
- `ai_docs/quality/m5-corpus-manifest.json`
- `ai_docs/quality/m5-golden-annotations.json`

# Zakres

- wersjonowany lokalny refiner LSD działający osobno dla każdego aktywnego
  slotu;
- grupowanie sześciu pionowych i czterech poziomych linii w tymczasowo
  zrektyfikowanym ROI;
- robust homography idealnej siatki 5 × 3 z obserwowanych przecięć;
- twarde bramki kompletności granic, pokrycia linii i przecięć, reprojekcji,
  source support, row-major oraz braku nakładania;
- osiem jawnych składowych confidence niezależnych od klasyfikatora symboli;
- stabilne statusy i reason codes per slot oraz checksumowany wynik źródła;
- testy syntetyczne i kontrola lokalnego korpusu dla glare, occlusion, ręki,
  overlapu, kolejności oraz niepełnego dowodu.

# Poza zakresem

- integracja z pipeline'em, bazą, API albo UI;
- renderowanie komórek i inferencja ONNX;
- ML, keypoint fallback i segmentacja;
- zmiana historycznych adapterów v20/v19;
- wymuszanie prostokąta albo kątów prostych w przestrzeni zdjęcia.

# Invarianty

- globalna homografia TASK-0310 pozostaje wyłącznie inicjalizacją;
- każdy slot jest dopracowywany niezależnie i nie dziedziczy finalnego quada
  sąsiada;
- slot z niepełnym dowodem nie udostępnia automatycznie używalnej finalnej
  geometrii;
- numer sekwencji i row-major wynikają wyłącznie z attested prefiksu `seq_*`;
- confidence geometrii nie używa predykcji ani confidence symboli;
- brakujące linie nie mogą przesunąć całej siatki o wiersz albo kolumnę;
- etap nie zapisuje bitmap ani nie modyfikuje danych użytkownika.

# Weryfikacja

Po implementacji uruchomić celowane testy workera, Ruff, format check i mypy
dla zmienionych modułów. Pełne `npm run quality` pozostaje zakresem tasków
integracyjnych.

# Outcome

Zaimplementowano wersjonowany, nieprodukcyjny pion
`structured-opencv-independent-board-refinement-v1`:

- `BoardLineRefiner` analizuje każdy początkowy quad osobno, wykorzystując
  luminance/gradient channels, LSD, czerwony border evidence i odporną
  homografię idealnej siatki 5 × 3;
- finalny quad jest rzutowany do przestrzeni źródła i nie ma narzuconych kątów
  prostych;
- dokładnie jedna brakująca linia wewnętrzna może być wyprowadzona tylko przy
  kompletnych granicach zewnętrznych, regularnym rozstawie i zgodności z
  inicjalizacją;
- osiem składowych confidence, hard gates, trzy disposition i stabilne reason
  codes są czystym, deterministycznym kontraktem niezależnym od symboli;
- wrapper źródłowy zachowuje jeden wynik na aktywny slot, sprawdza row-major,
  przypisanie do początkowego ROI i nakładanie finalnych quadów oraz checksumuje
  wynik.

Walidacja lokalnego corpus `m5-representative-corpus-v2` potwierdziła 43 obrazy
i 43 kompletne adnotacje. Kontrola historycznego false-success `seq_64–72`
nie dała automatycznej akceptacji przy niepełnym dowodzie poziomych linii —
sloty trafiają do korekty zamiast do croppera. TASK-0311 celowo nie ustala
jeszcze procentowej bramki rolloutu.

Uruchomiono:

- 32 celowane testy geometrii, globalnej inicjalizacji i source-direct
  renderowania — wszystkie przeszły;
- 10 nowych testów lokalnego refinera obejmujących 6 × 4, glare, okluzję/rękę,
  brak dowodu, pojedynczą linię, overlap, row-major, hard gates i historyczny
  false-success;
- Ruff format/check dla zmienionego kodu — bez błędów;
- scoped mypy dla trzech nowych modułów — bez błędów;
- `npm run m5:corpus:validate` — status `ready`, bez ostrzeżeń.

Nie zmieniono pipeline'u v20, bazy, API, UI, modeli ML, segmentacji ani danych
użytkownika. Produkcyjna integracja pozostaje w TASK-0312.
