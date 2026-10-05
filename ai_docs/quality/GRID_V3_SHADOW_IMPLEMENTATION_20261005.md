---
title: TASK-0805 — odbiór implementacji shadow
status: done
last_updated: 2026-10-05
---

# TASK-0805 — odbiór implementacji shadow

## Zakres i stan

Operator uruchomił V3-D. Implementacja znajduje się w worktree
`C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3`, na
`feat/grid-engine-v3`. Przygotowano neutralny rdzeń CPU, ograniczony job
porównania, osobną historię z migracją 0142 i manifestem v5 oraz pion
API/OpenAPI/klient/Admin/Reviewer. Przełącznik pozostaje domyślnie wyłączony.

Nie wykonano migracji ani zapisów w bazie operatora, scalenia, wdrożenia,
aktywacji modelu ani treningu. Nie odczytano nowych danych holdout.
TASK-0805 zakończył odbiór kodu, izolowanych testów PostgreSQL i UX oraz
techniczne warunki Definition of Done. Nie wolno przedstawiać tej
implementacji jako uruchomionej funkcji działającej aplikacji.

## Zachowanie

- Start przyjmuje wyłącznie requestId i 1–20 źródeł istniejących w aplikacji.
  Serwer zamraża model, SHA, wymiary, geometrię i aktywne sloty.
- Dopasowanie do referencji zachowuje numerację przy brakach. Dodatkowe
  detekcje nie tworzą nowych aktywnych plansz. Brak geometrii daje unknown,
  a nie fałszywą informację o polu poza zdjęciem.
- Mumie mają powód NEURAL_GRID_GATE_UNCALIBRATED. Wszystkie propozycje
  wymagają ręcznego przeglądu; zakończenie joba nie zatwierdza siatek.
- Inferencja odbywa się w kontrolowanym procesie CPU z deadline i przerwaniem
  przy anulowaniu. Publikacja ponownie sprawdza źródło i aktualny lease.
- Historia zachowuje wersje obu silników. Wynik nieaktualny nie może zostać
  podpięty pod nową rewizję korekty. Identyczny już wysłany zapis może
  skorzystać z istniejącego idempotentnego API po utracie odpowiedzi.
- Admin pokazuje pełne 24 węzły. Edytor jawnie opisuje szkic z czterech
  narożników, po czym używa istniejącej korekty i przypisywania symboli.
- Historia porównań blokuje usuwanie jej źródeł oraz retencję stagingu.
  Nie dodano cichego usuwania historii ani CASCADE.

## Weryfikacja wykonana bez bazy operatora

| Kontrola | Wynik | Granica dowodu |
|---|---|---|
| Klient Admina, właściwy runner TSX | 79 PASS | Atrapy żądań HTTP; nie połączenie z wdrożonym API |
| Regresje neural_grid i hybrid_v3, transitive import boundaries | 38 PASS, 3 pominięte selekcją | Bez treningu, rzeczywistej inferencji CPU z modelem i odczytu artefaktu kalibracji |
| Funkcje UI i kontrakt launchera | 10 PASS | Testy lokalne |
| Interakcje panelu Admina | 8 PASS | Obejmują restart strony, utratę odpowiedzi, obraz, stale, historyczne wersje oraz opóźniony GET/loading/empty |
| Interakcje shadow Reviewera | 2 PASS | Atrapy API i istniejący edytor |
| Regresje istniejącej korekty Reviewera | 14 PASS | Natychmiastowy podgląd i przypisywanie symboli |
| Target shadow Reviewera po poprawce replay | 5 PASS | Identyczny retry dopuszczony; nowe polecenie blokowane przy stale |
| Typecheck Admina/Reviewera, lint zmienionego UI | PASS | Końcowe wygenerowane DTO i poprawki audytu |
| Build Admina i Reviewera po audycie | PASS | Usługi nie zostały uruchomione; ostatnie poprawki wyłącznie Admina: build 20,11 s PASS |
| API composition i wybrane regresje profilu/audytu | 32 PASS | Bez PostgreSQL |
| Pakiet backendu i przygotowane testy PostgreSQL | 108 PASS, 2 SKIP | PostgreSQL świadomie nie uruchomiono |
| Regresje cleanup i historii | 14 PASS | Atrapy; odmowa resetu przed SQL/usuwaniem artefaktów |
| Końcowe storage/retention i blokada KEY SHARE | 16 PASS | Część testów wspólna z poprzednimi pakietami; nie sumować wyników |
| Nowe testy workera i neutralnego rdzenia | 20 PASS | Dwa osobne procesy, repozytorium plikowe, atrapy źródła; bez rzeczywistego PostgreSQL |
| Mypy zmienionego API | 9 modułów PASS | W tym main/router/config/jobs i pięć modułów shadow, typowane zależności z follow-imports=silent |
| Mypy neutralnego rdzenia, handlera/dispatch, CLI | 8 + 2 + 1 modułów PASS | Kontrole źródeł worktree, bez wyciszania błędów tych modułów |
| Ruff zmienionego Pythona | 65 plików PASS | Bez masowej zmiany cudzych plików |
| Formatowanie Pythona i git diff --check | PASS | Dwa nowe pliki poprawiono; cudze zmiany pozostają zachowane |
| OpenAPI i wygenerowany klient | PASS | Nowy proces eksportera wybiera źródła swojego worktree |
| Końcowe przygotowanie odbioru PostgreSQL | 4 SKIP | Wymuszony brak opt-in; bez połączeń, migracji i zapisów |
| PostgreSQL: odczyt w nowym procesie | 1 PASS, 35,29 s | Rzeczywisty wynik, FK i rola aplikacyjna; osobna baza testowa |
| PostgreSQL: współbieżność blokad gry i źródła | 1 PASS, 18,75 s | Dwa połączenia, Game FOR KEY SHARE czeka przed blokadą źródła |
| PostgreSQL: nowe gry, parent/child RLS i pruning | 1 PASS, 34,46 s | Dwie gry w osobnej bazie, realna rola aplikacyjna |
| PostgreSQL: migracja i odmowa niepustego downgrade | 1 PASS, 19,05 s | Wyłącznie izolowana baza testowa, historia zachowana |
| Kontrola usunięcia zasobów testowych w nowym procesie | PASS | Brak baz TASK-0805 i tymczasowych ról; odczyt bez zmian |
| Mobilny smoke panelu i istniejącego edytora, Edge Chromium | PASS, 360 × 844 i 390 × 844 | CDP touchStart/touchEnd; bez fizycznego Androida, atrapy API i obrazu |

