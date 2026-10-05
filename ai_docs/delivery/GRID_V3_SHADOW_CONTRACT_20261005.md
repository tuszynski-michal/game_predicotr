---
title: V3-D — kontrakt wykonawczy shadow
status: accepted
last_updated: 2026-10-05
---

# V3-D — kontrakt wykonawczy shadow

Operator jawnie uruchomił etap 2026-10-05. Ten dokument doprecyzowuje jeden
zarezerwowany TASK-0805 i nie zmienia domyślnego silnika ani zgód na dane.

## Stan, zakres i wejście

Profile 777 i Mumii są zamrożone w registry TASK-0830. Inferencja w labie
jest odseparowana od produkcyjnego workera. Nowy pion używa neutralnego
rdzenia, bez importowania anotacji, treningu i labowych runów.

Pierwszy zakres to istniejące `source_images` z jednoznacznymi zakresami
sekwencji i rewizją źródłowej geometrii. Staging nie jest takim źródłem.
Nie tworzymy game/source/board/sequence ani zatwierdzeń za operatora.

API i worker mają jawny przełącznik shadow, domyślnie false. Brak wybranego
profilu, 3 × 3, niejednoznaczny zakres, brak modelu/SHA i niezgodna gra
odrzucają start przed utworzeniem joba. Brak słownika symboli nie blokuje.

## Uruchomienie i trwałość

Nowy zasób jest addytywny do istniejącego API Admina:

- POST `/admin/games/{gameId}/grid-shadow-jobs`: requestId UUID i lista
  1–20 unikalnych sourceImageIds. Serwer wybiera model z profilu gry,
  zamraża SHA, rewizje, sloty, rozmiary i ścieżki oraz tworzy istniejący job
  VALIDATE (`validation_kind=grid_geometry_shadow_v3`, schema_version=1).
- Ten sam requestId i kanoniczny payload odzyskuje job. Zmieniony payload
  ma 409; kolejność źródeł jest deterministyczna po sekwencji i ID.
- GET `/admin/games/{gameId}/grid-shadow-results`: ograniczona paginacja.
- GET `/admin/games/{gameId}/grid-shadow-results/{resultId}`: wynik wraz
  z bieżącymi reviewItems wyłącznie przy zgodnych bindingach.
- Status, anulowanie i retry joba korzystają z dotychczasowego API jobs.

Wejście joba zamraża profil i wersję modelu, checksum manifestu i bundle oraz
źródła: ID, ścieżkę względną w zarządzanym magazynie, SHA, wymiary, ID i numer
rewizji geometrii źródła, checksum geometrii, zakres sekwencji oraz aktywne
sloty z geometrią referencyjną. Checksum manifestu oznacza SHA kanonicznego
JSON z registry, a checksum bundle oznacza SHA rzeczywistych bajtów pliku
registry. Lista plików zamraża SHA wszystkich czterech plików modelu.
Ścieżki i model nie pochodzą od klienta. Wszystkie wartości obejmuje digest.

Worker korzysta z istniejącego lease/heartbeat/checkpoint/cancel. Nie trzyma
transakcji podczas inferencji. Sprawdza modele i obraz przed wykonaniem;
publikacja wyniku jest fenced przez job lease i ponownie sprawdza source
binding. Unikalność `(game_id,job_id,source_image_id)` odzyskuje wynik także
po utracie odpowiedzi przed checkpointem. Nowszy worker nie publikuje
starym lease. Drift jest jawny, nie tworzy nowego targetu za operatora.

Publikacja bierze blokady w kolejności Game FOR KEY SHARE, sekwencja,
źródło, job. Jawna pierwsza blokada porządkuje blokadę wynikającą z FK do
gry: koliduje z resetem Game FOR UPDATE, lecz pozostaje zgodna z blokadami
FK zwykłej korekty. Nie używać Game FOR UPDATE przy publikacji, ponieważ
korekta może już trzymać blokadę sekwencji przed odwołaniem do gry.

Wynik przechowuje metadata/JSON/checksum, nie piksele. Techniczne zakończenie
joba nie oznacza akceptacji siatek. Błędy integralności przerywają job;
zwykły brak planszy pozostaje wynikiem wymagającym korekty.

## Geometria i numeracja

Inferencja CPU ONNX używa wyłącznie sprawdzonego modelu z registry.
Zamrożone progi runu 1 mogą opisywać zgodność dla profilu 777. Mumie mają
jawny powód `NEURAL_GRID_GATE_UNCALIBRATED`; nigdy nie dziedziczą pewności
runu 1.
Wszystkie końcowe shadow proposals są `needs_review`.

Sloty pochodzą z poświadczonego zakresu źródła, nie liczby wykryć. Dopasowanie
do referencji/quadów zachowuje slot i sequence_number także przy brakach.
Brak kotwicy oznacza nieprzypisane wykrycie. Dodatkowe wykrycia służą
diagnostyce i nie tworzą aktywnych slotów. Zakres 499996–500000 ma pięć
slotów; niepoprawny zakres 499996–500004 przy końcu gry 500000 daje błąd
metadanych, bez cichego ograniczania zakresu.

