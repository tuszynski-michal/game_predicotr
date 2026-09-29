---
title: Symbol reference library for pending symbol cells
status: accepted
last_updated: 2026-09-29
---

# Plan: biblioteka wzorców dla oczekujących symboli

Decyzja właścicielska: `ai_docs/process/DECISION_LOG.md` D-464. Operator
zaakceptował plan 2026-09-29 i zlecił zapis planu oraz wykonanie wyłącznie
etapu A dla wszystkich ośmiu symboli gry `777`. Etapy B i C wymagają osobnego
polecenia. Praca odbywa się w worktree
`worktrees/symbol-reference-library` na gałęzi
`feat/symbol-reference-library`, a nie bezpośrednio na
`v1.1-vision-lab-hybrid-geometry`.

## 1. Stan obecny (fakty z bazy i próby 2026-09-29)

- Gra `777` ma jeden aktywny model symboli (iteracja 2, `spatial`, bez
  augmentacji) wytrenowany 2026-09-14 na 122 wycinkach z 18 zdjęć. Od tego czasu
  nie było ponownego treningu; 24 807 zdarzeń `reassign` operatora nie wpływa
  na kolejne predykcje.
- Oczekujące komórki bez flagi jakości z pewnością 60–80%: Winogron 11 777,
  Śliwka 10 362, Arbuz 8 578, Pomarańcz 7 934, Gwiazda 6 953, Wiśnia 4 535,
  Siedem 3 100, Cytryna 1 563.
- Próba odczytowa: biblioteka 2 706 komórek zweryfikowanych przez operatora
  (do 15 na symbol, import i zgodność z predykcją), głosowanie 7 najbliższych
  wzorców, wzorce z importu badanej komórki wyłączone.

| Metoda | Wszystkie (2 706) | Predykcja Arbuz 60–80% (157) |
|---|---:|---:|
| Aktywny model | 14,9% | 1,9% |
| Aktywny model po korekcie balansu bieli | 17,2% | 21,0% |
| Aktywny model na obrazie szarym | 10,6% | 0,0% |
| Biblioteka, sam kształt | 95,6% | 98,7% |
| Biblioteka, kształt + cechy sieci + barwa | 96,0% | 98,1% |

- Próba zawiera w 87% komórki, w których model się pomylił (poprawki
  operatora). Wynik aktywnego modelu w tej tabeli nie jest jego ogólną
  jakością.
- 50 oczekujących komórek „Arbuz 60–80%”: 43 pewne propozycje (28 Arbuz,
  15 innych symboli), 7 do przeglądu. Ocena wzrokowa agenta nie jest
  weryfikacją operatora.
- Ryzyko zaobserwowane w próbie: zasłonięte wiśnie z etykietą `Wiśnia` uczą
  bibliotekę, że nakładka przycisku nawigacji oznacza wiśnię.

## 2. Cel i zakres

Poprawki operatora mają poprawiać propozycje symboli dla oczekujących komórek
bez ponownego treningu sieci i bez automatycznego zatwierdzania. Zakres planu
to gra `777` i topologia 3 × 5.

Poza zakresem: geometria i cięcie siatek, laboratorium wizji i gałąź
`codex/symbol-split-pilot`, automatyczne zatwierdzanie, inne gry, zdalny
Reviewer.

## 3. Kluczowe reguły i decyzje

| Reguła | Treść |
|---|---|
| R1 Źródło prawdy | Decyzja operatora na komórce (D-462). Propozycja biblioteki nie zmienia `assigned_symbol_id`, `review_state` ani historii. |
| R2 Predykcja modelu | `prediction_symbol_code` i `prediction_confidence` pozostają bez zmian. Propozycja jest osobnym, wersjonowanym wynikiem. |
| R3 Dobór wzorców | `review_state = approved`, `assignment_source = human`, pełna widoczność, brak flagi jakości, aktywny symbol, tożsamość pikseli akceptacji równa bieżącej, `asset_mode = virtual_source`. |
| R4 Limit biblioteki | Do 15 wzorców na (symbol, import, zgodność z predykcją); wybór deterministyczny. Wyszukiwanie pełne, bez nowych zależności. |
| R5 Tożsamość wycinka | Wycinek jest odtwarzany z `render_spec` i zapisanej sumy pikseli. Niezgodna suma wyklucza komórkę i jest raportowana, a nie pomijana po cichu. |
| R6 Opisy | A: kształt (histogram kierunków krawędzi 4 × 4 × 8 oraz jasność 12 × 12, bez barwy). B: kształt + mapa cech aktywnego modelu po korekcie balansu bieli + histogram barwy. |
| R7 Pewność | Ustalona przed pomiarem: propozycja jest pewna, gdy w A i w B wszystkie 7 wzorców wskazuje ten sam symbol i oba opisy wskazują ten sam symbol. W innym razie `do_przeglądu`. |
| R8 Uczciwy pomiar | Przy ocenie wzorce z importu badanej komórki są wyłączone. Brak 7 dostępnych wzorców daje `do_przeglądu`. |
| R9 Zapis | Etap A nie zapisuje niczego w bazie. Wyniki trafiają do `artifacts/symbol-reference-library/`. |
| R10 Zasłonięcia | Do rozstrzygnięcia przez operatora (pytanie O1). Do tego czasu zasłonięte wzorce pozostają w bibliotece, a raport mierzy je osobno, gdy ocena operatora je oznaczy. |

