---
title: Laboratorium geometrii plansz i rozpoznawania symboli — plan wykonawczy
status: accepted
last_updated: 2026-09-25
---

# Laboratorium geometrii i symboli

## Stan, cel i granice

Obecny worker ma geometrię i `SpatialSymbolCnn` dla aplikacji, a historyczny
eksperyment keypoint (D-262) pozostał shadow. Prototyp `screen_layout_v3`
(TASK-0648) i hybryda 777 pokazują błędy na zasłonięciach, refleksach i
skrajnych planszach. Budujemy lokalne laboratorium do oglądania siatek,
poprawiania anotacji, treningu i porównywania kandydatów. Startujemy od
hybrydy; bezpośrednia sieć węzłów jest wymiennym silnikiem uruchamianym
warunkowo. Kandydat trafia później do aplikacji wyłącznie jako review/shadow.

Laboratorium obsługuje topologie **5 kolumn × 3 wiersze** i **3 × 3**.
Integracja z obecną aplikacją obejmuje tylko 5 × 3; pełne 3 × 3 wymaga
osobnego planu zależności od 15 komórek. Historyczne 777 służy tylko do
porównania. 777 V2 jest osobną grą. Pracujemy w bieżącym katalogu na gałęzi
przygotowanej przez użytkownika. Nie ma automatycznego push, merge, aktywacji
modelu ani wdrożenia. Liczności zdjęć i podziałów zapisuje manifest konkretnej
wersji danych, a nie ten plan.

## Dane, etykiety i podziały

D-447 dopuszcza dwa jawnie różne źródła etykiet: zatwierdzenie w aplikacji i
`lab_human_approved`. Laboratorium zapisuje tożsamość gry i wersję słownika,
obraz oraz SHA-256, planszę, komórkę, rewizję geometrii, dokładny crop oraz
SHA-256, etykietę, rewizję zatwierdzenia i czas decyzji. Zmiana geometrii lub
cropa wyłącza próbkę z treningu do ponownego zatwierdzenia. Predykcja nie jest
zatwierdzeniem. Gra bez rekordu DB ma lokalną tożsamość i ręcznie zatwierdzony
słownik; rejestracja w aplikacji wymaga jawnego mapowania gry i symboli.
Istniejące reguły zatwierdzeń DB pozostają bez zmian.

Eksporter działa w głównym środowisku tylko do odczytu. Manifest wejściowy
ogranicza źródła, ich dostępne rewizje, metadane pochodzenia, słowniki,
powiązane zatwierdzone etykiety i historyczne 777 do porównania. Transakcja
`REPEATABLE READ READ ONLY` jest krótka, ma limity czasu i partie. Snapshot
publikuje się atomowo po sprawdzeniu kompletności i checksum. Pierwotny wynik
`selective_board_review_v1_1` i późniejsza ręczna reweryfikacja to odrębne
pozycje; brak pierwotnej rewizji oznacza brak porównania.

Manifest wejściowy v1 ma `schemaVersion`, `datasetName` i listę
`{gameId, sourceImageId, expectedSourceSha256, sourceFamilyId, role}`;
`role` rozróżnia zwykłe dane, historyczne 777 i zadeklarowane 777 V2.
Snapshot ID jest SHA-256 kanonicznego wejścia, wersji eksportera i
zamrożonych identyfikatorów/rewizji DB. Pierwsza krótka transakcja przypina
dokładne ID, rewizje i fingerprinty wierszy. Kolejne krótkie transakcje
czytają tylko te ID i sprawdzają fingerprint; drift lub brak rekordu
odrzuca publikację. Kolejność: freeze metadanych → eksport partiami →
kopia zarządzanych obrazów z kontrolą SHA → tymczasowy manifest z checksumami
→ fsync plików → atomowy rename na tym samym wolumenie. Retry z tym samym
fingerprintem weryfikuje snapshot i zwraca go; konflikt kończy błędem.

Folder `777` traktujemy jako historyczny, dopóki nie zostanie wykazane inne
pochodzenie. 777 V2 wymaga deklaracji użytkownika dla nagrania/rodziny źródeł
oraz kontroli konfliktów checksum i podobieństwa. Brak trafienia podobieństwa
nie dowodzi niezależności. Sprzeczne lub nierozstrzygnięte źródła są wyłączone
z treningu. Ten projekt nie uzupełnia slotów siecią w reweryfikacji
historycznego 777 (TASK-0645–0647).

