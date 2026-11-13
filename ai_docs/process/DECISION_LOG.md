---
title: Architecture decision log — index
status: active
last_updated: 2026-11-13
---

# Decision Log

Indeks **30 najnowszych** decyzji. Pełne wpisy (kontekst, alternatywy,
konsekwencje) leżą w [decisions/DECISION_LOG_2026.md](decisions/DECISION_LOG_2026.md)
z nagłówkami `## D-NNN — …` (kotwice `#d-nnn-…`); starsze wiersze indeksu są w
[decisions/DECISION_INDEX_ARCHIVE.md](decisions/DECISION_INDEX_ARCHIVE.md).
Hierarchia źródeł prawdy (`AGENTS.md`) odnosi się do pełnych wpisów; indeks to
tylko ich skrót.

Reguły:

- Obowiązkowy odczyt startowy to ten plik. Starszej decyzji szukaj
  wyszukiwaniem, nie lekturą archiwum:
  `rg -n "<słowo|D-NNN>" ai_docs/process/DECISION_LOG.md ai_docs/process/decisions/DECISION_INDEX_ARCHIVE.md`,
  a pełny wpis otwieraj przez kotwicę, gdy `Relevant docs` taska go wskazuje
  albo gdy trzeba ocenić sprzeczność.
- Nowa decyzja: pełny wpis na początku `decisions/DECISION_LOG_2026.md` i wiersz
  na górze tabeli poniżej; wiersze ponad 30 przenieś bez zmian na początek
  tabeli w `decisions/DECISION_INDEX_ARCHIVE.md`. Spójność i budżet (30 wierszy,
  12 000 B) sprawdza `npm run docs:check`.
- Numery D-416..D-429 oraz D-548 występują w dwóch torach (kolizja numeracji;
  D-548 to panel udostępniania `main` i doszkalanie V3 z gałęzi
  `codex/v3-grid-fine-tuning`); wiersze rozróżnia tytuł i kotwica.

Znana kolizja D-578 (detektor 777 A2 oraz uczenie korekt) zachowuje dwie odrębne kotwice zgodnie z zaakceptowaną D-579; bez przepisywania historii.

## Indeks

