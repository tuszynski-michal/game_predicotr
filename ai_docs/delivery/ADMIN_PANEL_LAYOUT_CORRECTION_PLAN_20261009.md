---
title: Czytelny panel punktu — korekta układu
status: proposed
last_updated: 2026-10-09
---

# Czytelny panel punktu — korekta układu

## Stan i zakres zlecenia

Operator poprosił o plan poprawy czytelności i omówienie go z Claude Code.
Najnowsze doprecyzowanie: **tylko punkt otwiera osobny widok**. Maszyna jest
wyborem na tym widoku, a jej kafelek pozostaje widoczny i podświetlony.
Ta reguła zastępuje zagnieżdżanie maszyny opisane w D-538; pozostałe kontrakty
zapisu i usuwania pozostają. Plan jest propozycją wykonania, a nie zgodą na
uruchomienie usług lub operacje na danych operatora.

Stan kodu: v1.7.291, `1332c910`. `ManagementWorkspace` ukrywa listę maszyn,
gdy `machine` istnieje (`selected && !machine`), a następnie renderuje osobną
sekcję gier i stawek. Kafelki maszyn nie otrzymują stanu wyboru. To przyczyna
rozbieżności, nie brak koloru w CSS. Padding i ikony poprawiono w TASK-0946.

Operator potwierdził, że zapis już działa. W kodzie nadal potwierdzono ryzyko
odzyskiwania po błędzie: komunikat i retry są za modalem, a `retryAvailable`
blokuje także jego Anuluj. Nie znamy przyczyny wcześniejszego błędu transportu.
Odczyt lokalnego API pokazał dwa archiwalne punkty i schemat0153; nie wykonano
zapisu, migracji ani restartu. Niedokończone, niezweryfikowane zmiany formularza
z poprzedniego podejścia odłożono do ignorowanego patcha; nie są implementacją
tego planu i nie należy ich nakładać bez ponownego sprawdzenia.

Potwierdzona dodatkowa rozbieżność: `ManagementCards` nie renderuje
`slot.pinnedPoints`. `ManagementGameWorkspace` pokazuje `ApproximateWinPinRows`
wyłącznie przy `selectedStake && !editor`. Dlatego samo wyświetlenie maszyny
ani zapis z nadal otwartym szkicem nie zapewnia oczekiwanego podglądu. Dane
są w istniejącym summary; to błąd miejsca prezentacji, nie dowód utraty pinów.

## Docelowy widok

1. **Lista punktów:** małe kafelki; kliknięcie otwiera wybrany punkt.
2. **Widok punktu:** jeden nagłówek z nazwą i przyciskiem „Cofnij do punktów”,
   poniżej „Maszyny” oraz „Dodaj maszynę”, następnie siatka maszyn.
3. **Wybór maszyny:** lista maszyn pozostaje. Wybrany kafelek ma obramowanie,
   delikatne tło i `aria-pressed`. Poniżej tej samej listy pojawiają się nazwa
   maszyny, wybór gry i stawki. Przełączenie maszyny podmienia tylko ten obszar.
   **Każda zapisana stawka od razu pokazuje wszystkie zapisane punkty wykresu,
   bez klikania stawki, otwierania wykresu ani pełnego wyniku.**
4. **Wybór stawki:** podświetla stawkę i rozwija wspólną wyszukiwarkę pod nią.
   Lista maszyn, stawki i ich zapisane podsumowania pozostają widoczne także
   podczas pracy nad szkicem; wynik, wykres i dziennik są rozwijane osobno.

Nie powstaje ekran maszyny ani przycisk „Cofnij do maszyn”. Na liście punktów
przycisk powrotu nazywa się „Punkty”; w punkcie „Cofnij do punktów”. To jedna
akcja w nagłówku, bez dwóch przycisków prowadzących w to samo miejsce.

## Reguły czytelności i miejsca

- Jedna, stała kolejność sekcji: punkt → maszyny → gra i stawki → układ.
  Nazwa wybranej maszyny jest widoczna nad jej grą i stawkami.
- Kafelki punktów i maszyn nadal mają maksymalnie320px i siatkę4/3/2/1 według
  szerokości kontenera1000/750/500px. Minimum16px odstępu treści od krawędzi,
  12px między kafelkami i24px między głównymi sekcjami. Ikony mają cele44px.
- Kafelki maszyn pokazują nazwę i liczbę gier. Edycja/usunięcie pozostają
  przyciskami rodzeństwa; kliknięcie ich nie wybiera maszyny.
