---
title: Geometria v2 — wspólna wiedza dla obecnych i kolejnych gier
status: accepted
last_updated: 2026-09-21
---

# Geometria v2 — wspólna wiedza dla obecnych i kolejnych gier

## Cel i zakres

Wdrożyć jeden deterministyczny rdzeń geometrii dla pełnych stron z ramką:
obrys planszy, perspektywę, układ 3 × 3, siatkę 3 × 5 i kontrolę kompletności.
777, Blazing, Gang, Reels i Mumie są grami tworzenia; każda nowa gra ma
zacząć od wspólnej wiedzy, a nie od kolejnego silnika wykrywania. Jej
konfiguracja może opisać tylko rzeczywistą różnicę obrazu, np. pomocniczy kolor
ramki, proporcję lub dekorację.

Treasure nie ma zakładanej rozpoznawalnej ramki i pozostaje poza tym planem;
otrzyma osobny wariant v3/v4. Biblioteka v2 nie przechowuje obrazów, symboli,
OCR, payoutów, sekwencji ani lokalnych kotwic ORB. Wspólny profil jest wyłącznie
kandydatem: lokalne piksele, ramka i siatka muszą go potwierdzić przed
automatyczną rejestracją.

Plan jest wykonywany na `codex/shape-geometry-v2` w osobnym worktree. Zmiany
nie trafiają do głównego katalogu aplikacji; scalenie z mainline pozostaje
oddzielną decyzją po końcowym odbiorze.

## Zasady realizacji

- Właściciel upoważnił do wykonania wszystkich zadań w tej kolejności, bez
  osobnego polecenia między nimi.
- Każde zadanie ma: skoncentrowane testy, lint i kontrolę typów odpowiednią do
  zakresu, self-review, niezależny audyt `gpt-6-astra` z reasoning `medium`,
  poprawę uwag niekrytycznych, re-audyt gdy były uwagi, osobny commit oraz
  aktualizację dokumentacji i `Outcome`.
- P0/P1, w tym błędna automatyczna akceptacja, mieszanie danych gier lub
  splitów, utrata sekwencji, nieodtwarzalny snapshot, wyciek acceptance albo
  błąd migracji, zatrzymuje plan. P2/P3 naprawiamy w tym samym zadaniu i
  kontynuujemy po potwierdzeniu audytu.
- Brak lokalnych danych ogranicza wyłącznie pomiar, kwalifikację albo import
  zależny od tych danych. Nie blokuje budowy wspólnego rdzenia, biblioteki,
  API, UI i zabezpieczeń. Wynik bez mianownika ma status `not_evaluable`, nie
  jest zerowym ani zaliczonym wynikiem.
- `development`, `calibration` i `acceptance` dzielą rodziny zdjęć wewnątrz
  gry. Nie dzielą listy gier. `reels_test` i `rells_big` pozostają wykluczone.
- Każda zatwierdzona korekta może zasilić kandydata wiedzy wspólnej. Nowa
  wersja staje się aktywna automatycznie dopiero po integralności, regresji,
  jakości i replayu; nieudana kandydatura pozostawia poprzednią wersję aktywną.

## Kolejność zadań

| Kolejność | Zadanie | Rezultat |
| --- | --- | --- |
| G00 | Korpus i baseline | Ukończone: read-only manifesty, split i baseline v1.1. |
| G01 | Eksperyment i kontrakt wejścia | Rozszerzalny, checksummowany opis źródeł, porównanie wariantów oraz jawny `not_evaluable`, gdy brakuje danych. |
| G02 | Wspólny rdzeń | Czysty, deterministyczny detektor kształtu/kontrastu, projektor perspektywy, siatka i diagnostyka. |
| G06 | Trwała biblioteka | Globalne, wersjonowane profile i dowody poprzez migracje Alembic. |
| G03 | Resolver i pion aplikacji | Bezpieczne zaproponowanie profilu wspólnego oraz lokalna weryfikacja w preflight. |
| G04 | Obsługa nowej gry | Stan gotowości i jasny powód ręcznego doprecyzowania, bez obowiązkowej kotwicy per gra. |
| G07 | Kwalifikacja i automatyczna aktywacja | Deterministyczna publikacja albo zachowanie poprzedniej aktywnej wersji. |
| G05 | Pilot importu i korekt | Przepływ: wiedza istniejąca → Mumie → korekta → Gang/inna gra, z pomiarem ponownych korekt. |
| G08 | Niezależny odbiór | Odbiór zamrożonego rozwiązania na danych acceptance, gdy operator je udostępni. |

### G00 — korpus i baseline

Pozostaje ukończoną podstawą. Zachowuje rozdział executor/acceptance i brak
zapisu danych aplikacji. G01 nie może reinterpretować ani osłabić jej walidacji
splitów i źródeł.

### G01 — eksperyment i kontrakt wejścia

Rozszerzyć kontrakt corpusów tak, aby późniejsze zgodne gry mogły być dodawane
bez zmiany rdzenia. Zgodność oznacza pełną stronę z ramką i topologię v2, a nie
nazwę gry. Zachować obsługę istniejącego manifestu G00 oraz odrzucać mieszanie
splitów, drift i dane acceptance.

