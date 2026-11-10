---
title: Architecture decision log — index
status: active
last_updated: 2026-11-09
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
| [D-579](decisions/DECISION_LOG_2026.md#d-579--manifest-wymiany-źródła-z-zachowaniem-historii) | Manifest wymiany źródła | accepted | 2026-11-03 | Exact source/alias planned i chronologia ocen człowieka. |
| [D-578](decisions/DECISION_LOG_2026.md#d-578--uczenie-korekt-i-ocena-w-jawnym-zakresie) | Uczenie korekt i ocena w jawnym zakresie | accepted | 2026-11-02 | Partial controls, report v3/gate v2 i trwały parent zwalniający slot. |
| [D-578](decisions/DECISION_LOG_2026.md#d-578--niezależny-detektor-jakości-777-a2-na-zamrożonym-kandydacie-nr-5) | Niezależny detektor jakości 777 A2 | accepted | 2026-11-02 | Frozen kandydat nr 5 bez aktywacji, dwa heady i niezależna bramka przed skanem. |
| [D-577](decisions/DECISION_LOG_2026.md#d-577--podział-korekt-geometrii-z-atestów-i-trwała-ochrona-zdjęć) | Podział korekt geometrii z atestów i trwała ochrona zdjęć | accepted | 2026-11-02 | Photo-only, atesty SHA, trzy bloki i trwałe role/bufory; stare polityki bez zmian. |
| [D-576](decisions/DECISION_LOG_2026.md#d-576--uproszczenie-wyszukiwarki-i-modal-supergry-w-adminie) | Uproszczenie wyszukiwarki i modal supergry w Adminie | accepted | 2026-11-01 | TASK-1115: tabela pod wykresem, PLN i najnowsze reguły; modal w miejscu, 0 dla dziesiątego symbolu. |
| [D-575](decisions/DECISION_LOG_2026.md#d-575--powrót-do-wyszukiwania-jednej-planszy) | Powrót do wyszukiwania jednej planszy | accepted | 2026-10-30 | TASK-1114 usuwa wiele wzorów; jedna plansza, ±15 i historia pozostają. |
| [D-574](decisions/DECISION_LOG_2026.md#d-574--przypięty-wybór-i-optymistyczna-nawigacja-selektora) | Przypięty wybór i optymistyczna nawigacja Selektora | accepted | 2026-10-29 | Jeden writer, przypięte F, timeout i handshake przed close; bez zmian trwałego formatu. |
| [D-573](decisions/DECISION_LOG_2026.md#d-573--wyszukiwanie-po-kolejnych-układach) | Wyszukiwanie po kolejnych układach | accepted | 2026-10-24 | 1–4 spiny, ranking cykliczny, historia v2, wygrane od końca; od 2026-10-27 wzory przed szukaniem, podgląd +10 zdjęć i limit 60 s. |
