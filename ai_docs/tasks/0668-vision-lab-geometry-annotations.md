---
title: TASK-0668 — T03 — edytor i zbiór geometrii
status: blocked
last_updated: 2026-09-26
---

# TASK-0668 — T03 — edytor i zbiór geometrii

## Status

`blocked` — anotacje i przegląd operatora wykonane; trwa odczytowy preflight,
pozostają dowody pochodzenia oraz zamrożony podział. Nie uruchamiać T04/T05
przed spełnieniem bramek danych.

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

Wznowienie po przeglądzie: ostatni odczyt wykazał 63 zaakceptowane zdjęcia,
180 pełnych geometrii i brak zapisanych rodzin/splitu; liczności wymagają
ponownego odczytu. Użytkownik potwierdza geometrię, nie poprawność symboli.
Nowe bieżące sprawdzenie: SHA i rewizje akceptacji, węzły i granice źródła,
liczności per gra/topologia, exact duplicates i stan dowodów rodzin.
Wynik nie może udawać wizualnej walidacji ani potwierdzać niezależności
po samych nazwach. Planowana kontrola nie zapisuje decyzji, nie zamraża
splitu i nie zmienia roli 777. Raport:
`ai_docs/quality/VISION_LAB_STAGE_B_DATA_PREFLIGHT.md` (nowy).
Sprawdzone moduły: `catalog.py::Catalog`, `annotations.py::read_checked`,
`photo_review.py::photo_accepted`, `geometry.py::cell_quads`,
`splits.py::freeze_splits` w `services/worker/src/game_predictor_worker/vision_lab`.
Komendy diagnostyczne ograniczone do istniejącego zbioru, timeout do 120 s.
Odczyt nie zastępuje brakującej decyzji o pochodzeniu; nierozstrzygnięty
warunek jest raportowany jako blokada, bez osłabiania istniejących testów.

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

## T03a — ergonomia edytora i bieżące cropy

Status: `done` (podzadanie; nadrzędny T03 nadal blocked na danych). Polecenie użytkownika 2026-09-26; wyłącznie laboratorium
3102. Wykonawca `gpt-6-sol` / `medium`, niezależny audyt `gpt-6-astra` / `medium`.
Duży edytor po lewej i zwarte cropy po prawej, automatyczny podgląd bieżących
węzłów po puszczeniu uchwytu. Kadr zdjęcia dopasowuje się do granic siatki
z 8% marginesem dopiero po puszczeniu; podczas gestu pozostaje zamrożony.
Zdjęcie nie jest rektyfikowane, współrzędne źródła i rewizje są zachowane.
Powrót do pełnego zdjęcia jest jawny; małe etykiety mają stabilny rozmiar
ekranowy i większy obszar chwytania. Początkowa propozycja obejmuje 70% zdjęcia.

Istniejący POST `/geometry` otrzymuje opcjonalne `preview_board` (kontrakt
Board); brak pola zachowuje baseline. Preview używa `cell_quads` i `crop_cell`,
zwraca istniejący GeometryResult i tylko nietrwałe assety. Błędna geometria
nie pokazuje starych cropów; nieobecność i brak węzłów nie uruchamiają żądania.
Frontend unieważnia trwające odpowiedzi przy każdej zmianie geometrii,
źródła, planszy i topologii; najnowsze żądanie jest jedynym przyjmowanym.
Podgląd nie zapisuje szkicu, decyzji, rewizji ani podziału.

Pliki: geometry-editor.tsx, nowy lib/editor-viewport.ts i lib/latest-preview.ts,
style.css, vision_lab/contracts.py, catalog.py, api.py, OpenAPI i generowany
klient/wrapper oraz testy UI, API i klienta. Dokumenty wymagań/architektury
i plan są aktualizowane; CURRENT_STATE prowadzi koordynator.

Kryteria/testy: mapowanie pointera po zoomie, nieruchomy kadr podczas drag,
dopasowanie po release, powrót do pełnego zdjęcia, obie topologie, zgodność
bajtów cropów z crop_cell, błędna/brak geometrii, odwrócona kolejność
odpowiedzi i zmiana źródła. Testy skoncentrowane → lint/typecheck → kontrola
OpenAPI/generowania → build i odbiór przeglądarkowy; każdy proces limit 120 s.
Nie obejmuje rzeczywistych zatwierdzeń ani odblokowania T04/T05.

### Outcome T03a

- Commit `v1.7.3` — `5db0a10bfa464526a6eb08dd6611cdafc9c262bf`.
  Hash uzupełniony po commicie, lokalnie do kolejnego commita.
- Wdrożono edytor/kadr, małe uchwyty z 44 px obszarem chwytania, sidebar
  cropów i automatyczny preview po release. Viewport nie zmienia geometrii.
  Stare odpowiedzi są unieważniane również na początku kolejnego drag.
- POST `/geometry` przyjmuje `preview_board`; cropper i walidacja pozostają
  wspólne z baseline, a brak pola zachowuje dotychczasowe zachowanie.
  Wygenerowano OpenAPI i klienta. Podgląd nie tworzy katalogu anotacji.
- Testy: UI 9/9, klient 4/4, backend API/anotacje 30/30. Po wzmocnieniu
  testu teksturowanym obrazem ponownie API 21/21; porównanie dokładnych
  bajtów JPEG croppera i odmienności wobec baseline dla obu topologii.
- ESLint, TypeScript obu pakietów, Ruff, formatowanie, OpenAPI i kontrola
  generowanego klienta zaliczone. Skoncentrowany mypy
  `--follow-imports=silent services/worker/src/game_predictor_worker/vision_lab`
  zaliczony (11 modułów). Domyślny mypy zgłosił 14 wcześniejszych błędów
  zależności `images` (brak importów `game_predictor_api.domain` i pochodny
  `no-any-return`); nie zmieniano ich w T03a.