Anotacja ma trzy warstwy: lokalizacja (obecność, topologia, cztery narożniki),
pełna geometria (wszystkie węzły i granice komórek) oraz symbole (dokładny
crop i klasa). Interpolacja z narożników jest propozycją, nie referencją
pełnej siatki. Pilot: do 40 zdjęć na grę z co najmniej 10 rodzin, jeśli są
dostępne; początkowe 30 pełnych siatek na kombinację gra–topologia. Pierwsze
10 zdjęć na grę mierzy czas anotacji. Niedobory i rozszerzenia są jawne.

Podział grupuje nagrania/rodziny, duplikaty i pochodne obrazu. Przed pierwszym
treningiem geometrii zamrażamy development, validation, final test i grę
niewidzianą przez geometrię. Na STOP A pokazujemy kandydatów; domyślnie grę
o środkowej liczbie niezależnych rodzin, bez zabrania jedynej topologii z
treningu. Wybór zapisuje T03 przed treningiem. Jeśli dane nie wystarczają,
raportujemy brak wiarygodnego testu między grami. Symbole mają własny podział
per gra.

## Kontrakty, środowisko i bezpieczeństwo

Proponowane `GeometryEngine`, `GeometryResult` i `SymbolRecognizer` pozwalają
podmienić `baseline`, `hybrid` i `neural_grid` bez zmiany odbiorców. Wynik
zawiera źródło, topologię, plansze, wszystkie węzły, pochodzenie punktów,
wersję modelu i powody korekty. Układ plansz na ekranie jest oddzielony od
`BoardTopology` pojedynczej planszy. 5 × 3 ma 24 węzły, 3 × 3 ma 16.
Nie wymuszamy dziewięciu plansz; nieobecność, zasłonięcie i nieczytelność są
odrębne. Bramki sprawdzają kolejność, przecięcia, dodatnie pola i kompletność
bez zależności od jednego algorytmu OpenCV.

Hybryda używa lekkiego `MobileNetV3-Small`, narożników, perspektywy i
opcjonalnego lokalnego dopasowania. Pełna sieć przewiduje węzły bezpośrednio.
Symbole porównują RGB, szarość powieloną do 3 kanałów i fuzję z udziałem RGB
`0`, `0,1`, `0,2`, `0,3`, bazując na `SpatialSymbolCnn`. Każdy wariant ma
wersję preprocessingu. Kalibracja i wybór są tylko na walidacji; niezgodność
modeli oznacza niepewność. Testy obejmują wiśnia–winogrono, refleksy i
kontrolowane zmiany barwy.

Proponowany FastAPI `game_predictor_worker.vision_lab` działa na
`127.0.0.1:8102`, Next.js `apps/vision-lab` na `127.0.0.1:3102`.
Zajęty port zgłasza błąd bez zabijania procesu. Frontend używa proxy Next.js
z zamkniętą listą tras. FastAPI jest właścicielem OpenAPI i osobnego
generowanego klienta; kontrola wchodzi do głównego `openapi:check` i
`quality`. Oba wejścia HTTP kontrolują `Host`; zapis wymaga dozwolonego
`Origin` i JSON, także przez proxy. Assety mają zarejestrowane identyfikatory,
bez ścieżek podanych przez klienta. Brak tunelu.

Dane poza repo: `C:\Users\tuszy\Documents\game_predictor_vision_data`.
Niezmienne manifesty, zarządzane kopie obrazów, anotacje, checkpointy i
raporty zapisują się atomowo. T03 obejmuje backup i próbę odtworzenia.
Laboratorium nie importuje `storage`, `psycopg` ani produkcyjnego handlera
treningu; produkcyjne punkty wejścia nie importują `vision_lab`; neutralny
rdzeń nie zależy od laboratorium ani bazy. Eksporter jest osobnym narzędziem.

Izolowane środowisko przypina PyTorch `2.12.1`, torchvision `0.27.1` i CUDA
13.0: najpierw pakiety CUDA, potem projekt z constraints, na końcu kontrola
wersji, `torch.version.cuda`, GPU i krótkie obliczenie. Główne środowisko
pozostaje nietknięte; integracja CPU używa ONNX Runtime. Checkpoint v2
zawiera optimizer, scheduler, RNG, konfigurację i checksumę danych. Odczyt v1
pozostaje możliwy, lecz nie obiecuje identycznego numerycznie wznowienia.

## Zadania i punkty STOP

Każdy task ma własny audyt, commit, Outcome i aktualizację `CURRENT_STATE.md`.
Polecenie uruchomienia etapu obejmuje wszystkie jego taski. P00 zapisuje plan,
reguły pracy etapami i D-447, a **nie uruchamia A**.

