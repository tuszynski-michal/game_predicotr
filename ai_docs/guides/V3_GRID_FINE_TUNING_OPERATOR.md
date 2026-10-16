---
title: Doszkalanie geometrii V3 — instrukcja operatora
status: active
last_updated: 2026-10-16
---

# Doszkalanie geometrii V3 — instrukcja operatora

Instrukcja opisuje cały przebieg doszkalania siatek V3 z poprawek w aplikacji:
od kontroli jakości do aktywacji nowej wersji i ponownego rozpoznania. Dotyczy
gier V3 (np. Mumie, 777a2). Historyczna gra 777 (kod `7`) pozostaje archiwalna
i nie bierze udziału w tym procesie. Modele symboli są osobne dla każdej gry i
nie są doszkalane tym przebiegiem.

Źródła prawdy: plan
[V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014](../delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md),
decyzje D-548–D-560 w
[DECISION_LOG_2026](../process/decisions/DECISION_LOG_2026.md) oraz wymagania
„Pełna sekcja Geometria V3” w [ADMIN_APP](../requirements/ADMIN_APP.md).
Wynik odbioru: [V3_GRID_FINE_TUNING_ACCEPTANCE](../quality/V3_GRID_FINE_TUNING_ACCEPTANCE.md).

## 1. Warunki wstępne

- Baza na head migracji `0166_grid_model_evaluation`. Migrację wykonuje
  operator w kolejności: stop usług → scalenie → `npm run db:migrate` → start.
  Rola capability z D-554 musi istnieć przed `0161`.
- Usługi z `D:\game_predicotr`: API (`npm run api:dev`), Admin
  (`npm run admin:dev`), Reviewer (`npm run reviewer:dev`).
- Workery (sterowane skryptem `scripts/manage_worker_lanes.ps1`):
  - `npm run workers:start` — tylko lane `general` (kohorty, ocena kandydata,
    ponowne rozpoznanie, importy);
  - `npm run workers:start:all` — `general`, `image-selection` oraz
    `grid-training`, ale ten ostatni tylko wtedy, gdy skrypt znajdzie
    interpreter CUDA (niżej);
  - `npm run workers:start:grid-training` — tylko lane `grid-training` (trening na
    GPU); bez interpretera odmawia startu;
  - `npm run workers:status` i `npm run workers:stop` obejmują zawsze wszystkie
    lane i wszystkie procesy zapisane przez skrypt, niezależnie od interpretera.
  - Trener GPU potrzebuje interpretera z CUDA, torch i onnxruntime. Skrypt bierze
    go kolejno z parametru `-GridTrainingPython <ścieżka>`, ze zmiennej
    `GAME_PREDICTOR_GRID_TRAINING_PYTHON` (procesu albo użytkownika Windows) albo z
    `.venv-vision-lab\Scripts\python.exe` checkoutu. Bez interpretera
    `-Lane grid-training` odmawia startu, a `-Lane all` pomija ten lane. Worker
    uruchomiony ręcznie (`npm run worker:grid-training:poll`) bez zmiennej startuje,
    ale każdy run kończy się kodem `GRID_TRAINING_PYTHON_UNSET`.
  - Stan 2026-10-16: środowisko `.venv-vision-lab` istnieje tylko w starym
    checkoucie `C:\Users\tuszy\Documents\game_predicotr`; checkout
    `D:\game_predicotr` go nie ma. Do czasu kopii na D wskaż ścieżkę z C
    parametrem lub zmienną użytkownika i nie usuwaj tego katalogu przy
    sprzątaniu C (TASK-0957).
- Lane `grid-training` ma jeden slot GPU. Drugi run czeka w kolejce; zajęte
  GPU nie jest błędem runu. Orientacyjnie: kohorta 30 plansz TRAIN, preset
  `grid-only-v1`, 1200 kroków to około 5 minut treningu na lokalnym GPU (pomiar
  odbioru TASK-1001 na danych syntetycznych).

## 2. Przebieg w Adminie

Admin → Jakość modelu → wybór gry V3 → sekcja **Geometria V3**. Wejście na ekran,
zmiana gry i odświeżenie strony tylko odczytują dane. Każda zmiana jest
osobnym przyciskiem. Identyfikatorów nie trzeba wpisywać; sekcje
„Zaawansowane” są potrzebne tylko w nietypowych przypadkach.

1. **Przypisana wersja** — aktualna wersja geometrii gry, rodzina i powód
   kwalifikacji.
2. **Nagrania i role** — grupy nagrań gry i ich role: `TRAIN`, `VALIDATION`,
   `REGRESSION`. Nagranie kontrolne nie może być jednocześnie treningowym; ta
   sama treść zdjęcia w dwóch rolach jest odrzucana jako alias.
3. **Kontrola jakości (próbka)** — losowa próbka siatek do oceny w Reviewerze.
   Poprawki człowieka w Reviewerze są jedynym źródłem etykiet treningowych.
4. **Dane do doszkalania (kohorty)** — rodzina i baza pochodzą z przypisania
   gry. Wybierz import po nazwie i dacie, zaznacz nagrania i ich role, potem
   „Podgląd”. Podgląd pokazuje kwalifikację i powody blokad. „Utwórz kohortę”
   zamraża niezmienny snapshot; późniejsze poprawki go nie zmieniają.
