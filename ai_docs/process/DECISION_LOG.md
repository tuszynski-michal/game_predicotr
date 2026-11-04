---
title: Architecture decision log — index
status: active
last_updated: 2026-11-03
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
| [D-572](decisions/DECISION_LOG_2026.md#d-572--nazwa-folderu-wynikowego-selektora) | Nazwa folderu wynikowego selektora | accepted | 2026-10-23 | Nowe partie: gra aktualizacja pierwsza-ostatnia; stary outputRoot i nazwy JPEG bez zmian; zastępuje regułę folderu D-571. |
| [D-571](decisions/DECISION_LOG_2026.md#d-571--trwały-katalog-gier-i-aktualizacja-partii-selektora) | Trwały katalog gier i aktualizacja partii selektora | accepted | 2026-10-23 | Katalog niezależny od historii; aktualizacja a+cyfry lub z_a+cyfry w etykietach, bez zmiany nazw eksportu. |
| [D-570](decisions/DECISION_LOG_2026.md#d-570--nierozpoznane-pozycje-jako-wildcard-w-wyszukiwaniu-777a2) | Nierozpoznane pozycje jako wildcard w wyszukiwaniu 777a2 | accepted | 2026-10-23 | Tylko 777a2: brak dowodu daje punkt, nadal unknown; czerwony licznik w wynikach, bez zmiany wypłat. |
| [D-568](decisions/DECISION_LOG_2026.md#d-568--zachowanie-wygranych-sprzed-rozwinięcia-super-symbolu) | Zachowanie wygranych sprzed rozwinięcia super symbolu | accepted | 2026-10-21 | Większa wypłata per (linia, symbol), sztuki raz; próg rozwinięcia i bazowa plansza uruchamiająca bez zmian. |
| [D-567](decisions/DECISION_LOG_2026.md#d-567--edytowalny-kierunek-i-granica-500000-w-selektorze-windows) | Edytowalny kierunek i granica 500000 w selektorze Windows | accepted | 2026-10-21 | Jeden wybór folderu, wspólne kompaktowe przyciski, limit nowych zakresów i trwała zmiana kierunku dalszej numeracji. |
| [D-566](decisions/DECISION_LOG_2026.md#d-566--kolejka-masowej-weryfikacji-symboli) | Kolejka masowej weryfikacji symboli | accepted | 2026-10-19 | Wyjątek od D-551 pozwala kolejkować bulk za bulk; wykonanie pozostaje pojedyncze, konflikty z innymi typami bez zmian. |
| [D-565](decisions/DECISION_LOG_2026.md#d-565--tymczasowa-baza-wypłat-i-stawki-mumii) | Tymczasowa baza wypłat i stawki Mumii | accepted | 2026-10-19 | Tabela Mumii dotyczy 10 kredytów (1 zł); wyszukiwarka ma stawki 1/2/5/10/20 zł jako tymczasowy wyjątek w kodzie dla jednej gry, bez przeliczania historii. |
| [D-564](decisions/DECISION_LOG_2026.md#d-564--super-symbol-serii-definiowany-także-przez-odbiorcę-linku-udostępniania) | Super symbol serii definiowany także przez odbiorcę linku udostępniania | accepted | 2026-10-18 | Odbiorca linku otwiera serię z każdego znacznika supergry i definiuje super symbol przez cztery trasy publiczne z aktorem sesji; `seriesId` w markerach udostępnienia, panel zarządzania bez zmian. |
| [D-563](decisions/DECISION_LOG_2026.md#d-563--przycinanie-i-usuwanie-oryginałów-importów-oczekujących-na-przegląd) | Przycinanie i usuwanie oryginałów importów oczekujących na przegląd | accepted | 2026-10-18 | Import `completed` albo `waiting_for_review` kwalifikuje oryginał; aktywne, przerwane i anulowane importy wykluczają (`IMPORT_NOT_SETTLED`). |
| [D-562](decisions/DECISION_LOG_2026.md#d-562--przycięty-wariant-zarządzanego-oryginału) | Przycięty wariant zarządzanego oryginału | accepted | 2026-10-17 | Bezstratny crop JPEG z atestem obok pliku zastępuje usunięty oryginał; współrzędne i zatwierdzenia bez zmian, odczyt poza kadrem kończy się błędem. |
| [D-561](decisions/DECISION_LOG_2026.md#d-561--parity-eksportu-onnx-względna-do-wielkości-wyjścia) | Parity eksportu ONNX względna do wielkości wyjścia | accepted | 2026-10-16 | Różnica torch/ONNX dzielona przez max(1, moduł wyjścia torch): współrzędne w pikselach nie padają na szumie fp32, wyjścia jednostkowe bez zmian. |
| [D-560](decisions/DECISION_LOG_2026.md#d-560--wspólny-kandydat-geometrii-v3-kilku-gier) | Wspólny kandydat geometrii V3 kilku gier | accepted | 2026-10-16 | Jedna baza na TRAIN kilku gier z równą wagą gier i nagrań, przypięty plan bez aliasów kontrolnych, ocena na wszystkich kohortach treningu. |
| [D-559](decisions/DECISION_LOG_2026.md#d-559--ocena-kandydata-geometrii-v3-per-gra-i-most-aktualności-dowodów) | Ocena kandydata geometrii V3 per gra i most aktualności dowodów | accepted | 2026-10-16 | Raport v2 z miarami bazy i kandydata per gra, PASS tylko bez regresji w każdej grze, proof per gra z licznikiem notices blokuje nieaktualną publikację. |