Kroki mają jawne limity czasu; ich raporty są w
`artifacts/grid-v3-deployment-20261004/task0805-*.json`. Pierwszy pełny Mypy
z błędnie zapisanym mypy_path nie rozwiązywał importów. Przywrócono trwałą
listę dwóch katalogów źródeł w pyproject.toml. Próby pełnej kontroli zostały
przerwane limitem i ich drzewa procesów zakończono. Ostateczna kontrola
zmienionych modułów z typowanymi zależnościami przechodzi w nowym procesie;
nie raportujemy wcześniejszego timeoutu jako sukcesu pełnej kontroli repo.

## Audyt i granice odbioru

Niezależny audyt gpt-6-astra high wskazał problemy dotyczące drugiego odczytu
rewizji, argumentów dopasowania, retry korekty, walidacji Infinity, deadline,
blokad usuwania i historycznej wersji baseline. Wprowadzono poprawki oraz
regresje. Końcowy audyt statyczny potwierdził zamknięcie wszystkich P0–P2,
w tym kolejność Game FOR KEY SHARE przed blokadami sekwencji/źródła/joba.

Przygotowany, domyślnie pomijany test PostgreSQL tworzy osobną bazę `*_test`
oraz tymczasową rolę. Sprawdza migrację istniejącej gry, partycje nowych
gier, rzeczywiste rekordy z FK, publikację i ponowny odczyt, parent i direct
child RLS, brak kontekstu gry, pruning oraz odmowę downgrade z historią.
Operator zezwolił na te operacje testowe 2026-10-05. Wszystkie cztery testy
przeszły z limitem 120 s każdy. Teardown usunął zasoby testowe, co potwierdzono
dodatkowym odczytem w nowym procesie. Nie migrowano bazy operatora.

Odbiór po restarcie rzeczywistego workera połączonego z PostgreSQL oraz
równoczesna publikacja i korekta pozostają granicami dowodu. Testy jednostkowe
odtwarzają te ścieżki, ale nie zastępują pełnego odbioru operacyjnego.
Cztery przygotowane testy PostgreSQL obejmują także odczyt trwałego wyniku
w osobnym procesie oraz dwa połączenia przy Game FOR UPDATE/FOR KEY SHARE.
Zebrano je najpierw z wymuszonym opt-in=0 (4 SKIP), następnie po zgodzie
operatora wykonano z opt-in=1 (4 PASS). Kontrola Definition of Done wykryła
jeszcze brak jawnego loading/empty panelu i mobilnego dowodu dotyku.
Poprawiono stany oraz minimalną wysokość etykiet wyboru (48 px) i przycisków
panelu (44 px); niezależny audyt poprawek nie wskazał P0–P2.