- Koordynator potwierdził production build i odczyt przez 3102: 15/9 cropów,
  asset 200, rewizja anotacji nadal 0. Końcowy build dokładnego kodu
  po wydzieleniu helpera gestu także zaliczony; nowe procesy API i UI działają.
- Niezależny audyt Astra medium: PASS, brak otwartych P0–P2. Audytor
  uruchomił API 21/21 i końcowe helpery UI 4/4. Wykryte przerywanie gestu
  na numerze uchwytu naprawiono i potwierdzono czterema długimi gestami.
- Przeglądarka: pojedyncza plansza przybliżona po lewej i 15 aktualnych
  symboli po prawej, 3 × 3 z 9 cropami, powrót do pełnego zdjęcia,
  szerokość 390 px bez poziomego przepełnienia. Dowód lokalny:
  `artifacts/vision-lab/t03a-editor.png` (szkic, bez zatwierdzenia).
  Fizyczny Android niesprawdzony; stałość kadru w środku gestu potwierdzono
  kodem/testem, ponieważ narzędzie przeglądarkowe wykonuje drag atomowo.
- Kryteria podzadania zestawiono z implementacją i testami: fit/release,
  poprawne współrzędne źródła, kompaktowy layout, oba rozmiary siatki,
  zgodny cropper, obsługa braku/błędu geometrii i odrzucanie starych odpowiedzi
  zaliczone. Cały task pozostaje w aktywnych ze względu na bramkę danych.
- Audyt przeglądarkowy wykrył przerwanie długiego gestu z numeru uchwytu
  przez domyślny drag tekstu/obrazu. Dodano preventDefault przed capture,
  blokadę natywnego drag SVG i zaznaczania tekstu. Test regresji sprawdza
  kolejność preventDefault/capture; UI 9/9, lint i typecheck po poprawce
  zaliczone. Ponowny build/odbiór prowadzi koordynator i audytor.
- Nie zapisano zatwierdzeń ani pilota, nie uruchomiono T04/T05. Dane T03
  pozostają blokadą etapu B. Commit/hash dopisze koordynator po audycie.

## T03b — uproszczenie zatwierdzania i następna plansza

### Status i cel

`done` — implementacja odebrana testami i audytem kodu; ograniczenie browser QA opisano w Outcome.
Uprościć jawne zapisy operatora i rozpoczęcie kolejnej planszy na tym samym
zdjęciu. Wymaga ukończonego T03a, nie wymaga zakończenia pilota danych.
Relevant docs pozostają jak w T03 oraz sekcja T03b zaakceptowanego planu.

### Recommended execution

`gpt-6-sol` / `medium`; niezależny audyt `gpt-6-astra` / `medium`.
Ryzyko: zapis niewłaściwej pozycji, podwójna nawigacja po retry i niejawne
zatwierdzenie. Nierozwiązane P0–P2 po dwóch cyklach blokują odbiór.

### Scope i kontrakt

- Rozszerzenie zatwierdzone przed kodowaniem: miniatury pokazują osobno liczbę
  obecnych pełnych siatek, lokalizacji i szkiców. Filtry wszystkie / bez zapisów /
  rozpoczęte / z pełną siatką obejmują całą grę, przed paginacją. Pełna siatka
  oznacza przynajmniej jedną zapisaną obecną pełną geometrię, nie komplet zdjęcia
  ani kwalifikację do treningu. Wszystkie metadane pobierane partiami istniejącym API.
- Pozycje 1–9 oraz istniejące dalsze pozycje mają jawne statusy; wybór wczytuje
  dokładny zapis i jego topologię. Brak zapisu pozostaje pusty do jawnej propozycji
  (po automatycznym przejściu propozycja jest przygotowana bez zapisu).
  Przegląd pełnego zdjęcia pokazuje numerowane, klikalne obrysy zapisanych plansz.
- Jeden właściciel stanu anotacji odświeża galerię, geometrię i rodziny po zapisie
  oraz odczycie. Nawigacja, filtry i zmiana topologii porzucają niezapisane
  zmiany bez pytania (korekta T03d); niepotwierdzone żądanie blokuje nawigację do rozstrzygnięcia.
  Baza toastów jest współdzielona w packages/ui, bez importu z Admina.

- Ukryć pole osoby w edytorze geometrii; nowe decyzje mają `actor=operator`.
  Nie przepisywać autorów wcześniejszych rewizji ani panelu rodzin.
- Grupy przycisków wczytania/propozycji i trzech zapisów mają odstępy
  poziome/pionowe także po zawinięciu, z krótkim opisem znaczenia akcji.
- Usunąć checkbox sprawdzenia węzłów. Kliknięcie „Zatwierdź pełną siatkę”
  jest świadomym potwierdzeniem wszystkich granic: tylko ta akcja wysyła
  `reviewed_all_nodes=true`. Szkic, lokalizacja i preview nie zatwierdzają
  pełnej geometrii. Pozostają walidacja backendu oraz wymaganie pełnych węzłów.
- Po potwierdzonym sukcesie `approve_full` lub `approve_location` pozycji
  1–8 otworzyć następną pozycję na tym samym źródle, przywrócić cały kadr,
  unieważnić stary preview i stan gestu. Nie kopiować zatwierdzenia ani
  geometrii poprzedniej planszy jako zapisu nowej. Wczytać istniejący zapis
  następnej pozycji; dla braku zapisu przygotować niezatwierdzoną propozycję.
  Niezgodna topologia zapisu: komunikat, bez nadpisania lub konwersji.
- „Zapisz szkic” pozostaje na pozycji. Po zatwierdzeniu pozycji 9 zatrzymać
  automatyczną nawigację; nie przełączać zdjęcia. Komunikat „Zatwierdzono
  9 plansz” tylko jeśli stan potwierdza pełne zatwierdzenia pozycji 1–9;
  w pozostałych przypadkach podać faktyczną liczbę i brakujące pozycje.
  Dziewięć to koniec tego automatycznego przebiegu, nie limit domenowy.
