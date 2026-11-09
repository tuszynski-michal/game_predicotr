---
title: Poprawa siatek, obrysów symboli i rzeczywistych wycinków
status: accepted
last_updated: 2026-11-09
---

# Poprawa siatek, obrysów symboli i rzeczywistych wycinków

Operator zlecił cały zakres T1–T4 i zaakceptował 6–10 godzin pracy z audytami
Opus przez terminal. Rzeczywisty trening, wdrożenie, merge, aktywacja i import
nie należą do tej zgody. Plan nie ma niezależnego PASS; każdy task ma własny audyt.

## Cel i fakty

Wspólna siatka 3 wiersze × 5 kolumn już istnieje. Pola mają wspólne granice,
ale obwiednie grafiki J/10/symbolu mogą być różnej wielkości. Obejmują całą
grafikę wraz z ozdobną otoczką, bez tła i sąsiada. Pomocniczy generator
jasności/koloru pomija fragmenty. W lokalnym HTML wykryto 14 obrysów mimo
odrzucenia ich z danych. Sprawdzony legacy render usuwa 8% z każdej strony.
Przykład 462205 ma również błędne położenie siatki; sam margines go nie naprawi.

## T1 / TASK-1170 — Czytelny podgląd i poprawne szkice

- Zwykły podgląd pokazuje zapisane 24 punkty bez zmiany perspektywy i korekt.
- Osobne przełączniki: Siatka pól, Obrysy grafik, Rzeczywiste wycinki; legenda
  przekazuje znaczenie również tekstem. Powiększony kadr odróżnia otoczenie od cropu.
- Obrysy wyłącznie z aktualnej adnotacji, nigdy z odrzuconego boxInPreview.
  Brak quadu daje brak obrysu. Pochodzenie i zatwierdzenie są jawne.
- Wycofać pomocniczy generator jasności/koloru z domyślnego przygotowania.
  Zachować szkice wymagające sprawdzenia, bez zastępowania grafik całymi polami.
- Dane podglądu przypinają geometrię i konfigurację renderowania. Rozszerzenie
  istniejącego API obejmuje backend/OpenAPI/SDK/wrapper/test żądania.
- Aktualne rewizje i liczniki; brak zapisów adnotacji podczas odczytu/podglądu.
- Ślepy kontroler nie otrzymuje wcześniejszych punktów/etykiet/propozycji.
  Chronione zdjęcia nie trafiają do pomocniczej galerii.

Odbiór: aplikacja i HTML przedstawiają te same adnotacje i ich pochodzenie.

## T2 / TASK-1171 — Porównanie pełnych pól z obecnym przycinaniem

Użyć VirtualCellRenderer i istniejącej oceny produkcyjnej. Najpierw geometria
człowieka, potem rzeczywiste predykcje modelu. Na TRAIN/A porównać 0.08 i 0.0,
zmieniając wyłącznie margines przy tym samym rozmiarze i przetwarzaniu.
Osobno ocenić cały istniejący kontrakt lab-rgb-symbol-onnx-v1 (różni się także
przetwarzaniem). Żadnego trzeciego wariantu po obejrzeniu końcowego testu.

Mierzyć pełną grafikę, obcego sąsiada, pomylenie komórek i brak pikseli oraz
klasyfikację tych samych ręcznie oznaczonych symboli przy przypiętych wagach.
Pewność modelu nie jest etykietą. Rekomendacja wymaga mniej przycięć, braku
nowych uszkodzeń/przejęć, pogorszenia klasyfikacji i wzrostu błędnych akceptacji
osobno w każdej grze. Niedobór zatwierdzonych obrysów/klas daje brak danych.
Korzyść cropu przy pogorszeniu klasyfikacji blokuje zmianę produkcji i wskazuje
osobną potrzebę dostosowania klasyfikatora.

## T3 / TASK-1172 — Powiązanie danych z istniejącym uczeniem