Uruchamialny eksperyment ma porównywać: sam kształt i kontrast, wzmocnienie
kolorem, lokalną kotwicę oraz profil transferowy wyuczony wyłącznie z innych
gier. Ma raportować osobno automaty, błędne automaty, review, korekty i koszt
konfiguracji. Przy brakujących anotacjach lub profilu zwraca deterministyczne
`not_evaluable` per gra/źródło. Numery progów wybiera wykonawca na podstawie
skonfigurowanych danych i zapisuje je jako wersjonowaną politykę jakości; nie
wymagają one kolejnej akcji właściciela, ale nie mogą być zastąpione wynikiem
bez mianownika.

### G02 — wspólny rdzeń geometrii

Zaimplementować oddzielony od transportu i ORM deterministyczny rdzeń:
neutralne kolorystycznie kandydaty obrysu, ocenę kształtu i kontrastu,
opcjonalny pomocniczy dowód koloru, homografię, regularność siatki 3 × 3/3 × 5
i kontrolę kompletności. Wynik zawiera ustrukturyzowane dowody i powód review.
Historyczne v1.0/v1.1 pozostają niezmienione.

### G06 — trwała biblioteka przed pilotem

Dodać przez migracje Alembic neutralną globalną bibliotekę wersji profili,
topologii, znormalizowanych parametrów geometrii, wielokolorowego opisu ramki,
stanu dowodów i checksum. Jest to control plane poza routerem danych gry;
`source_game_ref` jest proweniencją, nie kluczem routingu. Przechowuje metadane
i statystyki, nigdy JPEG ani dane semantyczne gry. Deduplikacja, kolejność
wersji i retry muszą być idempotentne.

### G03 — resolver i integracja preflight

Resolver wybiera jedynie zgodny aktywny profil wspólny. Worker dokonuje
lokalnej weryfikacji na bieżących pikselach i zapisuje snapshot: wersję
biblioteki, konfigurację różnic gry, dowody oraz werdykt. Niepowodzenie,
niezgodność lub brak profilu zwracają `needs_manual_review`; nie ma ukrytego
fallbacku do profilu innej gry.

### G04 — tworzenie i gotowość gry

Przy tworzeniu gry wyświetlić stan kandydata wspólnej geometrii, zgodność i
konkretny brakujący dowód. Gra może istnieć bez lokalnej kotwicy i bez koloru
ramki. Wtedy pierwszy import prowadzi do jawnego review/korekty, po której
może powstać kandydat wiedzy wspólnej.

### G07 — kwalifikacja i aktywacja wiedzy

Po każdej zaakceptowanej korekcie utworzyć wersję kandydującą. Automatyczny
kwalifikator weryfikuje schema/checksum, zgodność topologii, replay,
regresję dotychczasowych dowodów, zasady jakości oraz brak udziału badanej gry
w teście transferu. Sukces atomowo aktywuje nową wersję; porażka zapisuje
powód i nie zmienia poprzedniej aktywnej wersji.

### G05 — pilot i pomiar redukcji pracy

Wykonać kontrolowany pilot istniejącej wiedzy: najpierw Mumie, następnie
zatwierdzona korekta, potem Gang albo następna zgodna gra. Mierzyć odrębnie
przeniesienie wiedzy i lokalną konfigurację, liczbę wymaganych korekt oraz
błędne automaty. Nie uruchamiać importu na danych bez przypiętego corpusów,
snapshotów i warunków odbioru; w takim przypadku dostarczyć kompletny,
przetestowany workflow w stanie oczekiwania na dane.

### G08 — niezależny odbiór

Niezależny evaluator używa wyłącznie acceptance i zamrożonej wersji rdzenia,
profili oraz progów. Potwierdza brak wycieku, pełny łańcuch snapshotów,
deterministyczny replay i Definition of Done. Brak acceptance daje
`not_evaluable` i blokuje wyłącznie aktywację/odbiór, nie fałszuje sukcesu.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
| --- | --- | --- | --- | --- |
| G00 — korpus i baseline | gpt-5.6-terra | xhigh | Kontrakt danych, splitów i odtwarzalności. | gpt-6-astra, medium — wykonano, brak P0–P2. |
| G01 — eksperyment i kontrakt | gpt-5.6-terra | xhigh | Metodologia, zgodność wsteczna i statuty bez danych. | gpt-6-astra, medium — split, transfer i progi. |
| G02 — wspólny rdzeń | gpt-5.6-terra | xhigh | Deterministyczna geometria i regresje CV. | gpt-6-astra, medium — automaty i diagnostyka. |
| G06 — trwała biblioteka | gpt-5.6-terra | xhigh | Migracje, idempotencja i proweniencja. | gpt-6-astra, medium — migracje i izolacja gier. |
| G03 — resolver i preflight | gpt-5.6-terra | xhigh | Snapshoty, integracja i fail-closed. | gpt-6-astra, medium — transfer profilu. |
| G04 — tworzenie i gotowość gry | gpt-5.6-terra | high | Kontrakt API/UI oraz stany operatora. | gpt-6-astra, medium — bezpieczne review. |
| G07 — kwalifikacja i aktywacja | gpt-5.6-terra | xhigh | Regresje, replay i atomowa publikacja. | gpt-6-astra, medium — aktywacja i rollback. |
| G05 — pilot importu i korekt | gpt-5.6-terra | xhigh | Pion importu i pomiar redukcji korekt. | gpt-6-astra, medium — bezpieczeństwo importu. |
| G08 — niezależny odbiór | gpt-6-astra | xhigh | Niezależna ocena bramek i dowodów. | gpt-6-astra, medium — kompletność DoD. |