- Przy wielu maszynach lista pozostaje dostępna w oznaczonym obszarze z własnym
  przewijaniem, wysokości `min(288px, 40dvh)`. Dzięki temu40 maszyn nie wypycha
  stawek daleko w dół. To założenie układu do odbioru na390/1440/1920px;
  żadna maszyna nie znika z listy. Lista ma nazwany `role="region"`, fokus
  klawiatury i `overscroll-behavior: contain`. Kliknięcie pozostawia jej scroll
  i fokus. Przy odtworzeniu z URL/reload zmienić wyłącznie `scrollTop` listy,
  wyliczając położenie kafelka względem jej krawędzi; nie używać metody
  przewijającej wszystkie przodki. `window.scrollY` pozostaje bez zmian.
- Karty stawek mają ten sam układ: kwota i „Zapisany układ”/„Brak układu” po
  lewej, miniatura symboli po prawej. Zachować symbole20px i ich fallback;
  przy wąskiej karcie miniatura może przejść niżej. Wysokość wynika z treści;
  nie wymuszać pustych, dużych kart ani ucinania komunikatów.
- Pod nagłówkiem każdej zapisanej stawki wyświetlić0–6 zapisanych wierszy:
  **Spin | Wkład | Wygrana netto | Na maszynie**. Wszystkie wybrane piny są
  widoczne, bez „Pokaż więcej”. Wiersze mają czytelny, gęsty układ; karta może
  być wyższa, gdy zawiera więcej punktów. Dostępności danych nie zastępować
  sztucznym ograniczeniem wysokości. Bez pinów: „Nie wybrano punktów na wykresie”.
- Kwoty podawać w złotych przez istniejący `managementAmount`, używając
  `stakeGrosze` i zapisanego bazowego `spinCost`. Brak danych do przeliczenia
  oznacza jawnie opisane kredyty lub „—”, nigdy wymyśloną kwotę w złotych.
  `requiredStakeCredits` jest wymaganym kapitałem, nie sumą kosztów spinów;
  `balanceCredits` jest wygraną netto, a `machineCashCredits` kwotą na maszynie.
  Zachować znaki zysku/straty i spin zero. `available=false` wyświetla
  „niedostępny”; brak nullable metryki wyświetla „—”. To zapisane prognozy
  dla danych spinów, nie deklaracja przyszłych gwarantowanych wygranych.
- Gra pozostaje opisanym selektorem, zamiast dodawania kolejnej szerokiej
  siatki. Na telefonie elementy układają się pionowo, bez poziomego overflow.
- Dodawanie/edycja zachowuje istniejący modal i atomowy zapis nazwy oraz gier.
  Komunikaty są przy działaniu, którego dotyczą; szczegóły techniczne nie
  trafiają do podstawowego widoku.

## Zapisane piny bez dodatkowego kliknięcia

Źródło podglądu: `ManagementStakeResponse.pinnedPoints` wszystkich sześciu stawek
wybranej maszyny i gry. Nie pobierać sześciu pełnych wyników i nie wyliczać pinów
ponownie na froncie. Użyć istniejącego `ApproximateWinPinRows` z opcjonalnym
wariantem kompaktowym/formatowaniem albo jego obecnych mechanizmów prezentacji;
domyślny tabelaryczny widok w kredytach i inni konsumenci pozostają bez zmian.
Nowy wariant wewnątrz klikalnej karty musi zachować poprawny HTML i dostępność,
bez zagnieżdżonych przycisków czy niepoprawnej tabeli wewnątrz button.

Po udanym Save natychmiast odświeżyć summary konkretnej stawki. Podgląd nie
zależy od `selectedStake`, zamknięcia edytora, wykresu ani pełnego wyniku.
Nowy/reset i zmiana pinów w szkicu pozostawiają ostatnie zapisane wiersze aż do
potwierdzonego zapisu; nie prezentować szkicu jako już zapisanego wyniku.
Po powrocie do punktu/maszyny i reload podsumowania odtwarzają się z serwera.
Zmiana gry/maszyny nie może zachować wierszy poprzedniego zakresu. Podczas
sprawdzania/nieaktualności zachować opis stanu; nie sugerować aktualnej wygranej,
jeśli istniejący kontrakt oznacza wynik jako wymagający sprawdzenia.

## Zachowanie i ochrona danych

