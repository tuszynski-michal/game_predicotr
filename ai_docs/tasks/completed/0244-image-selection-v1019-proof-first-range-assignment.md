---
title: TASK-0244 image selection v10.19 proof-first range assignment
status: done
release: "0.6"
last_updated: 2026-08-18
---

# TASK-0244 — Image selection v10.19 proof-first range assignment

## Status

`done — wydanie odrzucone jakościowo i zastąpione przez TASK-0245 / v10.20`

## Goal

Zakończyć serię korekt selektora jednym proof-first wydaniem, w którym zakres
automatyczny zawsze wynika z odczytanych etykiet wybranego JPEG-a, a pełny zimny
przebieg około 40–42,5 tys. zdjęć trwa najwyżej 7 godzin.

## Incident evidence

- run v10.18 `229913–248184` został anulowany przy `8160/42420`; selekcja
  trwała `8750,081 s`, co daje projekcję około `12,6 h`,
- tylko `6/3488` weryfikacji zakończyło się szybkim potwierdzeniem, mimo że
  zakotwiczony OCR rozwiązał `2099` przypadków z trzech albo czterech etykiet,
- fallback poziomu 18 wykonał 3340 prób i nie dodał żadnego rozstrzygnięcia,
- w zakończonych runach v10.18 `200557–222912` i `177562–200583` wszystkie
  `1943 + 1961 = 3904` automatyczne wybory noszą
  `RANGE_CARDINALITY_INFERRED`,
- `_assign_cardinality_range` może wybrać JPEG bez `recognized_range`, nadać mu
  zakres z pozycji globalnej i promować go do `auto_selected`,
- `_strong_range_is_acceptable` wymaga obecnie, aby liczba wykrytych plansz
  była równa rozmiarowi pełnego zakresu. Odrzuca przez to poprawny odczyt 3–4
  widocznych etykiet, gdy nie wszystkie dziewięć plansz jest wykrytych.

## Non-negotiable rules

1. `auto_selected` musi wskazywać JPEG z własnym, zapisanym dowodem tego samego
   zakresu. Kolejność, liczność i sąsiedzi są wyłącznie walidacją.
2. Dwie etykiety nigdy nie wystarczają do automatycznego zakresu. Mogą tworzyć
   sugestię manualną, ale nie kanoniczny `range_start/range_end`.
3. Brak lokalnego dowodu pozostaje bez zakresu i trafia do review. Reconciler
   nie może zmienić go w automat ani udawać kompletnego pokrycia.
4. `skipped_unreadable` nie jest logicznym właścicielem zakresu i nie zalicza
   pokrycia wynikowego.
5. Nie powstaje v10.20 jako eksperyment. Warianty są benchmarkowane lokalnie
   bez rejestracji wersji; v10.19 zostaje opublikowany dopiero po przejściu
   wszystkich bramek.
6. Żaden kolejny job ani etap kolejki nie startuje przed akceptacją dry-runu
   właściciela.

## Plan implementation

### 1. Niezmienny korpus prawdy i diagnostyka

- Z zatrzymanego runu oraz dwóch zakończonych runów v10.18 zbudować
  deterministyczną próbę obejmującą auto, manual, duplikaty, wszystkie trasy OCR,
  rozmiary fragmentów i pozycje początku/środka/końca zbioru.
- Rozszerzyć istniejący modal o tryb szybkiego audytu zakresów: środek oraz
  kwantyle 35/65, widoczne odczyty OCR na pozycjach plansz, Enter = poprawny,
  pole pierwszego numeru = korekta, odrzucenie = brak użytecznego zdjęcia.
- Zapisywać osobno surowe obserwacje: checksum JPEG-a, pozycję planszy, odczytaną
  liczbę, confidence, trasę OCR i wyliczoną bazę zakresu.
- Dodać telemetrię przyczyny odrzucenia każdego mocnego odczytu, aby różnica
  `2099 resolved -> 6 confirmed` nie była ponownie ukryta.

### 2. Dowód zakresu z co najmniej trzech etykiet

- Mocny dowód jednej klatki wymaga co najmniej trzech różnych pozycji plansz,
  w tym jednej pary sąsiadującej, oraz jednej zgodnej bazy `number - position`.