- Błąd/konflikt/utrata odpowiedzi pozostawia bieżącą planszę i identyczny
  request do retry. Sukces retry przechodzi raz, względem pozycji zapisanej
  w request, nie ruchomego stanu UI; zablokować podwójny submit. Restart
  odczytuje trwałe zapisy i nie powtarza zatwierdzeń automatycznie.

### Expected files i testy

Doprecyzowanie T03b — komunikaty wyłącznie w toastach:

- Wszystkie powiadomienia ekranu laboratorium (galeria, edytor, rodziny,
  backup, preview, zapis, konflikt i błędy odczytu) trafiają do wspólnego
  stosu `position: fixed` w lewym dolnym rogu viewportu. Usunąć ich kopie
  z body; scroll ani przejście między planszami nie ukrywa komunikatu.
- Sukces: zielone tło, błąd: czerwone, ostrzeżenie: pomarańczowe.
  Informacje i postęp: neutralny wariant informacyjny, bez sugerowania sukcesu.
  Treść/ikona i dostępna nazwa opisują typ niezależnie od koloru.
- Czas wszystkich rodzajów: 4 s (korekta użytkownika 2026-09-27);
  odliczanie od pokazania, wstrzymane na hover/focus i w ukrytej karcie.
  Kliknięcie body zamyka; przycisk Kopiuj kopiuje samą wiadomość bez zamknięcia;
  przyciski akcji (np. ponów) nie mogą przypadkowo zamykać komunikatu.
- Kolejka nie nadpisuje niezauważonych błędów sukcesem; powtarzający się
  identyczny komunikat scala się z licznikiem. Nie tworzyć toastu na każdy
  pointermove; aktualizacja jednej operacji zastępuje jej postęp wynikiem.
  Timeout toastu nigdy nie resetuje stanu błędu, blokady ani pending request.
- Toast informuje o niepoprawnym polu i pozwala do niego przejść; pole może
  zachować aria-invalid/oznaczenie, ale nie osobny banner komunikatu w body.
  Etykiety, instrukcje, dane raportu i kontrolki nie są powiadomieniami
  i pozostają w układzie. Niedostępna sekcja zachowuje bezpieczny stan
  oraz kontrolkę retry; szczegółowy komunikat pojawia się w toaście.
- Istniejący wzorzec to lokalny toast w
  `apps/admin/src/features/symbol-reviews/symbol-review-workspace.tsx`
  (stan SymbolReviewToast) i module CSS `.toast`; ma timeout 4 s i dwa
  warianty, nie jest gotowym wspólnym komponentem. Wydzielić/reużyć bazę
  bez zależności laboratorium od aplikacji Admin; nie kopiować kilku implementacji.
  Zmiana zachowania pozostałych ekranów dopiero w końcowym T14.
- Dodać regresje kolorów/semantyki, zamykania klik/klawiatura, zegara,
  hover/focus, kolejki/deduplikacji, widoczności po scrollu i zmianie planszy,
  konfliktu/retry po zniknięciu toastu, braku zdublowanych komunikatów w body.

Istniejące: `apps/vision-lab/src/components/geometry-editor.tsx::GeometryEditor`
(save/load), `src/app/style.css`, testy `apps/vision-lab/test/` i kontraktu
anotacji. Proponowany nowy czysty helper przejścia pozycji, jeśli potrzebny.
Bez zmian DB, treningu, portu 3001 i automatycznych decyzji za człowieka.

Kryteria odbioru/testy planowane: stały operator i brak pola/checkboxa;
pełna zgoda wyłącznie przez akcję; odstępy desktop/mobile; sukces 1→2,
szkic 1→1, 9→9; brak nadpisania istniejącej pozycji; mniej niż 9 plansz;
niezgodna topologia; błąd i konflikt bez przejścia; utrata odpowiedzi/retry
bez podwójnej nawigacji; restart zachowuje zapis i autora; regresje 5×3/3×3.
Najpierw testy UI/klienta i istniejące testy anotacji, następnie lint,
typecheck, build i browser. Każda skończona komenda z timeoutem do 120 s.

### Outcome T03b

Korekta zlecona 2026-09-27: wszystkie toasty 4 s zamiast dawnych120/180 s,
przycisk „Kopiuj” zamiast „Zamknij” kopiuje wyłącznie item.message i nie
zamyka powiadomienia. Potwierdzenie dopiero po sukcesie clipboard; odmowa/
brak clipboard pokazuje lokalny status bez alertu i dodatkowych toastów.
Pauzy hover/focus/ukryta karta, kolejka/deduplikacja, akcje i kliknięcie body
zamykające pozostają. Timeout nie zmienia pending/retry. Pliki: wspólne
toasts.tsx/toast-store.ts, regresje lab i dokumentacja. Kontrakt zastępuje
wcześniejsze czasy także w planowanym T14, bez uruchamiania T14. Testy:
fakeclock4s/pauzy/kolejka, clipboard success/fail, retry po timeout; następnie
lint/typecheck do120s. Wykonawca Sol medium/audyt Astra medium według T03b.

Wynik korekty: wspólna baza toastów ma4000ms dla każdego rodzaju i przycisk
Kopiuj z lokalnym statusem. Testy UI **29/29 PASS** (1,34 s), format,
ESLint (lab i oba pliki wspólne), typecheck oraz diffcheck PASS. Testy
potwierdzają dokładny timeout/pauzy/kolejkę, oryginalną treść clipboard,
brak sukcesu przed odpowiedzią, odmowę i brak clipboard, izolację kliknięcia
oraz skuteczne identyczne retry po wygaśnięciu toastu. Dane i usługi nietknięte.
Audyt Astra medium PASS bez P0–P2, niezależne testy20/20 (1,89s).
Build/restart wyłącznie UI PASS, HTTP200. Browser: Kopiuj pokazuje Skopiowano
po sukcesie, schowek zawiera dokładną treść, focus zachowuje toast,
po opuszczeniu przycisku toast znika. Odbiór
na osobnej karcie, bez anotowania danych; API bez restartu. DoD korekty
potwierdzone testami; fizyczny Android i restart komputera niebadane.
Commit `v1.7.11` / `9626f3b3172172b76038f7f53a8314b5eddc2595`.
Hash dopisany po commicie; kolejny patch v1.7.12 po kontroli historii.
T14 nie uruchomiono, nadrzędny T03 blocked.

