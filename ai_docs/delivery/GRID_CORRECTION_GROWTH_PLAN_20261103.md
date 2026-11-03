---
title: Przyrostowe uczenie siatek i aktualność oceny
status: accepted
last_updated: 2026-11-03
---

# Przyrostowe uczenie siatek i aktualność oceny

Operator 2026-11-03 zlecił cały zakres, audyt Opus 5.5 i zaakceptował dodatkowy
koszt pracy szacowanej na 1–2 godziny. Nie obejmuje to migracji bazy operatora,
restartu usług, rzeczywistego treningu, zastosowania modelu ani merge/push.

## Stan obecny i rezultat

W odczycie Mumie A2 zapisano 196 zatwierdzonych plansz wobec 117 wcześniej.
TRAIN pozostaje 77, VALIDATION 17, REGRESSION rośnie z 20 do 99. V1 utrwala role
całej populacji importu, także zdjęć bez etykiet. Te rezerwacje blokują przyrost
treningu. Zakończona ocena była stale po nowych notices; pełne sprawdzenie
aktualności przeszło bez błędów, a podgląd zastosowania ma canApply=true.

Cel: nowe korekty kwalifikujących się zdjęć zwiększają TRAIN, osobne kontrole
i bufory pozostają chronione. Pula zdjęć oczekujących na korektę może dostarczyć
ograniczoną, jawną rezerwę przyszłych testów. Nieopisane zdjęcie nie jest wynikiem
testu. Panel pokazuje rzeczywisty podział i pozwala sprawdzić aktualność oceny.

## Reguły danych

- Nie zmieniać istniejących kohort, snapshotów, raportów ani użytych etykiet.
  Źródłem prawdy pozostaje rejestr D-554; nie dodawać drugiego rejestru ról.
- Faktycznie użyte TRAIN/VALIDATION/REGRESSION, jawne holdouty, ancestor use,
  sesje, kopie i istniejące bufory pozostają chronione. Nie przenosić użytych
  kontroli do TRAIN. Wszystkie plansze jednego zdjęcia mają jedną rolę.
- Rozróżnić stare rezerwacje V1 bez użycia od rzeczywistego użycia. Dopuszczalne
  zwolnienie dotyczy wyłącznie rezerwacji metadanych bez żadnego użycia lub
  innej ochrony w całym komponencie kopii/sesji. Zwolnienie ma trwały,
  audytowalny zapis; nie usuwa ani nie aktualizuje historycznego użycia.
- Nowa wersjonowana polityka podziału nie rezerwuje całych nieopisanych ogonów
  importu do kontroli. Chroni istniejące obszary kontroli i bufory, pozwala na
  dodatkowe bloki TRAIN poza nimi. Granice wynikają wyłącznie z atestów jak D-577;
  nieznana kolejność nadal oznacza nierozdzielny import.
- Przy istniejących wystarczających kontrolach dodatkową rezerwę wybierać tylko
  spośród dostępnych zdjęć oczekujących na korektę, maksymalnie 5 zdjęć na rolę
  kontrolną, z zachowaniem grup i buforów. Brak bezpiecznego miejsca nie blokuje
  użycia wystarczających istniejących kontroli, ale daje jawny brak rezerwy.
  Jeśli nie ma jeszcze kontroli spełniających minima, ich kompletacja zachowuje
  dotychczasowe minima 15 plansz/5 zdjęć; nieopisane rezerwy ich nie spełniają.
- TRAIN zachowuje minimum 30 plansz/10 zdjęć, bufory minimum 10 kolejnych zdjęć
  wszystkich źródeł pomiędzy różnymi rolami. Bufor nie dowodzi niezależności sesji.
- Przyrost nie jest obietnicą użycia każdej poprawki: zdjęcie kontrolne, kopia,
  bufor, zmieniona etykieta lub niepewne pochodzenie mają jawny powód wyłączenia.
- Podgląd wyłącznie czyta. Zwolnienia/przydziały utrwalają się atomowo podczas
  freeze, z kontrolą rewizji i tożsamości, blokadą konkurencji oraz idempotencją.
  Stare dowody aktualności pozostają sprawdzalne według historycznego użycia;
  nowa polityka nie nadaje im fikcyjnego zakresu ani nowych wyników jakości.

## TASK-1139 — Przyrostowy podział i prawdziwe liczniki

Wykonawca najpierw zapisze ograniczony preflight Mumie A2: rzeczywiście użyte
role, rezerwacje bez użycia, obszary i bufory oraz policzone możliwości wzrostu.
Nie obiecywać przesunięcia wszystkich 79 nowych korekt. Zmiana decyzji D-577
wymaga nowej decyzji z jawnym zakresem wyjątku, wynikającej z polecenia operatora.

Rozszerzyć istniejący rejestr capability migracją Alembic, politykę/snapshot
i adapter podziału. Nową semantykę stosować jawnie; stare formaty zachowują
interpretację i działające dowody. Przy przekroczeniu limitu solvera blokada,
bez cichego wycinania danych. Zachować kontrolę znanych kopii między grami.

