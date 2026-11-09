---
title: Poprawa cięcia pełnych symboli w planszach 3 × 5
status: accepted
last_updated: 2026-11-09
---

# Poprawa cięcia pełnych symboli w planszach 3 × 5

Operator zlecił cały plan T0–T5 i zaakceptował 8–12 godzin implementacji,
testów i audytów (2026-11-08). Upoważnienie obejmuje wykonawców według tabeli
i ograniczone pakiety kodu/dokumentacji przekazywane do Anthropic.
Rzeczywisty trening, merge/push, migracje operatora, restarty, aktywacja
i import pozostałych zdjęć wymagają osobnych zgód. W razie limitu Opus
operator polecił kontynuować implementację i odłożyć audyty; oczekujące
zmiany nie otrzymują PASS i nie są zamykane jako audytowane.

Stan wykonania 2026-11-09: T0–T5 wykonane z osobnymi commitami v1.7.572–577
i audytami Opus PASS; każde zadanie zamknięto przez task-close. Operator
zaakceptował ujawniony wzrost szacunku
do 15–19 godzin, w tym domknięcie kalibracji BASE/WIDE. Szczegółowy odbiór:
`ai_docs/quality/FULL_SYMBOL_CROPS_ACCEPTANCE_20261109.md`. Historyczny
werdykt audytu projektu poniżej nie jest przepisywany przez audyty kodu.

## Stan i cel

Audyt projektu wykonał Claude Code Opus 5.5/High, tylko do odczytu.
Pierwszy przegląd: REVISE; sprawdzenie poprawek zamknęło wcześniejsze
uwagi i wskazało siedem doprecyzowań, zawartych poniżej. Ostatni formalny
werdykt pozostaje REVISE. Nie stanowi to audytu przyszłej implementacji.

Nowy model poprawił A 44/45→45/45 i REG 17/21→21/21, ale błąd A wzrósł
0,678→0,965 px. 36 etykiet A stanowiły zatwierdzone predykcje bazy:
zatwierdzenia są ważne, lecz nie są niezależnym pomiarem subpikselowym.
Referencja: root `artifacts/grid-detector-training-20261107/block-analysis/analysis.html`.

Potwierdzone: sieć zwraca 24 punkty i 15 visibility, kontrola i fixture
wymagają 24 visibility; loss korekt pomija visibility. Kontrola zewnętrznego
quadu nie dowodzi zachowania zawartości właściwych komórek. Zarchiwizowane
wejście 462205 już ucinało górny rząd. Softargmax ogranicza punkty do wejścia.
Ostatni TRAIN obejmował 10 zdjęć jednej gry. Układ 3×5 jest już kodowany.

Cel: poprawne propozycje pełnych plansz i rzeczywistych wycinków symboli,
zmierzone względem niezależnych etykiet. Nie zakładamy jakości innych gier.

## T0 — Trwała procedura audytu (TASK-1163)

Jeden wersjonowany runner, istniejący `scripts/audit_task.ps1` jako wejście,
spójne instrukcje startowe i kopie skilli. Standard: terminal i dynamiczne
wykrywanie instalacji. Rozróżniać brak PATH, brak instalacji, auth CLI
i działającą aplikację. Jedna próba i ograniczona diagnostyka po błędzie
auth; bez pętli logowania i kopiowania poświadczeń. Desktop jest jawną
metodą zastępczą ze śladem faktycznego wykonania.

Zachować scope, aktywność streamu, idempotencję i własność procesu. Operator
2026-11-08 zwiększył limit audytu z 480 do 1800 s; host do 1860 s, idle nadal60s.
Sprawdzać główny model i rzeczywisty raport, nie zbiór modeli pomocniczych.
Effort zapisywać jako żądany lub obserwowane ustawienie UI. Brak raportu,
błąd dostępu i otwarte P0/P1 blokują zamknięcie; nigdy zastępczy PASS.
Test nowego procesu i odrębnego worktree; żadnych wersji CLI/PID na sztywno.

## T1 — Kontrakt modelu i widoczność (TASK-1164)

Wersjonować cały pion trening→eksport→worker→kontrola→API. Peak ma 24,
visibility 15. Cele: visible=1, occluded/out_of_frame=0, unknown=mask.
Po crop/augmentacji przeliczać dostępność zawartości; punkty nie są jej dowodem.
Node weights [N,24] obejmują rzeczywiste wsparcie i osiągalny zakres softargmax
[stride/2, wymiar−stride/2]; visibility targets/masks mają [N,15]. Pominięte
składniki jawnie liczyć, nie podmieniać na idealne przykłady. Inferencja nie
używa GT-mask do ukrywania słabych punktów. Stare wersje zachowują semantykę.

Do uznania nadzoru visibility: po 30 rzeczywistych dodatnich i ujemnych
komórek z co najmniej 5 zdjęć TRAIN na klasę. Bez tego oś niezwalidowana,
loss maskowany i brak automatu; geometria może się uczyć. Min po 15 oznacza
świadomą blokadę automatu na zasłoniętej planszy.

