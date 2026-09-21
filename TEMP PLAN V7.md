# TEMP PLAN V7 — wykonanie selekcji zdjęć

Status: `in_progress`. Plik jest dziennikiem wykonania; nie zastępuje
zaakceptowanego planu `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`.

## Zasady wykonania

- Praca biegnie na `version-0.10`, bez worktree i bez dołączania trzech zmian
  użytkownika widocznych przed rozpoczęciem.
- Każdy task ma: implementację, testy domenowe, self-audyt, review Astra Medium,
  poprawki, ponowne testy, osobny commit `v0.10.NNN` i wpis do `CURRENT_STATE`.
- Nie wykonuję automatycznego zapisu JPEG-a bez własnego dowodu numeracji.
  Sąsiednie zdjęcia mogą tylko utworzyć ograniczone potwierdzenie 3+3 w tym samym
  wystąpieniu; nie mogą samodzielnie nazwać kadru.
- Przy pytaniu produktowym stosuję wartość wskazaną w planie lub bezpieczny
  domyślny wariant i zapisuję ją w Outcome taska.

## Stan

| Task | Status                | Rezultat i bramka przejścia                                                                                                                                                                                                 |
| ---- | --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| T00  | done, `v0.10.318`     | Model, runtime i korpus sprawdzone. Historyczny OCR v3 nie lokalizuje etykiet; nie jest dowodem v7.                                                                                                                         |
| T01  | done, `v0.10.319`     | Konfiguracja pełnych stron, kierunek, `cut`, style, zamrożony korpus i role splitów.                                                                                                                                        |
| T02  | done, `v0.10.320`     | Lokalizator poziomej siatki 3×3, OCR własnych etykiet i proof 5 / 3+3; realny pomiar wykazał odczyt na 777, lecz proof pozostaje bezpiecznie zablokowany do kalibracji geometrii T05.                                       |
| T03  | done, `v0.10.321`     | Wystąpienia, luki, niezależne kursory, EOF, restart i globalna finalizacja bez cofania kursora.                                                                                                                             |
| T04  | done, `v0.10.322`     | Ocena jakości per plansza, niepewność, ranking kandydatów i warningi góra/dół.                                                                                                                                              |
| T05  | done, `v0.10.323`     | Wersjonowana kalibracja i metryki fail-closed; realny probe nadal nie ma wiarygodnej geometrii, więc aktywacja pozostaje zablokowana.                                                                                       |
| T06  | done, `v0.10.324`     | Addytywna migracja, kanoniczna konfiguracja i API/OpenAPI; backend blokuje V7 przed odczytem źródła do T12.                                                                                                                 |
| T07  | done, `v0.10.325`     | Przypięty manifest, JSON checkpoint skanu/finalizacji, pause/cancel/restart oraz blokada driftu bez zapisu JPEG-a.                                                                                                          |
| T08  | done, `v0.10.326`     | Pierwszy output bez nadpisania, journal operacji, kontrola generacji i manifestu, blokada katalogu oraz recovery po awarii.                                                                                                 |
| T09  | done, `v0.10.327`     | Manual replace, pierwszy półautomat, ręczny no-OCR, częściowa strona 1–8 i retry.                                                                                                                                           |
| T10  | done, `v0.10.328`     | Formularz V7, kanoniczne granice stron, blokada odbioru, target `cut`, read-only sąsiedzi i trwałe kursory.                                                                                                                 |
| T11  | done, `v0.10.329`     | Bounded prepare 1–4 / seryjny OCR, limit 8 payloadów i read-only raport CPU/RAM/VRAM. Pięć źródeł dało ten sam digest; profil 4/8 jest najszybszy, ale V7 pozostaje zablokowane do T12.                                     |
| T12  | done, release blocked | Audyt manifestu, recovery i kompatybilności przeszedł, ale kalibracja i holdout mają puste mianowniki, a aktualny holdout zawiera źródło D-404. API pozostaje zablokowane; dodatkowo brakuje produkcyjnego pionu worker V7. |
| T13a | done, `v0.10.332`     | Odrębny evaluator holdoutu `reels_test`, wiążący truth i surowy snapshot z manifestem, inwentarzem, SHA oraz zaliczoną kalibracją; T05 nadal nie może używać holdoutu do kalibracji. |

## T02 — obecne wykonanie

1. Zachować czysty dowód: pięć zgodnych etykiet pozycji 3×3 albo dwa własne
   dowody 3+3 z różnych klastrów tego samego wystąpienia.
2. Wiarygodna sprzeczna etykieta veto'uje hipotezę; nieczytelna nie jest
   konfliktem. Lewa/prawa kolumna poza kadrem nadal może oznaczać pełne `seq_1-9`.
3. Dokończyć i zmierzyć lokalizator poziomy na reprezentatywnej ograniczonej
   próbce z każdego katalogu, raportując liczbę odczytów, konflikty i czas.
4. Nie commitować T02 bez task Outcome, testów realnego adaptera, self-audytu i
   Astra Medium.

## Definition of done całego planu

T12 może aktywować v7 wyłącznie po spełnieniu: co najmniej 95% odzyskanych
kwalifikowanych zakresów, co najmniej 95% poprawnych zapisanych reprezentantów,
zero błędnych zapisów automatycznych w opisanym zbiorze oraz 100% oznaczonych
przycięć góra/dół. Raport podaje mianowniki, fałszywe warningi i wyniki po
restartach; ręczne poprawki nie podnoszą wyniku automatu.
