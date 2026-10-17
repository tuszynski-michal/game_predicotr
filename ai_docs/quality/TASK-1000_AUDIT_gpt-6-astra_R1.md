# Audyt TASK-1000 — Pełna sekcja „Geometria V3”

Werdykt: REVISE
Audytor: Codex, gpt-6-astra / medium (etykieta briefu)
Wykonawca: claude-opus-5-5 / high
Zakres: HEAD...1b38ae6ce742272a5f63557670b7e8ed5bbc7c3a oraz niezacommitowane zmiany wskazane w briefie, data 2026-10-16
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdzono integrację paneli, wybór danych, polecenia treningu i wersji, bramkę publikacji oraz testy. Rozdzielenie publikacji i aktywacji oraz brak automatycznych mutacji przy wejściu są zachowane. Pełny przebieg blokują jednak ograniczenia wyboru źródeł i bazy oraz brak obsługi kolejnych stron katalogów.

## Znaleziska

### P0

- [P0-1] `apps/admin/src/features/model-quality/grid-cohort-preview.tsx:325` — Zwykły wybór źródeł obejmuje wyłącznie jeden import. Zaznaczenie nagrań TRAIN, VALIDATION i REGRESSION z różnych importów nie dodaje ich zdjęć do kohorty: backend ogranicza członkostwo do `selector.importJobId` (`services/api/src/game_predictor_api/application/grid_training_cohort_commands.py:65`). Dla typowego układu „jedno nagranie = jeden import” powstaje kohorta bez wymaganych danych kontrolnych. Jedyną alternatywą formularza jest ręczne wpisanie UUID zdjęć, sprzeczne z kryterium zwykłego przebiegu. Należy umożliwić wybór źródeł z wymaganych nagrań/importów po nazwach i przekazać dokładny zakres obsługiwany przez backend.

- [P0-2] `apps/admin/src/features/model-quality/grid-cohort-preview.tsx:306` — Rodzina i baza kohorty są bezwarunkowo pobierane z aktywnego przypisania gry; operator nie może wybrać innej zgodnej bazy z katalogu. Przy dwóch grach przypisanych do różnych baz nie da się przygotować zgodnych kohort wspólnego treningu bez wcześniejszego przełączenia przypisania. Backend wymaga identycznej rodziny, bazy i trybu wszystkich kohort (`services/api/src/game_predictor_api/domain/shared_grid_model_candidate.py:78`). Należy oddzielić nazwany wybór bazy treningowej od aktywacji produkcyjnej, zachowując walidację zgodności backendu. Sam zapis tego ograniczenia w nowej dokumentacji nie realizuje wymaganego wyboru zgodnej wersji.

- [P0-3] `apps/admin/src/features/model-quality/grid-training-run-panel.tsx:80` — Selektor treningu pobiera tylko pierwsze 100 kohort i ignoruje `nextCursor`. Ten sam problem dotyczy kohort dodatkowych gier (`grid-training-run-panel.tsx:145`, `grid-model-comparison.tsx:155`) oraz pierwszych 200 nagrań (`grid-cohort-preview.tsx:203`). Poprawna kohorta lub nagranie na kolejnej stronie pozostają niedostępne; reload tego nie naprawia. Task jawnie wymaga wykorzystania stronicowania istniejących katalogów. Należy dodać pobieranie kolejnych stron i zachować wybory pomiędzy stronami.

### P1

- [P1-1] `apps/admin/test-interactions/grid-model-workspace.test.mjs:208` — Test utraty odpowiedzi runu kończy się na obecności lokalnego pending w tej samej instancji komponentu. Nie odmontowuje panelu, nie odtwarza go z zachowanym storage i nie sprawdza ponowienia dokładnego polecenia. Nowe operacje wersji również nie mają testów odzyskania po reload ani konfliktu rewizji. Istniejące testy kohort dotyczą innego mechanizmu zapisu. Należy dodać wymagane testy trwałości runu i poleceń wersji: remount, brak automatycznego POST, identyczne body/klucz przy retry oraz zachowanie po 409.

### P2