Nowa oś inputEdgeClearance: minimalna odległość surowych zewnętrznych węzłów
od brzegu realnego wejścia, normalizowana nominalną komórką według canvas/margin.
To podejrzenie, nie dowód kompletności. A wybiera próg: minimum przeoczonych
ucięć, minimum zbędnych rescue, niższy próg. Min. 5 rzeczywistych uciętych
plansz z 3 zdjęć dla wariantu; inaczej próg nieustalony i brak automatu.
Test prawdziwego BoardExport na uciętym rzędzie ujawnia ograniczenia.

## T2 — Niezależne etykiety zawartości (TASK-1165)

Zachować geometrię, role i historię. Dodać 4-punktową obwiednię pełnej widocznej
grafiki/obrysu bez tła pola w pikselach źródła, stan visible/occluded/
out_of_frame/unknown, własną rewizję i pochodzenie/aktora. Obwiednia nie
przesuwa się z geometryRevision. „10” jest jedną komórką. AI-propozycje
wymagają człowieka; w ślepym pomiarze nie pokazuje się żadnych propozycji AI.

Przed wyborem checkpointu ślepo ponownie oznaczyć A. Pomiar powtarzalności:
≥30 plansz z ≥10 zdjęć TRAIN/A per gra, dwa przebiegi bez widoku wcześniejszych
etykiet. Ten sam operator oznacza powtarzalność wewnątrzoperatorską.
u=P95 symetrycznej rozbieżności brzegów / przekątna komórki;
δ=P95 fotograficznych średnich rozbieżności 24 punktów z dokładnie tą samą
normalizacją co normalized_error. Zamrozić przed B/REG. u>0,02 lub δ>0,002
wymaga poprawy etykiet, nie zwiększania tolerancji; to reguły produktu.

Sprawdzić oracle: geometria człowieka i produkcyjny VirtualCellRenderer
z przypiętym classifier/padding snapshot. Jeśli pełna widoczna zawartość
jest przycinana nawet przez oracle, render_contract_blocked: brak kwalifikacji
automatu, żadnego cichego zmieniania cropów klasyfikatora; ręczne propozycje
i niezależne eksperymenty geometrii pozostają możliwe.

TRAIN/A/B/REG korzystają z istniejącego ledger, ochrony kopii, sesji, buforów,
rodowodu i historycznego użycia. Świeży REG: utrwalone losowanie seed20261108
przed treningiem, najpierw sprawdzenie dopuszczalności staging691; jeśli brak,
nowe źródła. Wykluczyć diagnostycznie oglądane źródła, w tym462205. Nie
deklarować niezależności nagrania. ≥5 pełnych opisanych zdjęć REG per wymagana
gra; partial tylko uzupełnia. Unknown etykiety >10% wszystkich slotów roli
oznacza not_evaluable. Mianownik instancji określa wyłącznie etykieta.

## T3 — Ocena końcowych wycinków (TASK-1166)

Użyć produkcyjnego renderer/padding/classifier snapshot. Zachowana:
dylatowana o u zawartość mieści się w rzeczywistym wsparciu właściwego cropu.
Przycięta: nawet erodowana o u się nie mieści. Inaczej borderline, bez sukcesu.
Float64, epsilon1e-6 piksela źródła wyłącznie numeryczny. Brak wyniku=błąd,
nie unknown. Stany zasłonięte/poza obrazem raportowane osobno, bez auto-PASS.

Macierz pokrycia etykiet przez cropy określa wrong-cell: większe pokrycie
w obcym wycinku, remis=niejednoznaczność. Pełne przejęcie obcego symbolu
też blokuje. Jednoznaczne dopasowanie plansz pozostaje. Skala pogorszenia
instancji: preserved→borderline→clipped/missing, bez kompensacji inną poprawą.

Nowa funkcja i ruleVersion; stare reguły/raporty zachowane. Każda wymagana
gra i A/REG: bez nowych pogorszeń zawartości/wrong-cell/niejednoznaczności,
bez spadku recall/board_correct/full-photo correctness, bez wzrostu FP/duplikatów
na pełnych zdjęciach, NME_k≤NME_b+δ. Bieżąca gra REG: ≥1 dodatkowa użyteczna
plansza (board_correct, 15visible/preserved, bez wrong-cell/ambiguity).
Odrzucenie wszystkiego nie zalicza poprawy. Bazą b/treningu/banku błędów
jest3ed60010-7c3e-5c3b-91aa-4e03eb9bfa5e. Kandydat9992a316-1b08-554e-aa3d-ec05addffb89
pozostaje wyłącznie komparatorem informacyjnym, historycznie REVISE.

## T4 — Kontrolowane warianty uczenia (TASK-1167)

Istniejący trener; detektor tylko pełne zdjęcia, partial nie jest tłem.
Bank błędów tylko TRAIN i zamrożona baza z potwierdzonym brakiem użycia tych
źródeł w rodowodzie. SHA banku i dowody; niedobór uzupełnić nowym TRAIN,
bez A/REG i bez niebudżetowanego out-of-fold.