- Widoczne mogą być dowolne trzy z dziewięciu, np. `1–3`, `3–5` albo `5–8`;
  niewidoczne plansze nie są syntetyzowane jako odczyty OCR.
- Zastąpić warunek `detected board count == full range size` sprawdzeniem, że
  każda odczytana etykieta ma zgodną wykrytą pozycję. Nie wymagać widoczności
  wszystkich dziewięciu plansz.
- Alternatywny dowód wieloklatkowy wymaga dwóch różnych checksum, co najmniej
  dwóch zgodnych etykiet na każdej klatce i łącznie co najmniej czterech różnych
  pozycji. Konflikt choćby jednej mocnej bazy zamyka automat.
- Odczyt dwuetykietowy, fuzzy, zakres z kursora, luka i sama liczność mogą tylko
  zasilić sugestię manualną.

### 3. Pięć kwantyli bez skanowania całej grupy

- Zachować kolejność `50% -> 35%+65% -> 15%+85%` i nigdy nie używać pierwszego
  ani ostatniego zdjęcia jako domyślnej próbki.
- Jeżeli środek ma mocny trzyetykietowy dowód i przechodzi jakość JPEG-a,
  zakończyć grupę bez OCR pozostałych czterech kandydatów.
- Gdy środek nie wystarcza, analizować 35/65 jednym batchem. Zgodny dowód kończy
  grupę; różne mocne zakresy oznaczają granicę semantyczną i podział fragmentu,
  a nie głosowanie większościowe.
- Dopiero potem analizować 15/85 jednym batchem. Brak mocnego dowodu po pięciu
  kwantylach daje manual review bez kanonicznego zakresu.

### 4. Reconciler nie może tworzyć prawdy

- Usunąć promocję kandydata z `recognized_range=None` do `auto_selected`.
- Zachować oryginalny dowód kandydata; nie zastępować go zakresem oczekiwanym.
- Globalne bounds mogą wykrywać duplikat, lukę, odwrócenie i zakres poza siatką,
  ale nie mogą nadawać numeru nierozpoznanej grupie.
- Dwa fragmenty z tym samym mocno udowodnionym zakresem mogą zostać scalone w
  jednego właściciela i duplikat. Nieudowodnione fragmenty pozostają w review.
- Dla manual review przechowywać `suggestedRange` oddzielnie od kanonicznego
  zakresu. UI nie może przedstawiać sugestii jako rozpoznanego zakresu.
- Raport osobno pokazuje: zakresy udowodnione, ręcznie zatwierdzone, oczekujące,
  duplikaty i rzeczywiście brakujące. Zielona ciągłość nie może powstać przez
  przypisanie kolejnych numerów nieznanym zdjęciom.

### 5. Budżet czasu

- Wyłączyć poziom OCR 18 dla automatycznego przebiegu, ponieważ w zatrzymanej
  próbce miał `3340` prób i `0` dodatkowych rozstrzygnięć. Może pozostać jako
  jawna akcja diagnostyczna w review.
- Wykonać jeden decode JPEG-a i jeden batch OCR etykiet na kandydat/poziom;
  współdzielić wynik pomiędzy geometrią, dowodem zakresu i wyborem jakości.
- Po naprawie bramki 3–4 etykiet rzeczywiście wykonywać early exit; raportować
  średnią i p95 liczby zweryfikowanych JPEG-ów na logiczną grupę.
- Profilować osobno decode, detekcję plansz, cropy etykiet, inference OCR,
  persistence i wall time. Optymalizować tylko zmierzony dominujący etap.

### 6. Bramy przed publikacją v10.19

- Testy mutacyjne muszą odrzucać: `+1`, `-1`, zamianę cyfry, dwie zgodne liczby,
  konflikt dwóch klatek, fragment obejmujący dwie strony oraz JPEG bez własnego
  dowodu.
- Invariant: każdy `auto_selected` ma wybranego JPEG-a z mocnym dowodem dokładnie
  jego kanonicznego zakresu; liczba `RANGE_CARDINALITY_INFERRED` w automacie
  wynosi zero.
- Deterministyczny audyt co najmniej 200 grup, warstwowy według tras i statusów,
  musi mieć zero błędnych zakresów. Błąd `±1` jest błędem blokującym.