## 4. Etapy i taski

### Etap A — dowód bez zmian w aplikacji

- **T1 / TASK-0740** — odczytowe narzędzie i raport dla ośmiu symboli.
- **T2 / TASK-0741** — ślepa ocena operatora na 200 komórkach i porównanie.

Bramka etapu: zgodność pewnych propozycji z oceną operatora co najmniej 98%
i żaden symbol poniżej 95%. Niespełnienie zatrzymuje etap B.

### Etap B — propozycje w weryfikacji symboli

- **T3 / TASK-0744** — tabela propozycji (Alembic) i handler workera.
- **T4 / TASK-0745** — rozszerzenie `listSymbolCellReviews` i liczników,
  OpenAPI, klient, test żądania.
- **T5 / TASK-0746** — grupowanie i podgląd wzorców w Adminie.

### Etap C — ponowny trening sieci

- **T6 / TASK-0747** — nowa iteracja modelu z poprawek, augmentacja barwy,
  test na importach nieobecnych w treningu.

Taski etapów B i C zostaną rozpisane według `TASK_TEMPLATE.md` przed ich
uruchomieniem.

## 5. Mapa wymaganie → task → test

| Wymaganie | Task | Test / kryterium |
|---|---|---|
| Rozpoznać oczekujące symbole | T1, T3 | zgodność i pokrycie per symbol, macierz pomyłek |
| Wynik najpierw do obejrzenia | T1, T2 | arkusze i raport bez zapisu w bazie |
| Nic nie zmieniać bez zgody | T1–T3 | sesja tylko do odczytu; zero zmian decyzji i predykcji |
| Uczenie na poprawkach | T3, T6 | nowa poprawka zmienia kolejne propozycje |
| Wdrożenie | T4, T5 | filtr i grupowanie w Adminie |

## 6. Ryzyka

- Błędna etykieta operatora w bibliotece powiela się w propozycjach.
  Ograniczenie: R7 oraz podgląd wzorców w etapie B.
- Zatwierdzenie masowe z 2026-09-28 (50 183 komórki) może zawierać
  nieobejrzane predykcje (pytanie O2).
- Nowa gra lub nagranie bez wzorców daje rzadkie propozycje do pierwszych
  poprawek.
- Gałąź zaczyna od `v1.7.51`; równoległe commity na gałęzi bazowej mogą
  użyć tych samych numerów wersji. Scalanie wymaga uzgodnienia numeracji.
- Numery decyzji w gałęzi `codex/symbol-split-pilot` (własne D-462, D-463)
  kolidują z gałęzią bazową; ten plan używa numeracji gałęzi bazowej.

## 7. Pytania otwarte

- **O1** Czy symbol pod przyciskiem nawigacji lub dłonią dostaje klasę, czy
  status nieczytelny? Blokuje regułę R10 i dobór wzorców w T3.
- **O2** Czy komórki z zatwierdzenia masowego 2026-09-28 były oglądane
  pojedynczo? Blokuje ich użycie w T3 i T6.

## Przypisanie modeli do zadań

Poziomu rozumowania nie da się ustawić jawnie z bieżącej sesji, dlatego
rekomendacja jest warunkowa. Względem propozycji z rozmowy T1 wykonuje model
bieżącej sesji, ponieważ prototyp i pomiary powstały w tej sesji; audyt
pozostaje niezależny.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T1 / TASK-0740 | claude-fable-5-1 | high | Przeniesienie sprawdzonego prototypu do narzędzia odczytowego; niskie ryzyko danych. | Tak: claude-opus-5-5, high |
| T2 / TASK-0741 | claude-fable-5-1 | high | Próbka ślepej oceny i porównanie wyników; wynik zależy od operatora. | Tak: claude-opus-5-5, high |
| T3 / TASK-0744 | claude-opus-5-5 | high | Migracja, handler workera, wznowienie i ochrona decyzji operatora. | Tak: claude-opus-5-5, high |
| T4 / TASK-0745 | claude-opus-5-5 | high | Zmiana kontraktu API z zachowaniem zgodności istniejących żądań. | Tak: claude-opus-5-5, high |
| T5 / TASK-0746 | claude-sonnet-5-5 | high | Interfejs na gotowym kontrakcie, regresje widoku weryfikacji. | Tak: claude-opus-5-5, high |
| T6 / TASK-0747 | claude-opus-5-5 | high | Trening, dobór zbioru testowego i bramka jakości modelu. | Tak: claude-fable-5-1, high |