- Wdrożono stałego operatora, pełną zgodę przez kliknięcie, odstępy i opisy,
  auto-przejście po potwierdzonym zapisie z idempotentnym retry, dokładne
  wczytanie istniejącej geometrii/topologii, statusy pozycji i klikalny przegląd.
- Galeria filtruje pełny katalog przed paginacją i rozdziela pełne siatki,
  lokalizacje i szkice. Wspólny stan anotacji aktualizuje wszystkich odbiorców;
  starsze odpowiedzi nie cofają rewizji. Zmiana tej samej planszy w innym
  odczycie wymaga jej ponownego sprawdzenia przed zapisem lokalnej edycji.
- Powiadomienia korzystają ze współdzielonej bazy packages/ui: kolejka,
  deduplikacja, obecnie czas4 s, pauza hover/focus/hidden, kopiowanie i akcje.
  Raport pomiarów pozostaje danymi. Timeout toastu nie resetuje pending request.
- Testy UI: helpery oraz rzeczywiste komponenty React z izolowanym transportem;
  double submit, utrata odpowiedzi po persist/retry, szkic i pozycja 9,
  dokładne zapisane cropy 3×3/5×3, dirty guard, odczyt po konflikcie,
  wspólna i monotoniczna rewizja, filtr obejmujący dalszą stronę katalogu,
  hover/focus/hidden, osobne akcje i zamknięcie toastu.
- Backend anotacji 9/9 i klient 4/4 potwierdzone przez koordynatora.
  Końcowe UI 22/22, lint aplikacji i wspólnej bazy, format, TypeScript
  i production build PASS, również po poprawce topologii.
- Audyt Astra medium: brak otwartych P0–P2; niezależne 13/13 testów
  workflow (8 React + 5 helperów). Naprawiono wyścig odczytu po konflikcie,
  deduplikację postępu toastów i rozjazd selektora zapisanej topologii.
- Nowy proces UI na 3102, HTTP 200 i katalog dostępny. Odczyt anotacji
  po restarcie UI identyczny: rewizja 20, cztery pełne geometrie na dwóch
  źródłach (3 i 1), historyczni autorzy zachowani. SHA-256 odpowiedzi:
  `4D665227F4AF308BBAA1F51A9252514F7DB669AB5A77821C1DC56D086E805AB3`.
- Końcowy browser QA i screenshot nie zostały wykonane: connector nie
  udostępnia żadnej przeglądarki, także po próbie open_in_codex. Nie użyto
  wcześniejszego zrzutu T03a jako dowodu nowego UI. Zachowania sprawdzają
  testy React; odbiór wizualny w rzeczywistej przeglądarce pozostaje ryzykiem.
- Zakres porównano z kryteriami T03b: wszystkie funkcje wdrożone, testy
  scenariuszy zapisu/retry/statusów/topologii/toastów zaliczone. Brak wyłącznie
  końcowego odbioru przeglądarkowego. Commit `v1.7.5` —
  `07f8e02f5270710e498315c30a48968fadc40441`. Hash dopisany po commicie,
  lokalnie do kolejnego commita; następny patch v1.7.6 po kontroli historii.
- Nie zmieniono API, DB ani danych użytkownika; testy nie zapisują rzeczywistych
  decyzji. T03 pozostaje blocked na pilocie, T04/T05/T14 nie uruchomiono.
  Fizyczny Android i restart komputera pozostają niesprawdzone.

## T03c — aktualizacja snapshotu z zachowaniem anotacji

Status `done`; użytkownik jawnie zlecił aktualizację zdjęć z folderu
`new_traning_set`, nie tylko odtworzenie starego katalogu. Wykonawca
`gpt-6-sol` / `medium`, audyt `gpt-6-astra` / `medium`.

Scope: istniejący importer tworzy nowy niezmienny snapshot. Nowy CLI
`vision_lab/rebase_annotations.py` domyślnie wykonuje tylko preflight;
`--apply` publikuje atomowo stan w nowym katalogu. Porównuje wszystkie
referencje bieżących anotacji, timingów i historii: identyczne id, SHA oraz
pełne metadane Catalog. Brak, zmiana albo rodziny/split (także w historii)
blokują przeniesienie. Zachowuje cały payload, receipts, historię, autorów,
rewizje i geometrię; zmienia wyłącznie state.snapshot_id. Osobny raport wiąże
digest wejścia/wyjścia oraz starego/nowego katalogu. Retry rozpoznaje dokładnie
ten sam wynik; nigdy nie nadpisuje istniejącego lub nowszego stanu celu.

Expected files: nowy moduł rebase_annotations.py, nowy
tests/test_vision_lab_rebase.py, guide VISION_LAB_LOCAL, wymagania i architektura
VISION_LAB oraz plan. API i schematy bez zmian. Root prowadzi CURRENT_STATE,
rzeczywisty import, zatrzymanie API na czas rebase, restart i commit.

Testy/DoD: zachowana pełna geometria i wszystkie metadane w nowym procesie;
zmienione anotowane zdjęcie blokuje, także referencja tylko historyczna;
rodziny/split blokują, istniejący cel/nowszy stan nie jest nadpisywany,
idempotentny retry i dry-run nie publikują zmian. Pytest, Ruff i mypy z
limitami 120 s, audyt przed operacją. Stary snapshot i anotacje pozostają.
777 zachowuje obecną rolę, bez treningu ani zmiany kwalifikacji w tym tasku.

### Outcome T03c