Rozszerzyć obecny ready/preview backend → OpenAPI → wygenerowany klient →
wrapper → test żądania. Liczniki mają rozdzielać zatwierdzone ogółem, dostępne
do TRAIN, już użyte w nauce, nowe do nauki, faktyczne kontrole, rezerwę bez
etykiet, bufory i wykluczenia. Wszystkie liczniki muszą mieć tę samą jednostkę,
deduplikację i pochodzić z tego samego podziału; wykluczenia z powodami.

Testy: przyrost na wcześniej nieużytej rezerwacji, zakaz użytych kontroli,
stare dowody po nowym freeze, kopie/sesje, 10 zdjęć bufora także bez etykiet,
brak kolejności, atomowość i porzucony preview, replay/restart, rzeczywiste
PostgreSQL capability i izolacja uprawnień, minima i niepełne kontrole.

## TASK-1140 — Czytelny panel i jawna aktualność oceny

Zależność: kontrakt TASK-1139. W istniejącym panelu pokazać nowe liczniki
z prostymi nazwami i objaśnieniem powodów. Nie mylić gotowości kolejnego
treningu ze statystyką zakończonego przebiegu. Pokazać brak potrzebnych danych
testowych i wskazówkę korekty zarezerwowanych zdjęć albo dodania nowego importu.

Wykorzystać istniejące verifyGridModelEvaluationCurrentness. GET panelu nadal
wyłącznie czyta. Jawny przycisk sprawdza aktualność, pokazuje loading, wynik
i błędy, następnie odczytuje ocenę i podgląd zastosowania. Powtórne kliknięcie,
zmiana gry/przebiegu, stara odpowiedź i utracona odpowiedź nie mogą pozostawić
fałszywego PASS. Zmienione/wycofane etykiety nadal blokują zastosowanie.
Checkbox nie omija blokad backendu. Sprawdzenie aktualności nie uruchamia
treningu i nie publikuje/aktywuje modelu.

Testy interakcji: wzrost licznika TRAIN, osobna rezerwa bez etykiet, kontrola
nie zwiększa TRAIN, stale → sprawdzenie → świeży preview, faktycznie zmieniona
etykieta → blokada, błędy i ponowienie, loading/double click, zmiana wyboru
w trakcie odczytu, brak automatycznych POST przy otwarciu. Regresje TASK-1138.

## Odbiór i ograniczenia

Każdy task: testy zmienionego pionu, lint/typecheck, niezbędne testy PostgreSQL,
Admin build przy zmianie panelu, docs:check i code-map:check, raport Opus
5.5/high przed osobnym commitem, jedna runda poprawek. P0/P1 blokują commit.
task-close zapisuje Outcome, wersję i hash. Na końcu ograniczony odczyt danych
operatora potwierdza możliwości nowej polityki bez jej utrwalania lub treningu.

Nie wykonujemy migracji operatora, restartu usług, uczenia GPU ani zastosowania
modelu bez osobnej zgody. Nie mierzymy jakości nieopisanych siatek. Nowe dane
mogą wymagać nowego importu, jeżeli wszystkie dostępne źródła są chronione.

## Wynik implementacji

TASK-1139 i TASK-1140 wykonano z osobnymi audytami Opus 5.5/high. Każda pierwsza
runda wykazała P1; po jednej rundzie poprawek oba przeglądy R2 mają PASS.
Raporty R1 i R2 oraz ograniczenia testów zapisano w `ai_docs/quality/`.
Testy PostgreSQL obejmują atomowy freeze, ochrony, guarded downgrade i nowy proces;
panel ma 40 własnych i 74 szersze testy interakcji, kontrolę typów i build PASS.

Końcowa symulacja READ ONLY: TRAIN146 (77 zapisanych +69 nowych), VALIDATION17,
REGRESSION21, 12 zatwierdzonych plansz wykluczonych przez bufory. Nie ma obecnie
bezpiecznej dodatkowej rezerwy pending. Dane nie zostały utrwalone nową polityką.
Migracja operatora 0172, wdrożenie i rzeczywiste uczenie pozostają osobnymi
operacjami; sam kod nie zmienia modelu domyślnego ani historycznych korekt.

Preflight integracji wykrył równoległy numer 0172 w niescalonej gałęzi
`codex/777a2-readability-replacement`: `0172_symbol_readability` od 0169.
Nasza `0172_grid_correction_growth` jest liniową następczynią aktualnej 0171.
Wymagane jest potwierdzenie kolejności wdrożenia przez operatora; numerów nie
zmieniono automatycznie. Wdrożenie tej gałęzi jako pierwszej pozostawia późniejszą
koordynację numeru i grafu Alembic po stronie integracji gałęzi symboli.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1139 — Podział i liczniki | gpt-6-astra | high | Zmiana trwałych dowodów, polityki danych i zgodności historycznych ocen | Obowiązkowy Claude Code claude-opus-5-5/high |
| TASK-1140 — Panel i aktualność | gpt-6.1-sol | high | Istniejący kontrakt, prowadzony interfejs i ochrona odpowiedzi asynchronicznych | Obowiązkowy Claude Code claude-opus-5-5/high |