Maksymalnie R0: naprawione cele/maski/visibility, obecne wejścia;
R1: R0 z nowym batchnorm_stats (statystyki zamrożone, affine uczone);
R2: R1 plus równo screen768/1280 i board320×192/.15 lub480×288/.30;
R3: R2 plus pomocnicze obwiednie i lokalna visibility15, wyłącznie jeśli R2
nie przejdzie bramki A i są zatwierdzone etykiety. Stary batchnorm bez zmian.
R3 bez klas symboli i bez heurystycznego przesuwania siatki. Nie rozszerzać
listy ramion po wynikach. Heavy-occlusion wspólne dotychczasowe ustawienia,
naprawić targety; do3 losowań poprawnego jittera, potem jawny skip, nie GT-fallback.

Ta sama baza/dane/seed, plan1200kroków/ramię, ocena co200 i końcowa.
Czas:1500s R0/R1,2100s R2/R3, suma7200s z walidacją. Preflight wykonalności
przed GPU; niedobór wymaga decyzji przed startem. Nieukończone ramię nie
kwalifikuje się. R3 wymaga pełnej rezerwy. Wznowienie zachowuje checkpoint,
plan, dotychczasowe zużycie i receipts; utrata odpowiedzi nie duplikuje prób.

Wybór wyłącznie A: mniej nowych clipped/borderline/wrong-cell, więcej użytecznych
zdjęć, więcej użytecznych plansz, mniejszy NME, prostsze ramię, wcześniejszy krok.
Równa waga gier, bramka per gra. B tylko kalibracja zamrożonego routingu;
REG raz po zamrożeniu, nie wraca do strojenia.

Rescue-v2: najwyżej jedna redetekcja1280 zdjęcia (wspólna dla jego plansz),
potem jeden crop480×288/.30 podejrzanej planszy. Ambiguity→człowiek, bez
dodatkowych paths; R0/R1 bez wytrenowanego wariantu nie mają rescue.
Progi osobne per wariant i routing, bez przenoszenia peak między rozdzielczościami.
Automat wymaga w B i REG min30 rzeczywistych dobrych i30 błędnych przypadków
z różnych źródeł po kopiach dla gry/używanej ścieżki. Skład próbki zamknięty
przed wyborem zwycięzcy; liczby na wynikach zamrożonego routingu. Niedobór
oznacza brak automatu. Nowa partia musi być odrębnie zamknięta, bez dobierania
po wynikach. Osobno losowa próba częstości i trudna próba odporności.

## T5 — Interfejs, HTML i odbiór (TASK-1168)

Istniejący kontrakt rozszerzyć pionowo: backend/OpenAPI/SDK/wrapper/requesttest.
Panel odróżnia gotowość treningu i automatu, propozycję/człowieka/automat,
powody zatrzymania, wariant wejścia i zakres sprawdzonych gier. HTML: oryginał,
rzeczywiste wejście, baza/kandydat i15 produkcyjnych cropów. Podgląd użytkownika
nie udaje wejścia sieci. Bez nadpisania ręcznych geometrii/symboli.

Testy: prawdziwy ONNX i24/15, górny rząd, wrong-cell/remisy/sąsiad,
perspektywa/zasłony/brzegi, partial/unknown, wersje/aktualność, restart/utrata
odpowiedzi/budżet, PostgreSQL/API/Admin/Reviewer, lint/typecheck/build/docs/map.
Każdy task: własny audyt, Outcome, commit i task-close. Wymaganie→test:
T0→nowy proces/worktree i błędna sesja; T1→realne wyjście/loss/maski;
T2→ledger/blind labels/oracle; T3→instancje i monotoniczna bramka;
T4→checkpoint/rescue/wznowienie; T5→kontrakt i cały przepływ.

## Ograniczenia

Zdjęcia wystarczają. Plansze3×5, inne układy jawnie odrzucane. Zgodna nowa
gra dostaje propozycje, nie fikcyjny dowód jakości. Augmentacja kolorów nie
zastępuje innej rzeczywistej gry. Niedobór kalibracji pozwala używać propozycji
z ręczną akceptacją. OCR/progi kolorów/przepisanie na135symboli nie są podstawą.
Obecny default do pozytywnego odbioru;309istniejących i ręczne korekty zachowane.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T0 / TASK-1163 | gpt-6.1-sol | high | Spójny mechanizm audytu i diagnostyki | Claude Code claude-opus-5-5/high |
| T1 / TASK-1164 | gpt-6-astra | high | Kontrakt treningu, eksportu i oceny | Claude Code claude-opus-5-5/high |
| T2 / TASK-1165 | gpt-6-astra | high | Trwałe etykiety i ochrona źródeł | Claude Code claude-opus-5-5/high |
| T3 / TASK-1166 | gpt-6-astra | high | Ocena i bramka bez regresji | Claude Code claude-opus-5-5/high |
| T4 / TASK-1167 | gpt-6-astra | high | Ograniczony trening i budżet | Claude Code claude-opus-5-5/high |
| T5 / TASK-1168 | gpt-6.1-sol | high | Kontrakt UI i końcowy odbiór | Claude Code claude-opus-5-5/high |