| Etap | Task | Wynik i bramka |
|---|---|---|
| P00 | [TASK-0665](../tasks/completed/0665-vision-lab-plan.md) | Plan, dokumenty, zadania i spójne reguły; stary plan zastąpiony. |
| A | [TASK-0666](../tasks/0666-vision-lab-export.md) | Ograniczony eksporter read-only; bez częściowych snapshotów. |
| A | [TASK-0667](../tasks/0667-vision-lab-gallery.md) | Kontrakty, baseline, galeria i bezpieczne lokalne API; błędny obraz nie zatrzymuje galerii. |
| B | [TASK-0668](../tasks/0668-vision-lab-geometry-annotations.md) | Edytor, warstwowy zbiór, backup, zamrożony split i pomiar kosztu. |
| B | [TASK-0669](../tasks/0669-vision-lab-training-core.md) | Neutralny rdzeń, trwały backend runów, izolowane GPU, checkpoint v2 i odczyt v1; bez przepięcia produkcji. |
| B | [TASK-0670](../tasks/0670-vision-lab-hybrid.md) | Hybryda i pierwszy checkpoint widoczny w galerii; ONNX. |
| C | [TASK-0671](../tasks/0671-vision-lab-symbol-labels.md) | Zatwierdzenia DB/lab, słowniki lokalne, ponowna zgoda po recrop. |
| C | [TASK-0672](../tasks/0672-vision-lab-symbol-models.md) | RGB, szarość, fuzja, kalibracja i metryki per klasa. |
| C | [TASK-0673](../tasks/0673-vision-lab-training-panel.md) | Panel start/cancel/postęp/retry i historia korzysta z trwałego backendu T04. |
| C | [TASK-0674](../tasks/0674-vision-lab-validation.md) | Walidacja i zamrożenie modelu/progów przed testem. |
| D | [TASK-0675](../tasks/0675-vision-lab-neural-grid.md) | Warunkowa sieć pełnych węzłów; brak danych daje konkretny plan anotacji. |
| E | [TASK-0676](../tasks/0676-vision-lab-geometry-integration.md) | Review/shadow tylko 5 × 3, 3 × 3 jawnie nieobsługiwane w aplikacji. |
| E | [TASK-0677](../tasks/0677-vision-lab-symbol-integration.md) | ONNX, pochodzenie i mapowanie; dopiero teraz przepięcie handlera na wspólny rdzeń. |
| E | [TASK-0678](../tasks/0678-vision-lab-final-acceptance.md) | Zamrożony test, niewidziana gra, restart i raport bez automatycznej aktywacji. |

**STOP A:** galeria, manifest, kandydaci gry testowej, cele anotacji per gra,
lista pobrań i budżet B; koszt czasu jest wstępny. **STOP B:** wynik hybrydy,
rzeczywisty czas anotacji i błędy. **STOP C:** raport walidacji i rekomendacja.
**STOP D:** kandydat lub raport brakujących danych. **STOP E:** kandydat
review/shadow i ograniczenia. Każdy etap wymaga jawnego uruchomienia. Przed
wydatkiem lub operacją poza zatwierdzonym zakresem następuje stop.

Budżet początkowy T05 i T10: do 50 kroków testowych oraz jeden trening do
20 epok lub 30 minut. T07: dwa treningi (RGB, szarość), każdy do 20 epok lub
30 minut; fuzja używa ich wyników. Dostępne zależności, wagi i koszt pokazuje
się przed etapem. Trening ma kontrolowany PID, timeout i raport postępu.

T04 jest właścicielem trwałego protokołu runów backendu; T08 dodaje panel
jako klienta tego kontraktu. Kanoniczny
fingerprint wiąże manifest danych, konfigurację, model, topologię,
preprocessing i seed. Trwały `requestId` z identycznym payloadem zwraca ten
sam run po utracie odpowiedzi; inny payload daje konflikt. Backend zapisuje
`queued` przed startem procesu, a `running` wiąże PID, czas startu, token
lease i heartbeat. Terminalne stany to `succeeded`, `failed`, `cancelled`;
panel nie obiecuje pauzy. Po restarcie żywy proces jest tylko obserwowany,
a wygasły lease po sprawdzeniu PID przechodzi w recoverable `failed`, bez
drugiej kopii. Cancel utrwala intencję i kończy proces po checkpointcie.
Jawne retry tworzy nową próbę tego samego runu po sprawdzeniu fingerprintu
i nowym lease; stary token nie może zapisać. `succeeded` wymaga atomowego
raportu i checksum artefaktów.

## Pomiar, mapa wymagań i kontrole

W T03, przed hybrydą, zamrażamy rozłączne zestawy baseline/hybryda. Losujemy
przydział w obrębie gry i trudności. Użytkownik nie poprawia tego samego
zdjęcia obiema metodami; materiał nie trafia do treningu. Referencja jest
oceniana bez informacji o silniku. Aktywny czas wyklucza przerwę > 30 s.
Raport obejmuje czas, liczbę korekt i końcową jakość. Redukcja 30% to cel
badany, a wynik małej próby jest wstępny.