- Zimny benchmark 5000 zdjęć na stagingu produkcyjnym musi prognozować najwyżej
  7 godzin dla 42 500 zdjęć. Następnie pełny zimny dry-run musi zakończyć samą
  selekcję w `<= 7 h`; upload jest raportowany osobno.
- Dry-run nie zapisuje wyników ani nie uruchamia kolejki. Pokazuje porównanie
  v10.18 -> kandydat: precision, auto/manual/unresolved, OCR calls/crops,
  średnie weryfikacje na grupę i czas.
- Dopiero po zerze błędnych zakresów w audycie właściciela zarejestrować jeden
  fingerprint `fast-image-selector-v10.19`, zrobić commit i uruchomić pojedynczy
  kontrolowany run. Kolejne etapy pozostają wstrzymane do jego odbioru.

## Likely files

- `services/worker/src/game_predictor_worker/images/selection/{adapters,engine,recovery,manifest,benchmark}.py`
- `services/worker/tests/test_image_selection_*.py`
- `services/api/src/game_predictor_api/{domain,storage,schemas,api}/image_selections.py`
- `apps/admin/src/features/image-selection/`
- `scripts/run_image_selection_*`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`

## Outcome

- Zaimplementowano manifest i adapter v10.19, trwałe obserwacje pozycyjne,
  wspólną bramkę proof-first oraz reconciler bez przypisywania z liczności.
- UI audytu odróżnia mocny dowód od sugestii i pokazuje zapisane odczyty OCR.
- Raport pokazuje częściowe, rzeczywiste pokrycie bez syntetycznego zazieleniania
  luk; `waiting_for_review` pozostaje prawidłowym wynikiem procesu.
- Pełne bramki kodu są zielone. Pierwszy zimny benchmark 5000 zdjęć zachował
  zero naruszeń dowodu, ale `3552,458 s` prognozowało `8,39 h`; zgodnie z bramką
  pełny run 32 079 nie wystartował. Telemetria wskazała OCR (`3214,957 s`) jako
  dominujący koszt.
- Kandydat zachowuje numer v10.19, ale po pomiarze dostał progresywne poziomy
  lattice `6 -> 12`, processed-first dla zakotwiczonego OCR i licznik postępu
  benchmarku. Ponowny zimny benchmark 5000 zakończył się w `666,585 s`, z zerem
  naruszeń dowodu i projekcją `1,57 h` dla 42 500 zdjęć.
- Kontrolowany run `7bd76e70-8c9a-4204-bab7-1dbfae32ac27` przeskanował 32079
  zdjęć w `4207,6 s`, po czym końcowa transakcja ujawniła błąd persistence:
  sugestia reprezentanta grupy `range_required` była oznaczana jako
  `selected_automatic`. Zapis ograniczono do gotowych statusów i dodano realną
  regresję PostgreSQL. Ten sam job wznowiono bez OCR i zakończył jako
  `waiting_for_review`: 1776 automatów, 491 grup do ustalenia zakresu, 316
  udowodnionych duplikatów oraz 1776 zgodnych plików wynikowych.
- Walidacja poprawki: worker `751/751`, API `339/339` z 26 jawnymi skipami,
  izolowana regresja PostgreSQL `1/1`, testy skupione `40/40`, Ruff i mypy dla
  256 modułów przechodzą. Fingerprint v10.19 nie zmienił się, ponieważ poprawka
  dotyczy wyłącznie materializacji projekcji.
- Po naprawie wystartował run v10.19 `7dbd3a54-8f6f-435d-bdbd-bf9e8373657a`
  na kompletnym stagingu 42420 JPEG-ów zakresu `229913–248184`; wynik trafia do
  `C:\Users\user\Documents\229913-248184 v10.19`. Do zamknięcia zadania
  pozostaje odbiór jakości proof-first przez właściciela.
- Odbiór właściciela wykazał przesunięte zakresy oraz błędną interpretację
  `1776 auto + 491 range_required` jako `2267` grup logicznych. Run został
  zatrzymany, kolejka wyłączona, a wcześniejsza decyzja „dwie etykiety nigdy nie
  wystarczają” została jawnie zastąpiona przez sekwencyjnie walidowany model
  v10.20 opisany w TASK-0245.