Mobilny smoke uruchomił zainstalowany Edge z odrębnym profilem i lokalną
statyczną fixture, bez głównych usług. W obu viewportach dotyk wybrał zdjęcie
i przycisk startu z atrapy API, a istniejący edytor pozwolił wybrać pole oraz
przypisać symbol. Brak poziomego overflow, 15 cropów, zero zapisów i zero
wyjątków przeglądarki. Raport i cztery screenshoty:
`artifacts/grid-shadow-mobile-smoke/`. Obejrzano oba ekrany 360 px.
Nie testowano fizycznego Androida ani połączenia z bazą operatora. Początkowe
błędy harnessu (podwójny React, brak wrappera mobile i tap podczas reflow)
poprawiono w izolowanym teście; nie zmieniano istniejącego edytora.
Końcowe 8 testów interakcji Admina, typecheck, lint bez ostrzeżeń,
formatowanie i build (20,11 s) PASS. Nowy proces potwierdził zero procesów
Edge z profili testowych. Końcowy niezależny audyt kodu i DoD: brak P0–P2.

Główny checkout zawiera cudzą niecommitowaną migrację 0141. Nowa 0142 ma
parent 0140. Przed jakimkolwiek scaleniem należy uzgodnić pojedynczy head
Alembic oraz schema guard. Działające API z reload nie może otrzymać kodu
wymagającego 0142 przed kontrolowanym wdrożeniem migracji.

## Porównanie z TASK-0805 i zaakceptowanym V3-D

| Kryterium zadania | Dowód | Ocena |
|---|---|---|
| 1. Opt-in i wyłączenie topologii 3 × 3 | Testy aplikacji/API, jawna flaga API i workera | PASS |
| 2. Ten sam SHA, oddzielne wyniki i wersje, bez etykiet symboli | Binding magazynu, checksumy modelu, granice importów rdzenia | PASS |
| 3. Zachowanie aktywnych slotów i numerów, odrzucenie dodatkowej planszy | Testy dopasowania pięciu slotów i braku środka | PASS |
| 4. Zamrożone rewizje i jawny drift | Testy źródła/modelu, drugiego odczytu i stale w UI | PASS |
| 5. Braki i widoczność, brak zapisu cropów/symboli przez shadow | Testy missing/partial/outside/unknown i kontrakt handlera | PASS |
| 6. Restart, utrata odpowiedzi, lease fencing i unikalność | Worker w nowych procesach, replay UI/API, nowy proces PostgreSQL, powtórna publikacja tego samego ID | PASS |
| 7. Lifecycle i parent/direct child RLS | Test PostgreSQL nowych gier, scope-less/cross-game odmowa, pruning i migracja istniejącej gry | PASS |
| 8. Porównanie i zwykła korekta z symbolami | Testy Admina/Reviewera, regresje natychmiastowego podglądu i mobilny smoke dotyku | PASS |
| 9. Regresje, lint, typy, kontrakt i build | Tabela wykonanych kontroli i końcowe kontrole poprawek UX | PASS |
| 10. Audyt, osobny commit i dokumentacja | Końcowy audyt bez P0–P2, task completed, Outcome/CURRENT_STATE, commit v1.7.191 | PASS |

Zakres V3-D z planu zachowano: równoległy kandydat dla tego samego źródła,
oddzielna wersjonowana historia gry, porównanie w Adminie i jawna korekta,
bez automatycznego zastępowania geometrii ani decyzji człowieka. Kontrakt
2026-10-05 rozszerza wejście o profil Mumii i ogranicza job do 20 źródeł.
Brama skali nadal poprzedza przyszłe masowe przetwarzanie.

## Definition of Done

- Funkcjonalność i dane: kryteria 1–7 potwierdzone; migracja przez Alembic,
  manifest v5 i odmowa destrukcyjnego downgrade sprawdzone w PostgreSQL.
- Kod i trwałość: neutralny rdzeń, krótka transakcja publikacji i kontrolowany
  proces inferencji; nowe procesy potwierdzają odzyskanie i wybór źródeł
  worktree przez eksportera OpenAPI oraz Mypy.
- Kontrakt i narzędzia: kompletny pion backend/OpenAPI/generowany klient/
  wrapper/test żądania, stabilne kody błędów; kontrole w tabeli powyżej.
- UX: error, loading/empty, blokada podwójnego submitu, tekstowe oznaczenia,
  rozmiary dotykowe oraz istniejąca korekta mają dowody. Mobilny smoke
  dotyku zaliczono w dwóch viewportach Chromium; fizyczny Android pozostaje
  granicą dowodu, podobnie jak przyszły odbiór na danych operatora.
- Dokumentacja i raport: wymagania, architektura, D-493, kontrakt, raport,
  Outcome i CURRENT_STATE uzupełnione; task przeniesiony do completed,
  osobny commit v1.7.191. Wdrożenie, aktywacja i pełny odbiór operacyjny
  na danych operatora pozostają poza zrealizowanym zakresem.