D-539 zapisano w Decision Log przed implementacją: tylko nawigacyjna część
D-538 jest zastąpiona. Maszyna jest stanem wyboru, nie poziomem nawigacji.
Otwarcie punktu i Home używają `pushState`; wybór maszyny, gry i stawki używa
`replaceState`. Back wraca z punktu do wcześniejszego widoku, bez historii
kolejnych wyborów maszyn/stawek. Po bezpośrednim linku nie tworzymy sztucznej
historii; Back zachowuje standardowe zachowanie przeglądarki i guard szkicu.
Fokus po otwarciu punktu trafia na jego nagłówek; po Home na dawny kafelek punktu
(jeśli jeszcze istnieje). Wybór maszyny pozostawia fokus na jej przycisku,
`aria-pressed` określa wybór i krótki `aria-live="polite"` ogłasza nazwę.

Zachować istniejące UUID
w URL (`mpPoint`, `mpMachine`, `mpGame`, `mpStake`) i odzyskiwanie po odświeżeniu.
Bez wyboru maszyny pokazać krótką wskazówkę „Wybierz maszynę”. Zapisana preferencja
gry danej maszyny pozostaje. Zmiana punktu czyści wybór maszyny, gry i stawki;
zmiana maszyny czyści stawkę i wybiera jej zachowaną/dopuszczalną grę.

Brudny szkic wymaga obecnego potwierdzenia przed zmianą punktu, maszyny, gry,
Home lub historią przeglądarki. Odmowa pozostawia kafelek, URL i szkic bez zmian.
Nie wybierać potajemnie pierwszego wyniku wyszukiwania. Renderować tylko jeden
workspace wybranej maszyny/gry, bez ładowania wyników pozostałych maszyn.

Po utracie odpowiedzi/5xx zachować dokładny UUID i treść operacji. W modalu
pokazać błąd, „Ponów ten sam zapis” i możliwość zamknięcia po zakończeniu żądania.
Nie odblokowywać nowego zapisu przez usunięcie niepewnego receipt. Po zamknięciu
odzyskiwanie pozostaje dostępne na widoku punktu. Po jednoznacznym odrzuceniu
4xx formularz zachowuje pola i stosuje dotychczasowe reguły błędu/rewizji.
Gdy odrzucone usunięcie zamknie dialog, jego błąd jest widoczny na stronie
punktu; test obejmuje409/422 oraz odrębne zachowanie401/403/429.

Historyczne archiwalne kafelki powinny dawać dostęp do swoich zapisów i usunięcia.
Propozycja wynikająca ze zgłoszenia operatora: umożliwić też jawne „Przywróć”
wyłącznie dla tych dawnych danych przez istniejące `archived=false`; bez nowej
akcji archiwizacji. Najpierw przywrócić punkt, potem jego archiwalną maszynę.
Nie zmieniać przypisań, zapisów ani dzieci automatycznie. To rozszerzenie czeka
na akceptację tego planu; D-538 obecnie nie przewiduje przywracania.
Potwierdzony transport to PUT, nie PATCH: router `api/management.py` przekazuje
`ManagementPointCommand`/`ManagementMachineCommand`, a repository `point`/`machine`
zapisuje `command.archived`. Ostatnie sprawdzenie kontraktu i regresji przed
implementacją0948 nadal jest wymagane; nie potrzeba nowego endpointu.
Jeśli wyjątek przywracania nie zostanie zaakceptowany,0948 realizuje odzyskiwanie
modala i odczyt/usunięcie historycznych danych, bez przywracania.

## Kolejność zadań i odbiór

| Zadanie | Rezultat | Dowód odbioru |
|---|---|---|
| TASK-0947 | Jedna strona punktu, stale dostępna lista maszyn, podświetlenie wyboru, czytelne sekcje, kompaktowe stawki i wszystkie zapisane piny bez klikania | Kliknięcie A/B zachowuje tę samą listę, zmienia jeden workspace i stan wyboru; dirty cancel/URL/reload, podgląd po Save bez wybrania stawki i pomiar Chromium390×844 |
| TASK-0948 | Czytelne odzyskiwanie formularza i dostęp do historycznych kafelków | Błąd/retry/close w dialogu, ten sam UUID po remount, archiwalne dane bez utraty przypisań |
| TASK-0949 | Odbiór rzeczywistego renderowania obu hostów i przekazanie operatorowi | Zrzuty390/1440/1920px,40 maszyn,6 stawek, długie nazwy, fokus/scroll/overflow i oddzielny status testu na żywo |