- [P2-1] `apps/admin/src/features/model-quality/grid-model-workspace.tsx:61` — Panele montują niezależne kopie list bez powiadamiania o zmianach. Zamrożenie kohorty nie odświeża selektora treningu, ukończenie treningu nie odświeża listy porównania, a aktywacja nie odświeża podsumowania i bazy formularza kohort. Panel treningu odczytuje listy przy montowaniu i własnych mutacjach (`grid-training-run-panel.tsx:93`), porównanie przy montowaniu (`grid-model-comparison.tsx:87`). Obecnie przejście między krokami wymaga przeładowania strony. Zalecane wspólne odświeżanie zależnych odczytów albo jawne przyciski odświeżenia; do tego czasu ograniczenie powinno być opisane operatorowi.

- [P2-2] `apps/admin/src/features/model-quality/grid-model-versions-panel.tsx:130` — Wyczyszczenie wyboru nie unieważnia trwającego żądania, ponieważ zwiększenie licznika następuje dopiero po `if (!id) return`. Spóźniona odpowiedź może przywrócić wyczyszczoną ocenę i odblokować publikację. Analogicznie działa wybór oceny w linii 140 i kohorty treningowej w `grid-training-run-panel.tsx:124`. Należy unieważniać żądanie przy każdej zmianie wyboru, także na pusty, i sprawdzać zgodność odpowiedzi z aktualnym wyborem.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Proces działa bez skryptów operatora | niespełnione | `apps/admin/src/features/model-quality/grid-cohort-preview.tsx:325`; P0-1 |
| Zwykły przebieg używa nazw zamiast ręcznych UUID | niespełnione | `apps/admin/src/features/model-quality/grid-cohort-preview.tsx:306`; P0-1, P0-2 i P0-3 |
| Wejście na ekran nie uruchamia joba | spełnione | Statyczna analiza efektów; `apps/admin/test-interactions/grid-model-workspace.test.mjs:115` |
| Zmiana gry/reload zachowuje właściwy stan | niezweryfikowane | Klucze per API/gra istnieją; brak pełnych testów odzyskania nowych poleceń — P1-1 |
| Panel działa z dwiema bazami i odrzuconym wspólnym kandydatem | niespełnione | Test `apps/admin/test-interactions/grid-model-workspace.test.mjs:420` sprawdza prezentację i blokadę publikacji, ale przygotowanie wspólnego treningu ogranicza P0-2 |
| Kontrole, audyt i ograniczenia zapisano w Outcome; dokumentacja odpowiada zachowaniu | niezweryfikowane | `ai_docs/tasks/1000-v3-grid-model-workspace.md:145` — Outcome zawiera deklarowane wyniki i ograniczenia; audyt oczekuje uzupełnienia, wyników poleceń nie odtwarzano |

## Listy zamknięte i otwarte

Zamknięte: Brak — runda 1.

Otwarte: P0-1, P0-2, P0-3, P1-1, P2-1, P2-2.

## Proponowane testy

W `apps/admin/test-interactions/grid-model-workspace.test.mjs` i `apps/admin/test-interactions/grid-cohort-preview.test.mjs` należy dodać:

- Przygotowanie kohorty z trzech nazwanych importów reprezentujących oddzielne role, bez wpisywania UUID.
- Przygotowanie wspólnego treningu dwóch gier z różnymi aktywnymi bazami, bez mutacji przypisań.
- Wybór nagrania i kohorty z drugiej strony katalogu.
- Utrata odpowiedzi, remount, jawne retry z identycznym kluczem/body oraz konflikt rewizji dla nowych poleceń.
- Wyczyszczenie wyboru przed zakończeniem opóźnionego odczytu.
- Odświeżenie kolejnego kroku po zamrożeniu kohorty i zmianie przypisania.

Komenda po poprawkach: `npm run test:geometry --workspace @game-predictor/admin`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, task i Outcome, właściwe fragmenty planu, wymagania, decyzje D-527/D-541, zmienione komponenty i testy oraz kontrakty backendu potrzebne do sprawdzenia selekcji źródeł i wspólnego treningu.

Nie uruchamiano testów, usług, treningów, migracji ani operacji na danych. Deklarowane wyniki kontroli wykonawcy nie zostały niezależnie potwierdzone. Przegląd nie potwierdza działania na rzeczywistych bazach operatora ani jakości modeli.