Wynik każdego slotu zawiera pozycję i numer sekwencji, zamrożone nazwy i wersje
silnika referencyjnego, referencyjne i neuralne 24 węzły albo null, powody
porównania, stan oraz widoczność 15 pól:
full/partial/outside. Brak obu geometrii oznacza unknown; sam brak detekcji
nie dowodzi, że pole leży poza zdjęciem. Całe zdjęcie zachowuje komplet
aktywnych slotów i listę nieprzypisanych wykryć.

## Magazyn i migracja

Nowa tabela `game_data_v2.image_geometry_shadow_results` jest LIST(game_id),
ma PK(game_id,id), source/sourceRevision composite FK i public.jobs FK.
Manifest v5 dodaje dokładnie tę tabelę; v4 pozostaje niezmienny. Trzy
runtime konsumery, schema guard, lifecycle i catalog używają v5.
RLS ENABLE+FORCE i policy obowiązują także na child partitions. Istniejąca
historia porównań blokuje usuwanie jej źródeł w podglądzie cleanupu oraz
automatycznej retencji stagingu; nie dodajemy cichego usuwania historii.

Przygotowana migracja 0142 ma parent 0140 w tym worktree. Niecommitowana
0141 innego toru nie jest kopiowana. Przed scaleniem obowiązuje osobny
wspólny head Alembic i zgodna schema guard. Bez migracji/downgrade na danych
operatora w tym tasku; downgrade z istniejącymi wynikami odmawia usunięcia.

## Porównanie i korekta

Admin pokazuje obraz, baseline i pełne węzły sieci, wersję, powody, stan
wykonania i jawne stale. Aktualny slot otwiera istniejący edytor Reviewera.
Węzły sieci są propozycją. Jeśli edytor używa czterech narożników, UI jawnie
opisuje rekonstrukcję jako szkic do korekty, nie zachowaną pełną siatkę sieci.
Użytkownik może poprawić siatkę oraz przypisać symbole na widocznych polach.

Zapis korzysta wyłącznie z istniejących source/revision-bound komend korekty.
GET/start/worker shadow nie zmienia geometrii produkcyjnej, cropów, decyzji
symboli ani canonical. Zmiana geometrii unieważnia dostępność starego
kandydata do zapisu. Bramka kompletności całego zdjęcia nadal obowiązuje.

## Odbiór i granice

TASK-0805 ma testy: flag off/3×3, źródło i model drift, pięć aktywnych slotów
z extra, brak środka bez renumeracji, częściowe/outside, restart/replay/lease,
izolacja gier i child RLS, wygenerowany kontrakt, dwa kontury i zwykła korekta.
Porównać kryteria taska oraz V3-D punkt po punkcie; audyt bez P0–P2.

Nie wykonujemy treningu, aktywacji, masowego przetwarzania ani wdrożenia.
Operacyjny odbiór danych/migracji i brama skali wymagają oddzielnej zgody.

## Warunki uruchomienia przez operatora

Samo przygotowanie kodu nie uruchamia porównań. Testy PostgreSQL w osobnych
bazach testowych zostały zatwierdzone i zaliczone 2026-10-05 (4 PASS),
z potwierdzonym usunięciem zasobów testowych. Przed wdrożeniem należy
rozwiązać rozbieżne
migracje głównego checkoutu i worktree oraz przygotować zgodny pojedynczy
head Alembic. Dopiero po osobnej zgodzie wolno zatrzymać usługi, scalić kod,
wykonać migrację i uruchomić API, worker, Admin oraz Reviewer.

Przełącznik `GAME_PREDICTOR_GRID_SHADOW_ENABLED` pozostaje domyślnie false.
Włączenie musi być zapisane w trwałej konfiguracji API i workera, a nie tylko
w bieżącym terminalu. Po restarcie sprawdzić gotowość i zgodność migracji.
Panel jest dostępny w Adminie przy wejściu do Reviewera. Otwieranie panelu
wykonuje odczyty; rozpoczęcie porównania jest osobnym przyciskiem.

Pierwszy przebieg obejmuje najwyżej 20 już zmaterializowanych źródeł.
Wyniki zawsze wymagają ręcznego przeglądu. Zmiana geometrii odbywa się
wyłącznie po jawnym zapisie w istniejącym edytorze korekty. Wyłączenie
przełącznika blokuje nowe porównania i nie usuwa historii. Nie wykonywać
downgrade w celu usunięcia historii; migracja odmawia usunięcia niepustej
tabeli.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0805 | gpt-6.1-sol | high | Jeden pion shadow z podziałem pracy na rdzeń/worker, backend/magazyn i API/UI; modele dostępne w bieżącej sesji. Ryzyko rewizji i trwałości wymaga testów błędów i wznowienia. | gpt-6-astra, high; niezależny audyt przed ukończeniem |