| Wymaganie | Zadania | Dowód |
|---|---|---|
| Wymiana hybrydy na sieć | T02, T05, T10 | Jeden kontrakt i niezmienieni odbiorcy. |
| Wczesny podgląd | T02, T05 | Galeria przed treningiem, potem pierwszy checkpoint. |
| Obie topologie w labie | T02–T05, T10 | 24/16 węzłów i właściwe cropy. |
| Integracja tylko 5 × 3 | T11–T13 | 3 × 3 odrzucone bez modyfikacji danych. |
| Pochodzenie etykiet | P00, T06, T12 | Typ decyzji, SHA cropa, mapowanie gry. |
| Brak przecieku 777 | T01, T03, T09, T13 | Manifest ról i rozdzielone metryki. |
| Refleksy i kolor | T07, T12, T13 | Wiśnia–winogrono, per klasa, test zmiany barwy. |
| Ochrona HTTP | T02 | Obcy Host/Origin, prosty POST i obca trasa odrzucone. |
| Trwałość i izolacja | T03, T04, T08 | Restart, backup, importy, checkpoint v1/v2. |
| Praca etapami | P00 i taski | Audyt, commit, Outcome i STOP etapu. |

D-261 obowiązuje przy późniejszej aktywacji domyślnej; liczby zdjęć w folderze
nie zastępują wymaganej liczby źródeł, plansz, kategorii i jakości. D-262
pozostaje odniesieniem do wcześniejszego eksperymentu. Testy zmienionego
przepływu poprzedzają lint/typecheck i uzasadnione szersze kontrole. `quality`
obejmuje generowany kontrakt labu. Nie uruchamia się nieograniczonych prób.

Zatrzymanie w trakcie etapu następuje przy sprzeczności wymagań, brakującej
koniecznej decyzji, niedostępnym modelu/reasoning, nierozwiązanych P0–P2 po
dwóch cyklach poprawek albo przed operacją/kosztem poza zakresem. Jeden
wykonawca naraz zapisuje kod, a audytor pracuje w osobnej sesji. Modelu nie
podmienia się niejawnie. Sama tabela modeli nie jest zgodą na delegowanie;
wyraźne polecenie etapu jest taką zgodą. Reguła właścicielska jest w
`AGENTS.md`.

Nie wykonano instalacji, treningu ani testów nowej implementacji. Porty,
gałąź, dostępność GPU i wolne numery są ponownie sprawdzane na początku
odpowiednich etapów.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| P00 / TASK-0665 | `gpt-6-sol` | `high` | Spójność wymagań, decyzji i reguł etapów. | `gpt-6-astra`, `medium` |
| T01 / TASK-0666 | `gpt-6-sol` | `high` | Ochrona DB i snapshotu. | `gpt-6-astra`, `high` |
| T02 / TASK-0667 | `gpt-6-sol` | `high` | Kontrakt UI/API i HTTP. | `gpt-6-astra`, `high` |
| T03 / TASK-0668 | `gpt-6-sol` | `high` | Trwałość anotacji i podziały. | `gpt-6-astra`, `high` |
| T04 / TASK-0669 | `gpt-6-sol` | `high` | Izolacja, trwały protokół runów i checkpointy. | `gpt-6-astra`, `high` |
| T05 / TASK-0670 | `gpt-6-astra` | `high` | Geometria i trening. | `gpt-6-sol`, `high` |
| T06 / TASK-0671 | `gpt-6-sol` | `high` | Słowniki i tożsamość cropów. | `gpt-6-astra`, `high` |
| T07 / TASK-0672 | `gpt-6-astra` | `high` | Kalibracja i odporność na kolor. | `gpt-6-sol`, `high` |
| T08 / TASK-0673 | `gpt-5.6-terra` | `high` | UI gotowych kontraktów. | `gpt-6-astra`, `medium` |
| T09 / TASK-0674 | `gpt-6-astra` | `high` | Ocena dowodów i wybór kierunku. | `gpt-6-sol`, `high` |
| T10 / TASK-0675 | `gpt-6-astra` | `high` | Sieć obu topologii. | `gpt-6-sol`, `high` |
| T11 / TASK-0676 | `gpt-6-sol` | `high` | Rewizje i przepływ 5 × 3. | `gpt-6-astra`, `high` |
| T12 / TASK-0677 | `gpt-6-sol` | `high` | ONNX, pochodzenie i regresja produkcji. | `gpt-6-astra`, `high` |
| T13 / TASK-0678 | `gpt-6-astra` | `high` | Test końcowy i odbiór. | `gpt-6-sol`, `high` |
