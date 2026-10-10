---
title: Przegląd planu korekty układu przez Claude Code
status: active
last_updated: 2026-10-09
---

# Przegląd planu korekty układu

Audytor: Claude Code, claude-opus-5-5 / medium.
Zakres: plan z2026-10-09 i wybrane fragmenty committed baseline v1.7.293.
Końcowa weryfikacja na prośbę operatora; dostęp do narzędzi wyłączony. Ocena planu nie jest odbiorem UI.

**Werdykt: PASS.** Plan jest gotowy do implementacji TASK-0947–0949. Oceniam wyłącznie spójność planu; działający UI nie został sprawdzony. Restore w 0948 pozostaje warunkowy i niezaakceptowany, a plan poprawnie podaje ścieżkę bez restore.

**P0/P1:** brak.

Wcześniejsze uwagi są domknięte:
- przewijanie zmienia tylko `scrollTop` listy;
- `replaceState` obejmuje wybór maszyny, gry i stawki, a obecny `pushState` w `onStakeSelected` (`:1039`) jest wskazany do zmiany;
- pomiar Chromium jest w 0947.

Wymagania dotyczące pinów są jednoznaczne:
- źródłem jest `pinnedPoints` z summary;
- podgląd nie zależy od `selectedStake` ani `editor`;
- Save, reload i zmiana zakresu są opisane;
- przypadki 0/1/6 pinów, spinu 0, strat i `available=false` są wymienione;
- wymagany jest poprawny HTML wewnątrz klikalnej karty.

**P2-1 — sprzeczność przy przeliczaniu na złote.**
Plan nakazuje użyć istniejącego `managementAmount` i jednocześnie zakazuje „wymyślonej kwoty w złotych”. `managementAmount` przy `spinCost <= 0` zwraca `formatZloty(credits * 10)`. To jest właśnie kwota w złotych bez podstawy w danych slotu.

Korekta, jedno zdanie w sekcji kwot: „Wiersze pinów wywołują `managementAmount` wyłącznie przy `spinCost > 0` i znanym `stakeGrosze`. W przeciwnym razie pokazują kredyty z jawną etykietą. Gałąź `credits * 10` nie jest używana dla pinów.”

Dodatkowo przed 0947 warto potwierdzić, że `spinCost` jest dostępny w `ManagementStakeResponse` bez zmiany API. Jeśli nie jest, fallback na kredyty jest jedyną dopuszczalną ścieżką.

**P2-2 — niedookreślony stan „wymaga sprawdzenia”.**
Zdanie „zachować opis stanu; nie sugerować aktualnej wygranej” nie rozstrzyga, czy wiersze pinów zostają widoczne, czy są ukryte, gdy summary stawki jest oznaczone jako nieaktualne lub wymagające sprawdzenia.

Korekta: „Wiersze zamrożonych pinów pozostają widoczne z etykietą stanu z istniejącego kontraktu, na przykład ‚Wymaga sprawdzenia’. Nie są ukrywane ani przedstawiane jako aktualne.” Ten przypadek należy dodać do listy obowiązkowych przypadków pinów w 0947.

Obie poprawki są doprecyzowaniami, nie zmianą zakresu. Nie wymagają kolejnej rundy przeglądu planu. Wystarczy, że sprawdzi je ograniczony audyt implementacji 0947, który plan już przewiduje.

Nie zmieniałem plików i nie uruchamiałem narzędzi.

## Zamknięcie drobnych uwag przez autora planu

P2-1: plan i TASK-0947 wymagają spinCost>0 oraz znanej stawki przed użyciem
managementAmount. Dla pozostałych przypadków pokazują kredyty z etykietą,
bez gałęzi credits*10. Nullable spinCost istnieje w wygenerowanym
ManagementStakeResponse; nowe API nie jest potrzebne.

P2-2: zamrożone wiersze pozostają widoczne przy sprawdzaniu/nieaktualności
z etykietą istniejącego stanu. Dodano ten przypadek do odbioru0947.

Obie uwagi zamknięto w specyfikacji. Kolejnego audytu planu nie uruchamiano.
Potwierdzono gotowość planu, nie implementację; zadania0947–0949 pozostają todo.
