---
title: Poprawa wykrywania pełnych plansz — plan po audycie Opus 5.5
status: accepted
last_updated: 2026-11-03
---

# Poprawa wykrywania pełnych plansz

## Zgody, cel i dowody

Operator zlecił cały plan T0–T6 oraz zaakceptował kilka godzin pracy, testy i audyty Opus 5.5/high. Przekazanie planu i niezbędnego kodu do Anthropic jest zatwierdzone. Rzeczywisty trening, wdrożenie, merge/push, migracje operatora i restarty pozostają osobnymi operacjami. Rewizja wymaga focused review zamknięcia uwag audytu przed implementacją. Focused review R2 Opus 5.5/high: PASS, bez P0/P1; raport `../quality/FULL_BOARD_PLAN_AUDIT_claude-opus-5-5_R2.md`. Rezerwacja po sprawdzeniu wszystkich gałęzi: T0=TASK-1154, T1=1155, T2=1156, T3=1157, T4=1158, T5=1159, T6=1160. Szczegółowy task powstaje przed każdym krokiem według TASK_TEMPLATE. P2: T0 sprawdza wszystkie porównania wersji oraz artefakt 462205; T1/T4 wykluczają przykłady diagnostyczne z VALIDATION-B i REGRESSION; T4 ustala kryterium błędu względem ludzkiej geometrii przed etykietowaniem, T4/T6 raportują bazę modelu z polityką T0 oraz poprzednią politykę oddzielnie.

Najpierw uszczelniamy akceptację błędnych siatek, następnie poprawiamy wykrywanie plansz istniejącym trenerem detektora. Zamrożenie detektora dotyczy polityki korekt, nie istniejącego screen+grid. Automatyczna akceptacja pomija kody błędów dopasowania. Dla 462205 zapisano identyczny obszar detektora obu wersji, lecz dokładna przyczyna pominięcia rzędu wymaga T1. Nie obiecujemy bezbłędności każdej przyszłej gry. Filmy nie są wymagane: materiał to zdjęcia i zatwierdzona geometria.

Podejrzany wynik uruchamia ograniczoną próbę poprawy, a nierozstrzygnięty pozostaje do ręcznej korekty. Ponowne rozpoznanie kolejki korekt nigdy samo nie zatwierdza propozycji. Nowa gra nie dziedziczy dowodu jakości innych gier.

Pełne wsparcie innych układów, dodatkowa sieć kompletności oraz klasyfikator symboli są poza zakresem. Model deklaruje możliwości i blokuje nieobsługiwany układ; nie nazywamy blokady pełną obsługą. Kolejny układ wymaga konkretnej gry, danych i osobnej zmiany bazy, symboli, wyszukiwania oraz pozostałych odbiorców.

Stan realizacji 2026-11-03: T0 / TASK-1154 wykonany i zweryfikowany; audyt Opus 5.5/high PASS, bez P0/P1. Nowe operacje przypinają v2, historyczne v1 zachowują interpretację. Szczegóły: `../quality/TASK-1154_VERIFICATION.md`. TASK-1153 scalony do bazy `448f75e7` przez roota za osobną zgodą operatora; warunek integracyjny T5 spełniony. T1–T6 pozostają do wykonania.

## Etap A — Bezpieczeństwo i potwierdzenie przyczyny

### T0 — Uszczelnienie automatycznej akceptacji

Wprowadzić nową wersję NEURAL_AUTO_CROP_POLICY wspólną dla workera i API. Blokują: NEURAL_GRID_FIT_FAILED, NEURAL_GRID_FIT_OUTLIERS, niekompletne/niejednoznaczne przypisanie pozycji, niepoprawna geometria, brak rzeczywistych pikseli oraz nieobsługiwany układ. Egzekwowanie: neural_pending_payload, qualify_v3_engine_acceptance i handler reinferencji. API sprawdza dowody ponownie, nie ufa statusowi workera.

Nowe operacje przypinają nową politykę; historyczne zachowują swoją. Nie zmieniamy korekt ręcznych. Stare oczekujące operacje pokazują politykę; skorzystanie z zabezpieczeń wymaga nowego przygotowania.

Odbiór: fallback po błędzie dopasowania nie jest automatic; zapisany kandydat 462205 z FIT_OUTLIERS pozostaje do korekty. To nie wykrywa wszystkich możliwych pominięć rzędów.

### T1 — Odtworzenie wejścia sieci i dane

