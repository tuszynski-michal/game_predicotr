---
title: Równoległe przygotowanie cropów w przeglądarce
status: done
last_updated: 2026-09-15
---

# TASK-0547 — równoległe przygotowanie cropów w przeglądarce

## Status

`done`

## Goal

Skrócić przygotowanie katalogu `cut` przez równoległą analizę maksymalnie
czterech zdjęć, współdzielenie przygotowanej kotwicy i usunięcie zbędnych
zapisów, zachowując kolejność, recovery oraz dokładne bramki obrazu v12.

## Context

Pomiar aktywnej sesji 2482 zdjęć pokazał medianę 10 s i średnią 9,53 s na
zdjęcie. Proces Chrome wykonujący pracę miał priorytet `Idle`, a cały browser
zużywał około 0,29 rdzenia z 16. Obecna implementacja analizuje zdjęcia
sekwencyjnie, dla każdego ponownie dekoduje pełną kotwicę 1920×1080 oraz
wykonuje serię synchronicznych zapisów. W 1626 wynikach 78% uruchomiło
rejestrację v12, 13,5% drugi poziom 1600 px, a 21,9% zakończyło się szybką
regułą `complete_layout_board_buffer`, która nie potrzebuje kotwicy.

Użytkownik zaakceptował przygotowanie zmiany równolegle do działających cropów
w osobnym worktree oraz polecił wdrożyć wszystkie zaproponowane optymalizacje.

## Dependencies / entry conditions

- Aktywny v12, shardy v2, journal i blokada jednego writera na katalog są
  wdrożone przez TASK-0536, TASK-0538, TASK-0544 i TASK-0545.
- Działające obecnie przeglądarki korzystają z głównego worktree. Ten task jest
  wykonywany w osobnym worktree i nie może przeładować bieżącej aplikacji.
- Nie zmieniamy progów detektora, reguł review ani fingerprintu v12.

## Recommended execution

`gpt-6-astra` z reasoning `high`. Zmiana łączy wielowątkowe wykonanie w
browserze z uporządkowanym journalem i wymaga analizy wyścigów oraz recovery.
Eskalacja do osobnego review jest potrzebna, jeżeli implementacja zmieni
fingerprint, próg jakości albo dopuści równoległe commity do jednego katalogu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Scope

- Wprowadzić pulę maksymalnie czterech browserowych workerów z ograniczoną
  kolejką, recyklingiem i dotychczasowym recovery niezgodnego workera.
- Analizować stałe paczki maksymalnie czterech pozycji równolegle, ale zapisywać
  wyniki i zwiększać `currentIndex` wyłącznie w kolejności inwentarza.
- Przygotować kotwicę v12 raz na paczkę jako mały, klonowalny zestaw cech i
  używać go w workerach dopiero po nieskutecznej szybkiej ścieżce strukturalnej.
- Hash źródła uruchamiać równolegle z analizą i przekazywać zweryfikowany plik
  do zapisu bez ponownego pobierania uchwytu.
- Nie zapisywać niezmienionego review; zachować dwa journalowe zapisy sesji,
  checksumę wyjścia oraz odczyt weryfikacyjny JPEG-a.
- Dodać nietrwałą telemetrię czasu analizy i zapisu oraz pokazać bieżącą
  równoległość i tempo w istniejącym wierszu postępu.
- Dodać testy kolejności, ograniczenia współbieżności, recovery workera,
  leniwej kotwicy, braku zbędnego zapisu review i kontraktu UI.
- Uzupełnić wymagania, architekturę i `CURRENT_STATE.md`.

## Out of scope

- Zmiana detektora v12, progów, fingerprintu i klasyfikacji jakości.
- Przeniesienie File System Access API do backendu lub nowa usługa/kolejka.
- Zmiana danych w `D:\777`, restart działającego serwera oraz przełączenie
  otwartych kart na nowy build podczas bieżącego cięcia.
- Pełny benchmark tysięcy zdjęć na danych użytkownika.

## Acceptance criteria