Szczegóły wykonania są w plikach tasków0947–0949. Najpierw testy zmienionego
przepływu, potem lint/typecheck. Nie powtarzać wszystkich historycznych audytów.
Jedna ograniczona runda Claude na task i jedna runda poprawek; istotna zmiana
P0/P1 podlega zasadom ponownego review z AGENTS.md. Wygląd oceniać przez zrzuty
i mierzone położenie elementów; obecność tekstu w DOM nie dowodzi czytelności.
Już przed zamknięciem0947 uruchomić ograniczony przypadek Chromium390×844:
40 maszyn, wybór35., lista≤`min(288px,40dvh)`, brak zmiany scrollY i overflow,
wyraźne różnice computed tła i obramowania wybranego kafelka, nagłówek wyników
nie dalej niż1,5 wysokości viewportu od początku widoku.0949 poszerza odbiór,
ale nie odkłada podstawowej weryfikacji wyglądu do końca planu.
Obowiązkowe przypadki pinów już w0947: brak wybranej stawki; dwie zapisane
stawki z różnymi pinami; Save przy otwartym szkicu; reload; zmiana maszyny/gry;
0/1/6 pinów, spin0, straty, niedostępny punkt i brak starszej nullable metryki.
Test ma sprawdzać wiersze widoczne przy właściwej karcie, nie tylko tekst w DOM.
0949 obejmuje w obu hostach wąskie karty z sześcioma pinami i różną liczbą
zapisanych stawek, bez ucinania danych ani mylenia stawek.

## Granice weryfikacji i koszt

Potwierdzone dotąd: kod ukrywa maszyny; poprawiony padding ma Chromium10/10;
API GET i odczyt wersji bazy działają; operator potwierdził działający zapis.
To nie jest odbiór nowego układu. Planowane testy nie są wynikami wykonania.

Odbiór lokalny korzysta z prawdziwych komponentów z atrapą transportu i testów
integracyjnych na jednorazowej bazie. Test na danych operatora oraz restart
usług pozostają osobnym krokiem operatora. Nie deklarować „gotowe do testowania
na żywo” wyłącznie na podstawie statycznego audytu i atrap.

Zakres wyłączony: nowe API, migracje, algorytmy wypłat, kopia wyszukiwarki,
globalny redesign Admina, produkcyjne kasowanie, push, merge i lifecycle usług.
Nie wznawiać niedokończonego patcha ani implementacji podczas przeglądu planu.
Przed przyszłą implementacją oszacować koszt całego zakresu; jeśli będzie
długi/złożony, uzyskać wymaganą zgodę na czas i koszt zgodnie z AGENTS.md.

## Przegląd Claude Code i zamknięcie uwag planu

Przegląd zlecony: claude-opus-5-5 / medium, pojedyncza runda na planie i krótkich
fragmentach kodu, bez narzędzi i zmian plików. [Raport](../quality/ADMIN_PANEL_LAYOUT_PLAN_REVIEW_CLAUDE_20261009.md)
zawiera pierwotny REVISE oraz odpowiedź autora z zamknięciem uwag. Trzy P1
uwzględniono: przewijanie tylko listy, jednoznaczna historia wyboru oraz pomiar
Chromium już w0947. Doprecyzowano fokus, region klawiatury i4xx usuwania.
Stan ten oznacza poprawiony plan po konsultacji, nie drugi werdykt PASS ani
odbiór działającego UI. Filtr nazw maszyn pozostaje poza bieżącym zakresem;
nie jest konieczny do poprawy błędnego modelu wyboru.

Doprecyzowanie operatora po tym przeglądzie: zapisane piny mają być widoczne
przy wszystkich zapisanych stawkach bez wyboru stawki. Włączono je do0947 i0949
oraz wymagań/D-539. Nie uruchomiono nowej rundy Claude dla tego dopisku; przyszły
ograniczony audyt implementacji0947 musi objąć także tę zmianę.

## Przypisanie modeli do zadań

Modele Codex i poziomy potwierdzone w narzędziach tej sesji; Claude przez lokalne
CLI. Dostępność konkretnego modelu sprawdzić ponownie przy wykonywaniu taska.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0947 | gpt-6.1-sol | medium | Wspólne React UI, selection, URL i ochrona szkicu; eskalacja przy zmianie kontraktu | claude-opus-5-5 / medium, jeden przegląd ograniczonego diffu |
| TASK-0948 | gpt-6.1-sol | medium | Niepewny zapis i zachowanie UUID wymagają sprawdzenia regresji; bez nowego backendu | claude-opus-5-5 / medium, jeden przegląd ograniczonego diffu |
| TASK-0949 | gpt-6-luna | medium | Konkretne scenariusze i istniejący fixture ograniczają analizę; eskalacja przy niedostatecznej weryfikacji | claude-opus-5-5 / medium, końcowy przegląd dowodów i otwartych ryzyk |