Odtworzyć dla 462205 oraz dostępnych dobrych/błędnych przykładów: oryginał, obszar detektora, rzeczywisty wycinek z marginesem, surowe i dopasowane punkty, akceptację i powody. Porównać z pełną geometrią zatwierdzoną przez człowieka. Raport określa, w ilu błędnych przypadkach brakujący fragment leży poza wycinkiem sieci; bez GT nie udawać diagnozy.

Wersjonowany zapis diagnostyczny: checksum źródła/modelu, ustawienia, macierz transformacji, rozmiar wyjścia, interpolacja i wypełnienie. Obraz wejścia odtwarzany z metadanych; brak blobów w tabelach domenowych.

Policzyć oddzielnie zatwierdzone plansze, pełne zdjęcia detektora, rzeczywiste dobre/złe predykcje z ludzkim odniesieniem, niezależne grupy i ograniczenia pochodzenia. Zachować role, historyczne użycie, kopie i bufory. Przykłady diagnostyczne nie są niezależnym testem. Odbiór: konkretne liczby i diagnoza albo jawnie brakujące dowody. Braki nie blokują ręcznej korekty.

### T2 — Jawne możliwości modelu i nowej gry

Pakiet deklaruje układ planszy i strony: obecnie 5 kolumn × 3 wiersze, strona 3 × 3. Zgodność sprawdzić przed inferencją i przed akceptacją. Brak obsługi: czytelny komunikat, zachowane źródło, bez wciskania w 24 punkty. Nowa zgodna gra otrzymuje propozycje; automat wymaga oceny tej gry. Układ nie dowodzi zgodności wyglądu. Nie usuwać ograniczeń schematu pozorną zmianą sieci.

Punkt kontrolny A: raport diagnozy/gotowości. Przed rzeczywistym treningiem ustalić koszt i trwały limit kroków/czasu. Zlecenie całego planu obejmuje dalszą implementację, nie uruchomienie treningu bez tej zgody.

## Etap B — Poprawa rozpoznania i oceny

### T3 — Detektor w istniejącym procesie korekt

Nowa wersja polityki korekt dopuszcza screen+grid; wykorzystać SCREEN_GRID_V1, ScreenGridBatches, photo_evaluator, nie drugi trener. Detektor: wyłącznie kompletnie opisane zdjęcia. Częściowe zdjęcia nadal dla punktów w grid-only. Nieopisane plansze nie są tłem. Brak pełnych zdjęć daje liczniki/komunikat, bez pozornego treningu detektora.

Checkpoint nowej polityki wybierany od oryginalnego zdjęcia: poprawność całych zdjęć, poprawność plansz, mniejszy błąd punktów, wcześniejszy krok. Gry ważone równo. REGRESSION nie wybiera checkpointu. Zachować istniejące augmentacje przesunięcia/skali/obrotu; rozszerzyć o asymetryczne błędy obszaru wykazane przez T1.

Wersjonowany ratunek: jedna ponowna detekcja zdjęcia i najwyżej jeden dodatkowy wycinek podejrzanej planszy. Wyzwalacz: blokada geometrii lub kompletności T4. Większa rozdzielczość/margines dopuszczone wyłącznie po objęciu treningiem i walidacją. Brak dopuszczonego wariantu oznacza korektę ręczną, bez improwizowanej skali. Wznowienie zachowuje checkpoint, dane i zużycie budżetu; lost response nie tworzy nowego treningu.

### T4 — Kompletność i rozdzielona kalibracja

Kontrole: kompletność/pewność punktów, dostępne piksele, zgodność obszaru detektora i siatki, nietypowe proporcje względem zatwierdzeń gry, sąsiedzi z uwzględnieniem perspektywy, rozbieżność podstawowy/ratunkowy. Sąsiedzi są sygnałem podejrzenia, nie dowodem poprawności; brak odniesienia nie oznacza zaliczenia. Nie dodajemy sieci kompletności. Gdy sygnały nie wystarczą, ręczna akceptacja i osobna decyzja badawcza.

TRAIN uczy; VALIDATION-A wybiera checkpoint/ustawienia; VALIDATION-B dobiera progi; REGRESSION to końcowy zamrożony test. A/B utrwalone w istniejącym rejestrze dowodów; całe grupy/kopie/bufory chronione. Nie przenosić TRAIN/REGRESSION do kalibracji.

Automat per gra wymaga w VALIDATION-B oraz REGRESSION osobno minimum 30 rzeczywistych błędnych przypadków z różnych źródeł po scaleniu kopii i 30 dobrych z różnych źródeł, etykiet z ludzkiej geometrii, zera przyjętych przycięć i wzrostu poprawnych automatycznych wyników względem bazy. To minima produktu, nie gwarancja statystyczna. Raport liczebności/zależności; przedziały ufności tylko przy uzasadnionej niezależności. Syntetyczne przycięcia nie liczą się do kalibracji/odbioru. Brak danych blokuje kwalifikację automatu, nie trening ani propozycje pod nadzorem człowieka.