| Nr | Tytuł | Status | Data | Jedno zdanie |
|---|---|---|---|---|
| [D-609](decisions/DECISION_LOG_2026.md#d-609--bramka-v5-plansze-bez-cięcia-symboli) | Bramka v5: plansze bez cięcia symboli | accepted | 2026-11-13 | Gate v5 = v4 plus nieregresja plansz, których żaden węzeł pola nie przesuwa się o więcej niż 10 % pola; migracja 0187 (bind v7, dyspozytor v9). |
| [D-608](decisions/DECISION_LOG_2026.md#d-608--obrysy-symboli-z-zatwierdzonych-siatek) | Obrysy symboli z zatwierdzonych siatek | accepted | 2026-11-13 | Pole siatki zatwierdzonej przez człowieka jest propozycją obrysu symbolu; etykietą staje się po masowym zatwierdzeniu w oknie Admina; ręczny edytor do usunięcia. |
| [D-607](decisions/DECISION_LOG_2026.md#d-607--limity-poleceń-kohort-300-s) | Limity poleceń kohort 300 s | accepted | 2026-11-13 | Budżet poleceń kohort, podziału korekt i pojedynczego zapytania wynosi 300 s (freeze 4847 źródeł trwał ~65 s, jedno zapytanie 38 s). |
| [D-606](decisions/DECISION_LOG_2026.md#d-606--domyślny-zakres-uczenia-korekt-importy-z-etykietami-i-kohortami) | Domyślny zakres uczenia korekt | accepted | 2026-11-12 | Bez jawnych importów uczenie bierze tylko importy z ludzką akceptacją geometrii lub członkami kohort; limit 5000 źródeł zostaje. |
| [D-605](decisions/DECISION_LOG_2026.md#d-605--równościowe-wyszukiwanie-członkostwa-kohort-i-wycofywanie-kohort) | Równościowe wyszukiwanie członkostwa kohort | accepted | 2026-11-12 | Pary członkostwa w tabeli z PK zamiast `@>` pod RLS; ta sama semantyka zdarzeń; status retired tylko frozen↔retired. |
| [D-604](decisions/DECISION_LOG_2026.md#d-604--bramka-oceny-siatek-odporna-na-szum) | Bramka oceny siatek odporna na szum | accepted | 2026-11-12 | Nowe oceny siatki (gate v4) odrzucają tylko rażące pogorszenie: >max(1, 2 %) plansz albo >max(15 %, 0,001) błędu; REG nie musi się poprawić, v2 zostaje dla historii. |
| [D-603](decisions/DECISION_LOG_2026.md#d-603--pozycja-kopii-bez-plansz-i-dłuższy-odczyt-podziału) | Pozycja kopii bez plansz i dłuższy odczyt podziału | accepted | 2026-11-11 | Kopia bez plansz przejmuje jednoznaczny atest oryginału; podział korekt ma 120 s. |
| [D-602](decisions/DECISION_LOG_2026.md#d-602--skuteczne-uczenie-korekt-i-niezależny-pomiar-pełnych-wycinków) | Skuteczne uczenie i niezależny test wycinków | accepted | 2026-11-11 | Nowe v4 wyklucza konfliktujące grupy, rozdziela próbki i używa partial TRAIN tylko do punktów; pełny A i jawne braki. |
| [D-601](decisions/DECISION_LOG_2026.md#d-601--zakres-publikacji-i-bieżąca-gotowość-nowego-uczenia) | Zakres publikacji i gotowość nowego uczenia | accepted | 2026-11-10 | Nowe etykiety nie unieważniają historycznego zakresu; reuse i apply wymagają aktualności; zalecany cel opt-in. |
| [D-600](decisions/DECISION_LOG_2026.md#d-600--krótki-zapis-manifestu-i-koszt-zależny-od-planszy) | Krótki zapis manifestu i koszt zależny od planszy | accepted | 2026-11-10 | Attestation poza blokadą, fence rewizji pod krótką blokadą; bez rozluźniania własności lub zgody. |
| [D-599](decisions/DECISION_LOG_2026.md#d-599--propozycje-siatek-do-ludzkiej-weryfikacji-symboli) | Propozycje do weryfikacji symboli | accepted | 2026-11-09 | Osobny cel zapisu pending, bez human GT i kwalifikowania automatu. |
| [D-598](decisions/DECISION_LOG_2026.md#d-598--pełne-pola-w-nowych-wycinkach-i-jawnej-korekcie) | Pełne pola w nowych wycinkach | accepted | 2026-11-09 | Jawny full-cell-v2 wiąże0% w nowych snapshotach i korekcie; historia i dowody zachowane. |
| [D-597](decisions/DECISION_LOG_2026.md#d-597--diagnostyka-kontraktu-wycinków-niezależna-od-jego-dopuszczenia) | Diagnostyka a kwalifikacja cropu | accepted | 2026-11-09 | Poprawne u/δ dostępne do diagnozy rzeczywistego clipping, produkcyjne bariery pozostają. |
| [D-596](decisions/DECISION_LOG_2026.md#d-596--jawny-pin-aktualnego-kontraktu-renderowania-w-nowym-pomiarze) | Pin kontraktu w nowym pomiarze | accepted | 2026-11-09 | Opt-in v2, import i ocena osobno, pin przez sesję/freeze/R0–R3 i wczesny guard. |
| [D-595](decisions/DECISION_LOG_2026.md#d-595--diagnostyczne-porównanie-rzeczywistych-wycinków-z-przypiętym-odniesieniem) | Diagnostyka wycinków | accepted | 2026-11-09 | Read-only capture, realny renderer, klasy i osobna granica kwalifikacji. |
| [D-594](decisions/DECISION_LOG_2026.md#d-594--przypięty-zwykły-podgląd-siatki-i-produkcyjnych-wycinków) | Zwykły podgląd siatki i cropów | accepted | 2026-11-09 | Opcjonalne piny, prawdziwe footprinty, ochrona źródeł blind i brak ghost obrysów. |
| [D-593](decisions/DECISION_LOG_2026.md#d-593--izolowane-etykietowanie-i-dowodowy-eksport-html) | Izolowane etykietowanie i HTML | accepted | 2026-11-08 | Osobne edytory, snapshot-bound metadata/asset i rzeczywiste15rastrów z CLI. |
| [D-592](decisions/DECISION_LOG_2026.md#d-592--ograniczony-eksperyment-uczenia-pełnych-symboli-z-jednym-budżetem) | Ograniczony eksperyment pełnych symboli | accepted | 2026-11-08 | Jeden child R0–R3, wspólny budżet, dowiedziony TRAIN, ranking A i rzeczywiste warianty wejścia. |
| [D-591](decisions/DECISION_LOG_2026.md#d-591--ocena-zawartości-produkcyjnych-wycinków-z-niezależnym-odniesieniem) | Ocena produkcyjnych wycinków | accepted | 2026-11-08 | Realny raster, u/δ, brak kompensacji błędów i wersjonowana bramka T3. |
| [D-590](decisions/DECISION_LOG_2026.md#d-590--niezależna-zawartość-15-pól-i-ślepy-pomiar-powtarzalności) | Zawartość 15 pól i ślepy pomiar | accepted | 2026-11-08 | Własne etykiety, oracle produkcji, u/δ i jawny świeży REG bez zmiany legacy. |
| [D-589](decisions/DECISION_LOG_2026.md#d-589--jawny-nadzór-visibility15-i-próg-brzegu-wejścia-w-kontrakcie-v2) | Nadzór visibility15 i próg brzegu v2 | accepted | 2026-11-08 | Opt-in24/15, maski realnych pikseli, ekspozycja checkpointu i próg tylkoA; v1 bez zmian. |
| [D-588](decisions/DECISION_LOG_2026.md#d-588--jawny-odczyt-kwalifikacji-i-diagnostyka-rzeczywistego-wejścia) | Odczyt kwalifikacji i diagnostyka wejścia | accepted | 2026-11-04 | Compact publiczny read-model i strict diagnosticv2; historia, ręczne approval i rzeczywisty raster zachowane. |
| [D-587](decisions/DECISION_LOG_2026.md#d-587--trwałe-cele-walidacji-i-odrębna-kwalifikacja-automatu) | Cele walidacji i kwalifikacja automatu | accepted | 2026-11-04 | A/B w istniejącym ledger, partial assessment, niezależne progi i historyczne piny. |
| [D-586](decisions/DECISION_LOG_2026.md#d-586--korekty-detektora-i-dowodowy-ratunek-z-trwałym-budżetem) | Korekty detektora i dowodowy ratunek | accepted | 2026-11-03 | Full TRAIN/A, partial REG, photo-first checkpoint i jeden dowiedziony wariant z trwałym1+1. |
| [D-585](decisions/DECISION_LOG_2026.md#d-585--jawne-możliwości-i-przypięta-kwalifikacja-gry-w-nowych-operacjach-sieci) | Możliwości modelu i kwalifikacja gry | accepted | 2026-11-03 | Nowe v14/v3 przypina capabilities i exact per-game report lub unqualified, bez zmiany historii. |
| [D-584](decisions/DECISION_LOG_2026.md#d-584--wersjonowana-bezpieczna-akceptacja-siatek) | Wersjonowana bezpieczna akceptacja siatek | accepted | 2026-11-03 | Nowe v2 blokuje błędy fit i niepełne dowody; stare piny v1 zachowują semantykę. |
| [D-583](decisions/DECISION_LOG_2026.md#d-583--fizyczne-usunięcie-zastępowanego-zdjęcia-i-mały-manifest-luk) | Fizyczne usunięcie zdjęcia | accepted | 2026-11-03 | Source-only purge, compact manifest i tombstone, modele zachowane. |
| [D-582](decisions/DECISION_LOG_2026.md#d-582--przyrostowe-wyspy-treningu-i-zwalnianie-nieużytych-rezerwacji) | Przyrostowe wyspy treningu i zwalnianie nieużytych rezerwacji | accepted | 2026-11-03 | V2 zachowuje rzeczywiste kontrole i bufory; zwalnia wyłącznie niechronione metadane v1 przy freeze, bez zmiany historii. |
| [D-581](decisions/DECISION_LOG_2026.md#d-581--wspólne-pułapy-budżetu-uczenia-siatek) | Wspólne pułapy budżetu uczenia siatek | accepted | 2026-11-03 | 8000 kroków/7200 s, jednorazowa polityka legacy przy wznowieniu, bez resetu zużycia i zmiany planu. |
| [D-580](decisions/DECISION_LOG_2026.md#d-580--wycofanie-całego-źródła-i-autoryzacja-otwartej-luki) | Wycofanie źródła i autoryzacja luki | accepted | 2026-11-03 | Immutable preview, per-entry request i dowiedziony wewnętrzny derive. |