- [x] Na sprzęcie zgłaszającym co najmniej 12 logicznych procesorów analiza
      używa maksymalnie czterech workerów; słabszy sprzęt ma limit 1–3.
- [x] Kolejność commitów, progresu, failures i kotwic pozostaje zgodna z
      kolejnością inwentarza niezależnie od kolejności zakończenia analiz.
- [x] Jedna paczka przygotowuje najwyżej jedną kotwicę, a szybka reguła
      `complete_layout_board_buffer` nie dekoduje obrazu kotwicy w zadaniu
      zdjęcia.
- [x] Restart po dowolnym zatwierdzonym pliku wznawia brakujące pozycje bez
      usuwania ani ponownego zapisu gotowych JPEG-ów.
- [x] Normalny wynik bez zmiany listy korekt nie zapisuje pliku review.
- [x] UI pokazuje liczbę równoległych analiz oraz ostatni czas analizy i zapisu.
- [x] Skoncentrowane testy, lint i typecheck Admina oraz build przechodzą.

## Technical notes

Źródłem prawdy pozostaje inwentarz v2 i jego `sequence_number` wynikający z
naturalnej kolejności nazw. `Promise.all` ani zakończenie workera nie publikuje
wyniku. Koordynator zbiera rezultat paczki, a następnie wywołuje istniejący
journal dla każdej pozycji w kolejności. Błąd jednego przygotowania jest
utrwalany na jego pozycji i nie blokuje kolejnych.

Paczka ma stałą granicę czterech pozycji. Wszystkie pozycje używają snapshotu
kotwicy z początku paczki; po uporządkowanym commicie ostatni poprawny pełny
wynik staje się kotwicą kolejnej paczki. Pochodzenie kotwicy nadal trafia do
dowodu rejestracji. Liczba faktycznie aktywnych workerów zależy wyłącznie od
`hardwareConcurrency` i nie zmienia składu paczki ani kolejności wyników.

Worker najpierw wykonuje detekcję strukturalną. Dla braku kotwicy i dla
`complete_layout_board_buffer` zwraca wynik v12 bez ładowania cech kotwicy.
Pozostałe wyniki korzystają z przygotowanych cech 640 px, które zachowują
oryginalny deskryptor, wymiary i współrzędne dowodu.

Zapis nadal kolejno: utrwala pending w sesji, zapisuje JPEG, ponownie liczy jego
SHA-256, zapisuje shard i finalizuje sesję. Usuwamy wyłącznie zapis
niezmienionego review oraz ponowne `getFile()`/SHA źródła, gdy koordynator
przekazał już plik i checksumę z tej samej metadanej inwentarza.

## Expected files

- Istniejący: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-worker-client.ts` — pula workerów i telemetria.
- Istniejący: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-worker.ts` — dwa typy żądań i leniwa rejestracja.
- Istniejący: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-worker-contract.ts` — wersjonowany kontrakt.
- Istniejący: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-storage.ts` — równoległa analiza i uporządkowany zapis.
- Istniejący: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-workspace.tsx` — tempo i czasy etapów.
- Istniejący: `packages/manual-image-selection-core/src/auto-crop-v12-registration.ts` i `crop-preparation.ts` — przygotowana kotwica i dokończenie v12 z istniejącego wyniku strukturalnego.
- Proponowany: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-parallelism.ts` — czysty ograniczony koordynator.
- Proponowany: `apps/admin/test/selected-image-crop-parallelism.test.mjs` — kolejność i limit.
- Istniejące testy kontraktowe workera, storage i workspace.

## Test cases

- Cztery zadania kończą się w odwrotnej kolejności → wynik paczki i commity są
  nadal w kolejności wejścia, a maksimum aktywnych analiz wynosi cztery.
- Dwa procesory logiczne → jedna aktywna analiza; 8 → trzy; 12+ → cztery.
- Cztery zdjęcia ze wspólną kotwicą → jedno przygotowanie kotwicy i cztery
  żądania cropa; szybka ścieżka nie używa przygotowanych cech.