- Gotowy osobny CLI preflight/apply, bez zmian API. Referencje historii,
  timingów i anotacji zachowują komplet metadanych; nieznane formaty,
  rodziny/split i zmiany użytych źródeł blokują operację. Payload zachowany
  poza state.snapshot_id; osobny raport ma digests wejścia i wyjścia.
- Testy rebase 9/9 oraz istniejących anotacji 9/9: 18/18 PASS (16,68 s).
  Obejmują nowy proces, retry po utracie wyniku, nowszy cel, zapis źródłowy
  po preflight, konflikt późniejszego retry, historię, metadane i overlap.
  Ruff check i format PASS, mypy --follow-imports=silent PASS (1 moduł).
  Niezależny audytor potwierdził 9/9 (4,98 s), końcowy audyt PASS bez P0–P2.
  Koordynator wykonał preflight i apply przy zatrzymanym API.
- Guide wskazuje nowy snapshot/katalog anotacji
  `82c3c29dd35e17a1df74da249fd8687f86db6be0b781e0bb1a64f1dbbc1962c9`,
  procedurę preflight/apply/restart oraz zachowanie starego snapshotu.
- Wykonawca nie modyfikował danych użytkownika ani usług. Koordynator
  zaimportował 993 źródła i przeniósł aktualny stan: rewizja 46, 30 anotacji,
  46 zdarzeń historii. Cały payload zachowano poza state.snapshot_id;
  wejście `5ff8beaa258cc6f462fa1da3ae367fa542bde2a1502c8240ed25ac94f476860d`,
  wyjście `b480bcd288646b5a849c58a89e7531c72768610cf09c134ea6541f3384d468b7`.
  Stary katalog anotacji i snapshot pozostają nietknięte.
- Nowy proces API potwierdził przez proxy 3102 kompletny katalog zgodny
  z nowym snapshotem. SHA wszystkich 993 plików zgodne z new_traning_set;
  po jednym podglądzie każdej gry zgodnym bajtowo z encode aktualnego obrazu.
  Sprawdzone Blazing 1520×954, Gang 1520×1304, Mumie 1520×1054,
  Reels 1520×1004, Treasure 1520×1154; 777 pozostało bez zmian.
- DoD T03c: preflight/apply, zachowanie danych, retry/konflikty i atomowość
  sprawdzone testami; rzeczywisty katalog/anotacje i odczyt nowego procesu
  sprawdzone operacyjnie. Nie wykonywano browser QA, restartu komputera ani
  nowego UI builda (UI nie zmieniono). Commit T03c `v1.7.7` —
  `dd4aae3268439299da1a208f49361673c298cec4`. Hash dopisany po commicie;
  następny patch v1.7.8 po kontroli historii.
  Liczba zatwierdzeń jest odczytem operacyjnym, nie stałą fixture.
  Bez zmiany roli 777, splitu, treningu, push lub merge.

## T03d — przegląd zdjęcia i poprawki wybranych plansz

Status `done`; wykonawca `gpt-6-sol` / `medium`, niezależny audyt
`gpt-6-astra` / `medium`. Zlecony przez użytkownika pełny pion UI/API, zależy
od gotowych T03b/c. Relevant docs: niniejszy task, plan T03d, VISION_LAB
wymagania/architektura, D-450, Definition of Done.

Cel: pełne zdjęcie z numerowanymi zapisanymi siatkami, wyborem/cropami,
oznaczeniem wybranych pozycji do poprawy (opcjonalna uwaga), wycofaniem
błędnego oznaczenia i jawnym przyjęciem bieżącego zestawu geometrii zdjęcia.
Filtry: Do przeglądu (niezaakceptowane bez needs_correction), Do poprawy,
Zaakceptowane; osobny licznik pozycji wymagających poprawy/przeglądu.

Kontrakt: istniejący POST /annotations przyjmuje dodatkowo PhotoReviewRequest
z mark/withdraw/accept, source SHA i expected_board_revisions całego
zdjęcia. AnnotationState rozszerzony kompatybilnie o photo_reviews (domyślnie
pusty). Istniejące request_id/CAS/history/backup chronią wszystkie decyzje.
Accept wymaga co najmniej jednej full/present i braku needs_correction;
wiąże wszystkie bieżące rewizje, bez promowania draft/location. Mark czyści
akceptację. Zapis oznaczonej pozycji → needs_review, pozostaje na tej pozycji.
Accept domyka needs_review tylko gdy każda taka pozycja jest full/present;
szkic/lokalizacja blokuje akceptację poprawki. Nie wymaga osobnego resolve.
Withdraw wycofuje błędne zgłoszenie niezależnie od poprawki, bez akceptacji.

Split wymaga dotychczasowych warunków i aktualnej akceptacji zdjęcia. Edycja
lub otwarcie uwagi oznacza istniejący split stale bez zmiany jego przydziałów.
Rebase zachowuje nowe review/history z kontrolą wszystkich referencji; stare
dane domyślnie nieprzejrzane. UI blokuje review przy dirty geometrii i wszystkie
nawigacje przy pending; retry zachowuje identyczny request, konflikt wymaga
odczytu i ponownego sprawdzenia. Komunikaty wyłącznie toastami.

Pliki: annotation_contracts.py, annotations.py, api.py, splits.py,
rebase_annotations.py; nowy photo_review.py; OpenAPI/generowany klient/wrapper;
GeometryEditor, nowy PhotoReviewPanel, status/gallery; testy backend/request/UI;
dokumenty właścicielskie i guide. CURRENT_STATE/build/restart/commit: koordynator.

DoD/testy: stary payload bez zmian po odczycie; mark→edit→needs_review→
accept; wycofanie; niepusty full/present bez wymagania9; każda zmiana/dodanie
pozycji unieważnia, inne zdjęcie nie; stale versions/CAS, utrata odpowiedzi,
nowy proces i backup, rebase zachowuje review. API/OpenAPI/client spójne;
UI filtry/liczniki/dirty/pending/wybór/cropy i brak auto-next po naprawie.
Kolejność: testy skoncentrowane → lint/typecheck → OpenAPI/check → audit/build.
Skończone procesy limit120s. Bez zapisu realnych danych, roli777 i treningu.