## Etap C — Interfejs i odbiór

### T5 — Panel, propozycje, HTML

Edytor korzysta z TASK-1153. Warunek: integracja za osobną zgodą; bez niej T5 nie jest done. API rozszerzyć o możliwości modelu, kwalifikację gry, kontrole/powody zatrzymania, ratunek, gotowość danych detektora/kalibracji. Pełny pion: backend, OpenAPI, wygenerowany klient, wrapper, request test. Panel odróżnia propozycje, dopuszczenie automatyczne i ludzkie zatwierdzenia. Niezweryfikowane wyniki nie są „poprawne”. HTML: oryginał, faktyczne wejście sieci, zapisane cięcie, baza, kandydat; odróżnić viewport od model input.

### T6 — Końcowe porównanie i przygotowanie wdrożenia

Baza/kandydat na tych samych oryginałach. Zachować istniejące bramki braku regresji zakresu gier i poprawy bieżącej. Raport osobno: jakość wszystkich propozycji (również zatrzymanych), błędne dopuszczenia, poprawne automatyczne, udział korekty, czas/koszt. Odrzucenie wszystkiego nie jest poprawą rozpoznania. Pozostałe nieopisane plansze: tylko wizualne porównanie, bez potwierdzonej metryki.

Przygotować zgodność API/workera, migracje Alembic, trwałość i przywrócenie modelu. Apply nie przelicza historii i nie zmienia korekt. Każdy task: audyt, testy, Outcome, osobny wersjonowany commit, task-close. Otwarte P0/P1 po rundzie poprawek blokują task; brak audytora nie jest PASS.

## Mapa wymaganie → task → test

| Wymaganie | Zadania | Kryterium |
|---|---|---|
| FIT_FAILED/OUTLIERS nie przechodzi | T0 | Identyczne decyzje API/workera, fallback i 462205 |
| Rzeczywiste wejście sieci | T1,T5 | Deterministyczne odtworzenie wycinka/transformacji |
| Detektor uczy się korekt | T3 | Pełne zdjęcia zmieniają detektor, częściowe nie są tłem |
| Pominięty rząd nie jest cichym sukcesem | T0,T4,T6 | Poprawny wynik lub jawna korekta |
| Nie przejąć sąsiada | T3,T4 | Perspektywa, sąsiedzi, niejednoznaczne dopasowanie |
| Nowa gra nie dziedziczy jakości | T2,T4 | Bez kwalifikacji brak automatu |
| Brak przecieku kalibracji | T1,T4 | Trwałe A/B, grupy/kopie/bufory/historia |
| Korekty pozostają ręczne | T5,T6 | Reinferencja nie zatwierdza geometrii/symboli |
| Restart/lost response | T3,T6 | Bez duplikacji i odnowienia budżetu |
| Zgodna historia | T0,T2,T6 | Stare wersje zachowują semantykę |

Weryfikacja planowana: scoped API/worker, PostgreSQL, Admin/Reviewer interakcje, ONNX, lint/typecheck/build, docs:check i code-map:check. Statyczny audyt nie zastępuje wykonania. Etapy kolejno; po A ocena danych/budżetu, nie automatyczny trening. Niedobory blokują tylko zależne funkcje, ręczna korekta pozostaje dostępna.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T0 — Bezpieczna akceptacja | gpt-6-astra | high | Spójność workera/API i historii | Claude Code claude-opus-5-5/high |
| T1 — Diagnoza i dowody | gpt-6-astra | high | Przyczyna i ochrona danych | Claude Code claude-opus-5-5/high |
| T2 — Możliwości modelu i gry | gpt-6.1-sol | high | Ograniczenia i kontrakty | Claude Code claude-opus-5-5/high |
| T3 — Trening detektora | gpt-6-astra | high | Istniejący trener i end-to-end | Claude Code claude-opus-5-5/high |
| T4 — Kompletność i kalibracja | gpt-6-astra | high | Ochrona testów i dopuszczenie | Claude Code claude-opus-5-5/high |
| T5 — Panel i HTML | gpt-6.1-sol | high | Propozycje i kontrakt | Claude Code claude-opus-5-5/high |
| T6 — Odbiór | gpt-6.1-sol | high | Trwałość i historia | Claude Code claude-opus-5-5/high |