- Stary protokół/fingerprint → jeden świeży worker, potem bezpieczny fallback.
- Błąd drugiego zdjęcia → pierwsze, trzecie i czwarte są zatwierdzone kolejno,
  a drugie ma trwały failure.
- Zwykły wykryty crop bez korekty → brak zapisu niezmienionego review.
- Przerwanie podczas batcha → przeanalizowane, ale niezatwierdzone wyniki nie są
  uznane za gotowe; wznowienie zaczyna od trwałego stanu.

## Verification

```powershell
node --experimental-strip-types --test --test-isolation=none apps/admin/test/selected-image-crop-parallelism.test.mjs apps/admin/test/selected-image-crop-worker-client.test.mjs apps/admin/test/selected-image-crop-storage-contract.test.mjs apps/admin/test/selected-image-crop-workspace-contract.test.mjs
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run build --workspace @game-predictor/admin
```

Kryterium zaliczenia: wszystkie komendy kończą się kodem 0, a testy obejmują
odwrotną kolejność zakończeń, fallback i trwały uporządkowany commit.

## Risks / open questions

- Chrome może nadal obniżać priorytet procesu tła. Pula zwiększa wykorzystanie
  rdzeni, ale nie usuwa polityki `Idle` narzuconej przez browser/Windows.
- Równoległe dekodowanie zwiększa chwilowe użycie pamięci; limit czterech jest
  twardy i nie może rosnąć automatycznie powyżej tej wartości.
- Nie ma pytań blokujących. Użytkownik zaakceptował zakres i realizację w
  osobnym worktree.

## Outcome

Zadanie ukończone 2026-09-15 w osobnym worktree, bez przeładowania kart i bez
zmiany danych trwających sesji cropów.

### Changed

- Dodano ograniczony scheduler oraz pulę 1–4 workerów z recyklingiem,
  anulowaniem i jednorazowym recovery nieaktualnego workera.
- Brakujące zdjęcia są analizowane paczkami po cztery, a ich wynik, failure,
  journal, progres i następna kotwica są publikowane w kolejności inwentarza.
- v12 przygotowuje małą kotwicę rejestracji raz na paczkę. Worker wykonuje
  szybką analizę strukturalną przed użyciem kotwicy i nie powtarza jej pełnego
  dekodowania dla każdego zdjęcia.
- SHA-256 źródła jest liczona równolegle z analizą i przekazywana razem z tym
  samym plikiem do zapisu. Identyczne review jest pomijane.
- UI pokazuje równoległość, tempo i czasy dekodowania, detekcji, renderu oraz
  uporządkowanego zapisu.

### Verification results

- Skoncentrowane testy cropów Admina: 35/35.
- Pełny zestaw testów Admina: 484/484.
- Pełny zestaw testów `manual-image-selection-core`: 98/98.
- Typecheck Admina i core, lint Admina oraz kontrola Prettier: kod 0.
- Produkcyjny build Admina: kod 0; kompilacja, typecheck i generowanie stron
  zakończone poprawnie.

### Not completed

- Nie wykonano pełnego benchmarku tysięcy zdjęć na danych użytkownika zgodnie z
  zakresem taska. Bieżące karty nie zostały przełączone na nowy build, aby nie
  przerwać już uruchomionych cropów.

### Documentation updates

- Uzupełniono wymagania, architekturę, `CURRENT_STATE.md` i decision D-385.

### Recommended next task

- Po zakończeniu obecnych sesji przełączyć aplikację na commit TASK-0547 i na
  jednym rzeczywistym katalogu porównać telemetrię czasu zdjęcia oraz zużycie
  CPU z bazą 9,53 s/zdjęcie. Taki odbiór wymaga osobnego polecenia, ponieważ
  zmieni działające karty operatora.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0547 — równoległe przygotowanie cropów w przeglądarce | gpt-6-astra | high | Równoległa analiza musi zachować deterministyczną kolejność i journal odporny na restart. | Nie; o ile fingerprint, progi jakości i kolejność commitów pozostają bez zmian. |