### Outcome T03d

### Rozszerzenie T03d — szybki przegląd (done, 2026-09-27)

Cel: jedna sekcja pełnego zdjęcia ze wszystkimi zapisanymi siatkami, liniami
wewnętrznymi i numerami; dwa główne przyciski Zatwierdź/Odrzuć, po sukcesie
natychmiast następne. Wejście przy górze, tryb ukrywa galerię/rodziny/edytor;
zdjęcie contain ograniczone viewportem. Powrót, retry/odświeżenie przy błędzie
są technicznymi kontrolkami. Stabilna kolejka katalogu wybranej gry lub wszystkich:
źródła z full/present i statusem review, nie accepted/rejected/needs_correction.

Additive API: PhotoReviewRequest.action += reject, PhotoReview.rejected=false.
Reject sprawdza SHA/mapę/CAS i idempotencję, czyści accept, ustawia rejected,
nie zmienia geometrii ani nie tworzy issues. Mark/withdraw/edycja zachowują
rejected; dopiero jawny accept po zwykłych warunkach go usuwa. Status rejected
to Do poprawy, wykluczony ze splitu i kolejki. Stare payloady zgodne; zachowanie
historii/backup/rebase bez zmian. Backend API rozszerzenie zapowiedziane.

QuickReview wysyła dokładnie wyświetloną mapę i rewizję; zdjęcie musi zakończyć
load bez error. Ref-lock chroni doubleclick, pending blokuje wyjście i zachowuje
identyczne retry niezależnie od toastu. Stara odpowiedź nie przesuwa kursora ani
nie obniża wspólnej rewizji. Sukces przesuwa raz, restart kolejki pomija decyzje.
Konflikt wymaga jawnego odczytu/przejrzenia nowych wersji. Brak autoapprove.

Pliki: annotation_contracts.py/photo_review.py i testy lab; izolowane OpenAPI,
generated client/wrapper/request test; nowy QuickReview/helper, Page/style/status,
UI regresje i guide/req/arch/plan. Bez dotykania obcego toru partial boards,
DECISION_LOG/CURRENT_STATE, live danych i usług. Koordynator zapisuje decyzję,
build/restart/commit. Wykonawca gpt-6-sol medium/audyt gpt-6-astra medium T03d.
Testy: reject/accept/oldpayload/retry/restart/backup/rebase/split, kolejka,
load/error/stale/doubleclick/lostresponse/monotonic i istniejące workflow;
najpierw fokus, lint/typecheck, kontraktcheck, audyt. Komendy do120s.

Wynik implementacji szybkiego przeglądu (freeze): nowy QuickReview i helper
kolejki, viewportowy obraz ze wszystkimi zapisanymi siatkami/numerami oraz
wyłącznie dwa główne przyciski decyzji. Loadguard obejmuje widoczne SVG image;
drugie zdarzenie doubleclick jest ignorowane także po szybkim sukcesie/cache.
Odrzucenie trwałe bez zmiany geometrii/issues, odwracalne jawnym accept w
zwykłym panelu. Additive kontrakt laboratoryjny wygenerowano; dotychczasowy
typowany wrapper writePhotoReview obsługuje rozszerzoną unię bez duplikacji.