5. **Trening** — wybierz zamrożoną kohortę po etykiecie. Podgląd pokazuje
   blokady; start jest dostępny tylko bez blokad. Opcjonalnie dołącz kohorty
   innych gier V3 tej samej rodziny, aby wytrenować kandydata wspólnego.
   Run można anulować i wznowić według jego stanu. Wynik runu to kandydat ze
   stanem `not_evaluated`, nigdy aktywna wersja.
6. **Porównanie z bazą** — wybierz run i uruchom ocenę. Kohorty wspólnego
   treningu są oceniane zawsze; inne gry rodziny można dodać po nazwie. Raport
   ma werdykt dla każdej gry osobno (polityka `grid-model-per-game-gate-v1`):
   - brak pogorszenia na `photo_complete_correct`, `boards_correct`,
     `boards_matched`, `false_boards`, `duplicate_predictions` i `image_macro`;
   - gra treningowa musi się poprawić.
   „Sprawdź aktualność” porównuje dowody kohort z bazą. Stan `stale`,
   `missing` albo `unavailable` blokuje publikację do czasu nowej oceny.
7. **Wersje** — publikacja kandydata wymaga oceny `PASS` z aktualnymi
   dowodami wszystkich kohort. Po publikacji: „Aktywuj dla gry”, „Ustaw jako
   domyślną” dla nowych gier oraz przywrócenie wcześniejszej wersji z historii
   gry. Każda z tych operacji jest osobną decyzją operatora.
8. **Ponowne rozpoznanie** — podgląd i uruchomienie dla wybranego zakresu
   siatek aktywną wersją (domyślnie zgłoszone „Złe siatki” i odroczone sloty;
   siatki niepotwierdzone i wszystkie automatyczne to osobne zakresy). Skutek
   zależy od stanu celu:
   - zgłoszona „Zła siatka” — trwała propozycja w Korekcie cięcia siatki
     Reviewera; zmienia się dopiero po decyzji człowieka, a aktualne wycinki i
     zgłoszenie zostają bez zmian;
   - geometria chroniona albo decyzja człowieka — brak nadpisania, raport
     przyczyny ochrony;
   - odroczony slot bez konfliktu — **zapis automatyczny** po bramce i ponownej
     kontroli aktualnego stanu;
   - niechroniona automatyczna plansza z wybranego zakresu — **zapis
     automatyczny** po bramce i sprawdzeniu rewizji oraz właściciela;
   - zmienione źródło, rewizja albo właściciel — konflikt, stary wynik nie jest
     zapisywany.
   Każde uruchomienie zaczyna się od pilota do 100 zdjęć; szerszy zakres wymaga
   oceny raportu pilota i osobnego potwierdzenia. Raport rozdziela propozycje,
   zapisy automatyczne, ochronę, brak zmiany, konflikty i brak źródła; ani
   propozycja, ani zapis automatyczny nie są dowodem poprawy jakości.

Ponowne rozpoznanie działa także bez treningu, aktualną bazą (krok 8 bez
kroków 4–7).

## 3. Utrata odpowiedzi, restart i ponowienie

- Polecenia runu, oceny i wersji zapisują klucz idempotencji i treść przed
  wysłaniem. Gdy odpowiedź zginie (zamknięta karta, restart API), panel po
  powrocie pokazuje oczekujące polecenie z przyciskiem ponowienia. Ponowienie
  z tym samym kluczem zwraca ten sam wynik zamiast tworzyć drugi run.
- Joby są trwałe w PostgreSQL. Po restarcie workera wygasła dzierżawa wraca do
  kolejki, a trening wznawia się od ostatniego zapisanego punktu.
- Usługi uruchamia i zatrzymuje operator. Po scaleniu zmian kodu Admin i
  Reviewer wymagają restartu albo przebudowy (`npm install`, build).

## 4. Typowe blokady

Panel pokazuje etykietę każdej blokady; nieznany kod ma postać
„Inny powód (KOD)”. Najczęstsze przypadki:

- kohorta bez danych `TRAIN` albo bez nagrań kontrolnych — dodaj poprawki w
  Reviewerze lub nagrania z właściwą rolą;
- źródło zmienione po zamrożeniu kohorty — utwórz nową kohortę;
- ocena nieaktualna — uruchom nową ocenę;
- `REVISE` albo `NOT_EVALUABLE` — kandydat nie jest publikowany; to
  dopuszczalny wynik eksperymentu, nie podstawa do osłabienia bramki.
- `GRID_TRAINING_ONNX_PARITY_FAILED` — eksport ONNX różni się od modelu torch
  ponad tolerancję względną 1e-4 (D-561). Pomiar różnic jest w
  `artifacts/grid-training/runs/<run>/parity-failed.json`; run można wznowić
  dopiero po wyjaśnieniu przyczyny.

## 5. Czego proces nie robi

- Nie wdraża i nie aktywuje modeli automatycznie.
- Nie uruchamia treningu na danych operatora bez polecenia operatora.
- Nie zmienia historycznej gry 777 ani modeli symboli.
- Nie przetwarza masowo zdjęć poza wybranym zakresem ponownego rozpoznania.
