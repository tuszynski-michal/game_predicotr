---
title: TASK-0668 — T03 — edytor i zbiór geometrii
status: blocked
last_updated: 2026-09-26
---

# TASK-0668 — T03 — edytor i zbiór geometrii

## Status

`blocked` — narzędzia odebrane; wymagane rzeczywiste anotacje i pochodzenie danych.

## Goal

Zatwierdzać warstwowe anotacje geometrii z trwałymi rewizjami i zamrożonymi podziałami.

## Context

Część zaakceptowanego `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md`; wykonanie wyłącznie po jawnym uruchomieniu odpowiedniego etapu.

## Dependencies / entry conditions

STOP A; wybór gry niewidzianej zapisany przed pierwszym treningiem; zatwierdzony budżet B. Przed kodowaniem ponownie sprawdź bieżący kod, dostępność modelu/reasoning oraz zakres zasobów; istotną rozbieżność zapisz w planie i tasku.

## Recommended execution

`gpt-6-sol`, reasoning `medium`; osobny audyt `gpt-6-astra`, reasoning `medium`. Trwałość decyzji oraz brak przecieku rodzin źródeł wymagają kontroli rewizji i podziałów. Brak dokładnej konfiguracji blokuje task; P0–P2 po dwóch cyklach poprawek wymaga zatrzymania i ponownej analizy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/VISION_LAB_EXECUTION_PLAN.md` (T03 — edytor i zbiór geometrii)
- `ai_docs/requirements/VISION_LAB.md`, `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/process/DECISION_LOG.md` (D-447)

## Scope

Edycja narożników i pełnych węzłów, rewizje, backup/restore, pochodzenie 777 V2, split rodzin i duplikatów; pomiar pierwszych 10 zdjęć na grę i prognoza pracy.

## Out of scope

Aktywacja domyślna modelu, push, merge, wdrożenie, niezwiązane refaktory i niezatwierdzone wydatki lub operacje na danych użytkownika.

## Acceptance criteria

- [ ] Brak przecieku rodzin; restart i odtworzenie backupu; narożniki nie udają pełnej siatki; nierozstrzygnięte 777 V2 wykluczone.
- [ ] Audyt przypisanym modelem nie pozostawia P0–P2; zmiana ma osobny commit, Outcome i CURRENT_STATE.

## Technical notes

Etap B uruchomiony jawnie przez użytkownika 2026-09-26. Na wejściu jest
snapshot plikowy T02 (1180 wystąpień, 1160 SHA), bez ręcznych anotacji.
Prefiksy rodzin są kandydatami, nie potwierdzonym pochodzeniem. Budowa
edytora i mechanizmów splitu jest możliwa; zamrożenie rzeczywistych danych
oraz trening wymagają potwierdzonego pochodzenia i decyzji człowieka.
Nie wolno zastąpić tych decyzji automatycznym zatwierdzaniem baseline.
Kandydat niewidzianej gry `gang zd` pozostaje warunkowy do kontroli rodzin
i pokrycia topologii. Pomiar czasu anotacji musi być rzeczywisty, nie
oszacowany z czasu działania agenta.

Doprecyzowanie użytkownika: foldery mają różne konwencje numeracji,
prefiksy nie mają wspólnego standardu, a różne nazwy mogą przedstawiać ten
sam układ plansz. SHA-256 wykrywa tylko identyczne bajty, nie wszystkie
takie powtórzenia. Relacje powiązanych źródeł/pochodnych muszą być jawnie
grupowane wraz z duplikatami SHA; brak dopasowania nie potwierdza
niezależności. Nie wolno automatycznie zamrozić splitu według nazw.

Zachowaj kontrakty z planu i właścicieli istniejących decyzji. Błędy wejścia oznaczaj per źródło lub próbka, a błąd integralności i infrastruktury zatrzymuje zależny run. Nie promuj predykcji do ręcznego zatwierdzenia. Istotne odstępstwo wymaga aktualizacji planu przed implementacją.

## Expected files

- Istniejące `services/api/src/game_predictor_api/domain/board_topology.py::BoardTopology`, `apps/vision-lab/src/app/page.tsx::Page`. Nowe (proponowane) `services/worker/src/game_predictor_worker/vision_lab/annotations.py::approve_geometry`, `.../splits.py::freeze_splits`, `apps/vision-lab/src/components/geometry-editor.tsx::GeometryEditor`, `services/worker/tests/test_vision_lab_annotations.py`.

## Test cases

- Rewizja cropa unieważnia approval; dwa zdjęcia jednej rodziny zawsze w jednym splicie; backup po restarcie zachowuje decyzje; interpolacja nie jest referencją.

## Verification

Z katalogu repozytorium (proponowany nowy test powstaje w tym tasku):

```powershell
$p = Start-Process -FilePath '.\.venv\Scripts\python.exe' -ArgumentList @('-m','pytest','services/worker/tests/test_vision_lab_annotations.py') -PassThru -NoNewWindow
if (-not $p.WaitForExit(120000)) { $p.Kill(); throw 'pytest timeout 120s' }
if ($p.ExitCode -ne 0) { throw "pytest exit $($p.ExitCode)" }
```

Po teście wykonaj lint/typecheck zmienionych modułów i wymagane kontrole kontraktu, każdą jako skończony proces z limitem maksymalnie 120 s. Testy tu są planowane, niezaliczone; zaliczenie wymaga kryteriów powyżej i braku regresji.

## Risks / open questions

- Zmiana schematu danych, zakresu zdjęć lub kosztu poza planem wymaga jawnej aktualizacji przed zależnym działaniem.

## Outcome

Część narzędziowa odebrana 2026-09-26. Cały T03 i etap B nie są ukończone.

### Changed

- Edytor narożników i 24/16 węzłów, osobne zatwierdzenia lokalizacji oraz
  pełnej siatki, pomiar aktywności i korekt. Wyniki AI pozostają propozycją.
- Atomowy magazyn rewizji z kontrolą konfliktu, idempotentnym retry,
  historią wynikowych decyzji i backup/restore do nowego katalogu.
- Grupowanie rodzin, pochodnych i duplikatów SHA; niezweryfikowane grupy
  wykluczone. Edycja oznacza podział jako `split_stale`, zachowuje jego
  przydziały i nie pozwala ponownie losować holdoutów.
- API, OpenAPI, wygenerowany klient, wrapper i testy żądań są spójne.

### Verification results

- Backend: 9 testów anotacji i 19 istniejącego laboratorium; UI 5/5,
  klient 3/3. Ruff/format, ESLint, TypeScript, mypy 11 modułów i kontrole
  OpenAPI/generowanego klienta zaliczone.
- Production build oraz restart obu usług zaliczone. Odbiór przeglądarkowy:
  24/16 węzłów, przesunięcie uchwytu, brak automatycznego approval,
  zachowanie wyboru rodziny między stronami. Nie zapisano decyzji na danych
  użytkownika; po restarcie rewizja 0, brak anotacji, rodzin i podziału.
- Niezależny audyt Astra medium: PASS kodu, bez otwartych P0–P2.
  Audytor niezależnie uruchomił wcześniejsze 7 testów anotacji; końcowe
  rozszerzone zestawy pochodzą od wykonawcy Sol medium.

### Not completed

- Brak rzeczywistych zatwierdzeń człowieka, potwierdzonego pochodzenia
  rodzin, pomiaru pierwszych 10 zdjęć/grę i prognozy pracy oraz zamrożonego
  splitu. Kryterium braku przecieku jest przetestowane mechanicznie, ale
  nieudowodnione dla rzeczywistych danych.
- 777 V2 pozostaje fail-closed: nie dostarczono dowodu pochodzenia i
  podobieństwa dopuszczającego dane. Historyczne 777 tylko porównawcze.
- Nie uruchomiono T04/T05, instalacji treningowych, treningu, aktywacji,
  pełnej kontroli repozytorium ani testu fizycznego Androida. Brak push/merge.

### Documentation updates

- CURRENT_STATE, instrukcja VISION_LAB_LOCAL i raport
  VISION_LAB_STAGE_B_ACCEPTANCE. Zadanie pozostaje aktywne, nie w completed.

### Recommended next task

- Rzeczywisty pilot anotacji w gotowym edytorze i rozstrzygnięcie powiązań
  zdjęć. Dopiero po spełnieniu bramek T03 można uruchomić zależny T04.
  Odblokowanie samego kodowania T04 wcześniej wymaga zmiany zaakceptowanego
  planu; nie przyjęto jej samodzielnie.