Kontrole: UI **34/34 PASS** (1,28 s; node --experimental-strip-types --test
apps/vision-lab/test/*.test.mjs); backend photo_review+rebase **20/20 PASS**
(17,86 s; pytest dwa odpowiadające pliki); client request **4/4 PASS** (tsx).
ESLint lab, format, app/client typecheck, Ruff, mypy13 modułów lab
--follow-imports=silent, izolowane OpenAPI --check, generated-client --check
i diffcheck PASS. Testy obejmują kolejność/gry/filtry, wszystkie obrysy,
image error/load, doubleclick, pending po4s, exactretry, niższą rewizję
odpowiedzi/GET, zmienioną geometrię receipt oraz restart/backup/rebase.
DoD względem powyższego zakresu potwierdzone: pełne zdjęcie/wszystkie siatki
i numery, dwie decyzje i następne po sukcesie, odrzucenie bez kasowania,
bezpieczne błędy/retry i trwałość po odczycie/restartach w izolowanych testach.
Niezależny audyt Astra medium PASS bez P0–P2, UI25/25 i backend11/11 PASS.
Produkcyjny build i nowe procesy API/UI PASS, HTTP200 na3102. Pierwszy krótki
readiness timeout podczas startu; po kontroli logów kolejny GET200 bez
duplikowania usług. Kopia bezpieczeństwa state.json wykonana przed restartem;
SHA256 przed/po identyczny3519739500F642069E99D2BEAFBB334FF7F5118E2F4426CF38E83D35F0692AD3.
Browser QA na osobnej karcie: kolejka63, wszystkie3 zapisane siatki pierwszego
zdjęcia, oba przyciski aktywne po załadowaniu; pełny widok1280×720 bez scrolla,
Powrót do edycji działa. Dowód artifacts/vision-lab/quick-review-qa.png.
Nie podejmowano decyzji na danych użytkownika. Restart OS/fizyczny mobile,
trening, kwalifikacja777 i obcy tor partial boards poza zakresem.
Commit `v1.7.13` / `8c7f63350b3b5ee15c96d2e84e88b034abdf3f82`.
Hash dopisany po commicie; następny patch v1.7.14 po kontroli historii.
Nadrzędny T03 nadal blocked, plik pozostaje aktywny do zakończenia
pozostałych bramek danych i splitu.

Korekta bez modalnych potwierdzeń, zlecona 2026-09-27: usunąć window.confirm
z nawigacji i jawnego reconcile oraz beforeunload. Nawigacja porzuca lokalne
niezapisane zmiany bez autosave/autoapproval; busy/pending nadal blokuje
nawigację w aplikacji, a CAS i retry bez zmian. Ten kontrakt zastępuje
wcześniejszy wymóg pytania o odrzucenie lokalnej edycji. Pliki: Page,
GeometryEditor, PhotoReviewPanel i test interakcji; dokumenty wymagań,
architektury, plan i guide. Testy UI/lint/typecheck limit120s. Brak pytań
blokujących i zmian API/danych; wykonanie/audyt według istniejącego T03d.

Wynik korekty bez dialogów: wszystkie wywołania confirm i rejestracja
beforeunload usunięte z lab UI. Testy **28/28 PASS** (0,89 s), format,
ESLint, typecheck i diffcheck PASS. Mock confirm rzuca przy każdym wywołaniu,
mock rejestracji zdarzeń odrzuca beforeunload. Regresje potwierdzają dirty
nawigację bez zapisów, jawne odczyty geometrii/review bez pytania oraz
zachowane blokady pending/busy i identyczne retry. API/backend bez zmian.
Audyt Astra medium PASS bez P0–P2; niezależne testy interakcji 13/13 PASS
(0,93 s). Produkcyjny build i nowy proces UI PASS, HTTP200 na3102.
Przeglądarka: niezapisana propozycja → pozycja2 bez dialogu; ponowna
niezapisana propozycja → reload bez dialogu. Testowano osobną kartę,
bez zapisów/akceptacji; API i dane pozostają nietknięte. DoD korekty
spełnione w tym zakresie; fizyczny Android i restart komputera niebadane.
Commit korekty `v1.7.10` / `729970227d1968ff34f752e65c57e1128c040b03`.
Hash dopisany po commicie; kolejny patch v1.7.11 po kontroli historii.
Nadrzędny T03 nadal blocked.

Korekta ergonomii zlecona 2026-09-27 po odbiorze: przegląd zapisanych plansz
na całym zdjęciu ma być domyślnie zwinięty przy wejściu na ekran, żeby
ograniczyć przewijanie. Zakres: usunięcie `open` z istniejącego `details`
w GeometryEditor i aktualizacja asercji interakcji; natywne ręczne rozwijanie
pozostaje bez nowego stanu/mechanizmu. Bez zmian API, danych i workflow.
Weryfikacja: testy interakcji UI **12/12 PASS** (0,83 s), ESLint i
typecheck PASS (limit120s). Usunięto wyłącznie `open`, istniejąca asercja
sprawdza brak wymuszonego otwarcia. Bez nowego mechanizmu wymagającego
osobnego testu remount; natywna kontrolka zachowuje ręczne rozwijanie.
Audyt korekty Astra medium PASS bez P0–P2; niezależne 12/12 testów (0,93 s).
Build i restart wyłącznie UI PASS, HTTP 200 na 3102. Przeglądarka potwierdza
open=false po wejściu i ręczne false→true→false przez nagłówek. API i dane
pozostały nietknięte; fizycznego Androida nie badano. Commit korekty `v1.7.9`
/ `f5680ba60b093c852389b234b34102e878ed564e`. Hash dopisany po commicie;
następny patch v1.7.10 po kontroli historii. CURRENT_STATE prowadzi koordynator.

Implementacja zamrożona do audytu 2026-09-27. Dodano trwały przegląd zdjęcia
w istniejącym kontrakcie `/annotations`, mapę wersji zapisanych pozycji i SHA
źródła, CAS oraz idempotentne ponowienie. `mark` nie zmienia geometrii,
poprawka przechodzi do `needs_review`, a osobne `accept` zamyka sprawdzone
poprawki i wiąże bieżący zestaw. `needs_correction` oraz korekta będąca tylko
szkicem/lokalizacją blokują akceptację. `withdraw` nie zatwierdza zdjęcia.
Zmiana geometrii unieważnia tylko akceptację tego zdjęcia. Stare rekordy
pozostają nieprzejrzane, z zachowaniem zatwierdzeń i historii. Stan przeglądu
jest objęty backupem, restartem i bezpiecznym rebase T03c.

UI ma rozwijany (po korekcie domyślnie zwinięty) widok całego zdjęcia z zapisanymi siatkami, numerami,
wyborem/cropami i tekstowymi oznaczeniami statusu; panel decyzji, filtry oraz
liczniki działają dla całej gry. Dirty/pending guards chronią edycję i retry.
Poprawiana oznaczona pozycja pozostaje wybrana; nieoznaczone pozycje zachowują
poprzedni auto-next także po wcześniejszym review i utracie odpowiedzi.
Akceptacja jest dodatkową bramką splitu; efektywny `split_stale` dawnych
splitów jest spójny dla GET, retry i nowych mutacji, bez zapisu przy odczycie.

Kontrole: backend annotations/review/rebase **25/25 PASS** (22,96 s), po
dodaniu regresji legacy splitu review **8/8 PASS** (9,27 s), czyli wszystkie
26 przypadków zakresu zaliczone. UI **27/27 PASS**, request client **4/4 PASS**;
Ruff, app ESLint, app/client typecheck, mypy zmienionych 13 modułów lab
(`--follow-imports=silent`), OpenAPI check, generated-client check oraz
`git diff --check` PASS. Pełne mypy z importami poza zakresem ujawniło
zastane błędy typów NumPy w `images/shape_geometry_v2/core.py` i
`images/contrast_frame_grid_v12.py` oraz zastane błędy w dwóch modułach API
`v7_label_geometry_calibration`, `images/qualified_manual_geometry.py`
i `images/page_geometry_preflight.py` (łącznie 27 błędów w 6 plikach);
nie zmieniano tych modułów. Ostrzeżenia
testów: istniejące Starlette/AnyIO, react-test-renderer i module type.

DoD i plan porównano punktowo: kontrakt, zachowanie statusów, izolowane
race/retry, restart/backup/rebase, wybór/cropy, filtry i ochrona edycji mają
implementację oraz regresje. Dokumenty wymagań, architektury, D-450 i guide
są zaktualizowane. Audyt Astra medium **PASS, bez P0–P2**, niezależne
review **8/8 PASS** (9,98 s). Koordynator dodatkowo potwierdził istniejące
API **21/21 PASS** (2,11 s), review **8/8 PASS** (13,10 s) i UI **27/27 PASS**.
Produkcyjny build i restart laboratorium PASS. Nowy proces API i proxy 3102
odczytują rewizję 93, 77 pełnych siatek na 27 zdjęciach. Kopia stanu
`artifacts/vision-lab/t03d-before-restart-revision-93.json` i plik po restarcie
mają identyczny SHA-256
`B5B13E5723F3FE5345E0BA730FD9BA967EB6894761E3A2D1D99142969A0AC45A`.
Odbiór przeglądarkowy read-only: filtry, pusty widok Do poprawy, numerowane
siatki, wybór pozycji 2/3 klawiaturą i 15 cropów. Oględziny w wąskim panelu
bez poziomego przepełnienia; fizyczny Android i restart komputera niebadane.
Commit T03d: `v1.7.8` / `067a0350d1f5569ffdafa4aa2cf60ae65168e2c9`.
Hash dopisany po commicie; następny patch v1.7.9 po kontroli historii.
Nadrzędny T03 pozostaje blocked.
Nie wykonano
zapisu na rzeczywistych danych, akceptacji zdjęć użytkownika, treningu ani
zmiany roli `777`; CURRENT_STATE i usługi należą do koordynatora.

## Outcome T03 (narzędzia i operacje)

### Wznowienie — odczytowy preflight danych (2026-09-27)

- Zapisano rozdzielenie zgody na geometrię od zatwierdzenia symboli w planie,
  wymaganiach i D-450. Etap C pozostaje poza zakresem wznowienia B.
- Preflight Sol medium: rewizja 259, 63 aktualne akceptacje, 180 pełnych
  obecnych siatek 5 × 3, 4320 węzłów / 2700 komórek. Kontrole SHA, map
  rewizji, struktury i granic źródeł bez błędów. Nie jest to dodatkowa
  wizualna weryfikacja jakości ani potwierdzenie poprawności symboli.
- Stan dyskowy i oba API (8102/3102) zgodne; SHA state.json przed/po:
  `22f452d0e976a9997909ece2cf9bede0073f1241574f5880fa7b3ebdbb0e0586`.
  Zero zmian anotacji, rodzin, roli źródeł, splitu lub usług.
- Blokada pozostaje: rodziny 0, brak podziału i dowodów niezależności.
  20 grup dokładnych duplikatów Reels, z czego 5 zawiera zaakceptowane
  zdjęcie i nieanotowany alias. Brak identycznych plików w samych 63
  wybranych zdjęciach nie dowodzi niezależności nagrań. Brak anotacji 3 × 3;
  nie można raportować wyuczonej jakości tej topologii.
- Raport: `ai_docs/quality/VISION_LAB_STAGE_B_DATA_PREFLIGHT.md`.
  Testy aplikacji/build nieuruchamiane: kod i kontrakty niezmienione.
  Audyt Astra medium potwierdził niezależnie liczności, akceptacje i SHA;
  poprawiono nadmierny wniosek o liczbie grup w alternatywie measurement.
  Kontrola diff bez błędów; bez zmian kodu produkcyjnego i bez jego nowych
  testów. Commit preflight: v1.7.18 (hash po commicie). T03 pozostaje
  aktywny/blocked; T04/T05 nie zostały uruchomione.

### Operacyjne przywrócenie ścieżki danych

Na jawne polecenie użytkownika przeniesiono odnaleziony snapshot oraz
`state.json` z `Documents/Nowy folder` do udokumentowanego
`Documents/game_predictor_vision_data`, bez nadpisania istniejących danych.
Przed przeniesieniem zatrzymano zweryfikowany proces API; kopię zapisów
zachowano w `recovery-backups/777-state-revision45/state.json`.
SHA-256 kopii i przeniesionego pliku jest identyczny:
`F0BF79E1BDB96F09140AED26C0F7BAFCA063D96A4C5C14BCD78F79E57DB9E490`.
Nowy proces API weryfikuje snapshot i odczytuje rewizję 45: 29 pełnych
siatek na 10 zdjęciach 777. Proxy 3102 potwierdza ten sam stan oraz HTTP 200
dla zdjęcia. Nie ustalono przyczyny wcześniejszej zmiany lokalizacji.
Nie zmieniono kodu ani geometrii, nie wykonano treningu ani browser QA.
Aktualizacja przyciętych zdjęć pozostałych gier nie jest częścią przeniesienia:
aktywny pozostaje odzyskany snapshot 1180 źródeł. Commit `v1.7.6` —
`95e0915f6175e3dc38509212460bbcc3b61b168d`. Hash dopisany po commicie;
kolejny patch v1.7.7 po kontroli historii.

Część narzędziowa odebrana 2026-09-26. Cały T03 i etap B nie są ukończone.

Commit części narzędziowej: `v1.7.2` —
`cea04bcf243e13a42b87669ced0d04ec8f6aa055`. Hash dopisany po commicie;
ten wpis pozostaje lokalnym uzupełnieniem do następnego commita.

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

- Aktualizacja po pilocie: zatwierdzenia geometrii i zdjęć zostały wykonane.
  Nadal wymagane potwierdzenie pochodzenia rodzin, ocena pomiaru pierwszych
  10 zdjęć/grę i prognozy pracy oraz zamrożenie
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

- Preflight wykonanych anotacji i rozstrzygnięcie powiązań zdjęć.
  Dopiero po spełnieniu bramek T03 można uruchomić zależny T04.
  Odblokowanie samego kodowania T04 wcześniej wymaga zmiany zaakceptowanego
  planu; nie przyjęto jej samodzielnie.