Wykorzystać wdrożone R0–R3, bez nowego trenera. Policzyć bieżące geometrie,
obrysy, widoczność, klasy i braki ról. Obrys pozostaje niezależny od siatki.
Zachować TRAIN/A/B/REG, powtarzalność, kopie, sesje, bufory i historię użycia.
462205 jest diagnostyczny. Przed treningiem i oceną przypiąć kontrakt cropów;
zmiana kontraktu wymaga nowego dowodu, stary raport nie zatwierdza zmiany.
Detektor dostaje pełne zdjęcia; częściowe etykiety nie tworzą tła. Zachować
rzeczywiste wejście sieci i ograniczony ratunek. Regularność nie dowodzi trafienia.

Odbiór: test przepływu etykiet/ustawień. Oddzielić gotowość kodu, danych i
zmierzoną jakość; brak danych nie udaje ukończonego treningu.

Doprecyzowanie integracyjne D-597: poprawny zamrożony pomiar u/δ może służyć
wyłącznie diagnostyce 8%/0% mimo rzeczywistej blokady oracle obecnego cropu.
Brak/unknown i niespójne dowody nadal blokują; trening i publikacja zachowują
strict kwalifikację. Historia/audyt T2 pozostają niezmienione; poprawka w T3.

## T4 / TASK-1173 — HTML i odbiór

Lokalny HTML: oryginał, wspólna siatka, zatwierdzone obrysy albo ich brak,
rzeczywiste wejście NN, 15 aktualnych i porównywanych rastrów produkcyjnych,
przycięcia/sąsiad/klasyfikacja jeżeli istnieją etykiety. Oddzielić poprawę UI,
cropu i modelu. Pokazać porażki. Nieoznaczone zdjęcia są tylko wizualizacją.

## Testy i granice

| Wymaganie | Task | Odbiór |
|---|---|---|
| Brak odrzuconych obrysów | T1,T4 | Brak quadu oznacza brak obrysu |
| Wspólne granice i perspektywa | T1 | Zachowane 24 ludzkie punkty |
| Pełne J/10/ramki/ciemne grafiki | T2 | Rzeczywiste rastry i etykiety |
| Brak przejęcia sąsiada/przycięcia | T2,T3 | Ta sama instancja, brak kompensacji |
| Brakujący rząd | T3,T4 | Nie zalicza regularnej błędnej siatki |
| Ochrona pomiaru i korekt | T1,T3 | Brak hints w blind i zapisów read-only |
| Restart/lost response/currentness | T1–T4 | Testy kontraktu i trwałości |
| Klasyfikacja | T2,T4 | Pełniejsze rastry nie ukrywają gorszych klas |

Testy pionu API/workera/PostgreSQL/Admin, lint, typy, build, docs:check,
code-map:check. Wyniki zapisać po wykonaniu. Każdy task: Opus przez terminal,
Outcome, task-close i osobny wersjonowany commit. Otwarty P0/P1 blokuje commit;
brak audytora nigdy nie oznacza PASS. Stosować CROSS_AUDIT (limit 1800 s).
Nie przewidujemy migracji; używamy istniejących rewizji i konfiguracji.
Default/margines/model nie zmieniają się przez samo przygotowanie poprawki.
Inne gry wymagają swoich dowodów jakości. Zdjęcia wystarczają, film zbędny.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T1 / TASK-1170 — Podgląd i szkice | gpt-6.1-sol | high | Kontrakt, UI i ochrona adnotacji | Claude Code claude-opus-5-5/high |
| T2 / TASK-1171 — Porównanie wycinków | gpt-6-astra | high | Geometria, render i klasyfikacja | Claude Code claude-opus-5-5/high |
| T3 / TASK-1172 — Dane i uczenie | gpt-6-astra | high | Podział danych i zgodność oceny | Claude Code claude-opus-5-5/high |
| T4 / TASK-1173 — HTML i odbiór | gpt-6.1-sol | high | Porównanie i trwałość | Claude Code claude-opus-5-5/high |
