# Korekta symboli z niezależnej partii Mumii

Status: accepted for implementation, 2026-10-05. Zakres wynika z prośby
o działającą korektę oraz wcześniejszej zgody na samodzielne naprawy.

## Stan, cel i granice

Galeria 18 przypadków TASK-0857 pokazuje wyłącznie propozycje. Kliknięcie
wycinka otwiera zdjęcie. Źródła nie należą do dotychczasowego katalogu lab,
więc zwykły edytor zaakceptowanych plansz nie może zapisać ich etykiet.
TASK-0858 dostarcza korektę dokładnego wycinka w istniejącym API i aplikacji.
Nie tworzy akceptacji całego zdjęcia, numeracji sekwencji ani pełnej geometrii.
Nie zmienia pierwotnych etykiet, podziałów, modeli i danych produkcyjnych.

## TASK-0858 — jeden pion korekty

1. Nowy proponowany `symbol_batch_labels.py` publikuje create-only pakiet
   referencji z istniejących `cases.json` i wyników V2. Sprawdza identyczność
   źródła, quad, surowe piksele RGB96, wykluczenia partii i zatwierdzony słownik
   kwalifikacji D-498. PNG jest bezstratny. Maksymalnie 100 przypadków.
2. Referencja przypina SHA źródeł, dokładnych PNG, słownika i polityki. Nowy,
   oddzielny magazyn pod `artifacts/` przechowuje checksumowane decyzje,
   receipts i historię. Zapis sprawdza binding, bieżący słownik/politykę,
   źródło i PNG pod bounded lock; receipt poprzedza CAS. Jedna atomowa
   publikacja na decyzję. Zmieniona klasa tworzy nową decyzję.
3. Istniejące POST `/symbol-crops` otrzymuje `kind=batch_queue`, a POST
   `/symbols` — `op=batch_label_decide`. Konfiguracja jest opcjonalna,
   ścieżki dostarcza operator/launcher, nigdy klient. Stare tryby bez zmian.
   Brak konfiguracji daje jawny 503. Drift/CAS/klasa daje 409 bez zapisu.
   OpenAPI generuje klient; wrapper i test żądania obejmują ten sam pion.
4. Proponowana strona `/symbols/batch` pokazuje 18 PNG. Kliknięcie wybiera
   wycinek. Paleta istniejących klas i jawny zapis nie wymagają zmiany siatki.
   Zapis zatwierdza wyłącznie widoczny wycinek. Nieczytelność/błąd siatki
   są decyzjami bez klasy. Miniatury zostają zamrożone, wynik potwierdza
   receipt. Utracona odpowiedź wymaga identycznego retry; konflikt — jawnego
   odczytu. Oddzielny link otwiera całe zdjęcie. Galeria linkuje ten edytor.
5. Trwały launcher zapisuje opcjonalne ścieżki referencji i nowych etykiet.
   Restart wyłącznie istniejącego lab API/UI 8102/3102. Odczyt realnych
   przypadków bez zapisania za operatora jakiejkolwiek klasy.

Nowe decyzje mają pochodzenie `batch_crop_review`, nie `lab_human_approved`.
Zawsze `trainable=false`; bramki `SYMBOL_BATCH_GEOMETRY_NOT_APPROVED` oraz
`SYMBOL_SPLIT_NOT_FROZEN` pozostają. Ich późniejsza kwalifikacja/trening
wymaga osobnego zadania. Ani model, ani agent nie ustala prawdziwej klasy.

## Weryfikacja i odbiór

Planowane: izolowane testy żądania, receipt/CAS/restart/drift, brak zapisu
do starego store, regresje API, test UI utraty odpowiedzi i zamrożonych PNG,
Ruff/mypy, klient generated drift/typecheck, UI test/lint/typecheck/build.
Kontrolowany restart i odczyt 18 przypadków przez proxy. Rzeczywisty zapis
pozostaje pierwszą konieczną interakcją człowieka. Bez DB, migracji, treningu,
aktywacji modelu, produkcyjnego wdrożenia ani merge/push.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0858 korekta dokładnych wycinków partii | gpt-6.1-sol | high | Jeden pion API/UI z trwałym zapisem i ochroną istniejących etykiet. | Własny audyt integralności, CAS i restartu; bez delegowania. |
