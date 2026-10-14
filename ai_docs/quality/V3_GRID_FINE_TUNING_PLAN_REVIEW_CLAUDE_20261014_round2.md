---
title: Przegląd rewizji 2 planu doszkalania siatek V3 przez Claude Code
status: active
last_updated: 2026-10-14
---

# Przegląd rewizji 2 planu „Doszkalanie siatek V3 z korekt w aplikacji”

Audytor: Claude Code, claude-fable-5-1 / medium.
Zakres: `ai_docs/delivery/V3_GRID_FINE_TUNING_EXECUTION_PLAN_20261014.md`
(rewizja 2, 929 linii, niezacommitowana w `D:\game_predicotr`, main `v1.7.356`),
`quality/V3_GRID_FINE_TUNING_PLAN_REMEDIATION_CODEX_20261014.md`, zmiany
`CURRENT_STATE.md`, `APP_V3_FUNCTIONAL_INVENTORY.md`, `tasks/0957-*.md`.
Przegląd statyczny; dodatkowo odczyt bazy operatora tylko do odczytu
(zliczenia w zakresie gry, transakcje cofnięte). Nie zmieniałem kodu, danych
ani usług. Runda pierwsza: `V3_GRID_FINE_TUNING_PLAN_REVIEW_CLAUDE_20261014.md`.

**Werdykt: REVISE, zakres wąski.** Pięć uwag P1 pierwszej rundy jest
zamkniętych rzetelnie i zgodnie z kodem. Pozostaje jedna nowa uwaga P1
wykryta przy weryfikacji definicji „niepewnej siatki”: w obecnej ścieżce
neural każda automatyczna siatka jest `uncertain` z konstrukcji, więc
zaplanowane ponowne rozpoznanie nie zmieni licznika, który operator widzi.
Plan musi nazwać mierzalny cel i rozstrzygnąć „akceptację silnika” dla
pewnych decyzji bramki. Po tej poprawce plan nadaje się do akceptacji bez
kolejnej rundy; wystarczy porównanie zmienionych sekcji.

## Zamknięcie uwag pierwszej rundy

| Uwaga | Stan | Weryfikacja |
| --- | --- | --- |
| P1-1 nowe gry | zamknięta | TASK-1004 obejmuje `GameCreate`, `gridModelVersionId`, join/fork, backfill z enumu w TASK-0994, globalny katalog `GET /admin/grid-models/catalog`, formularz i testy. Enum zostaje opisem formatu strony. |
| P1-2 stan danych i minimum | zamknięta | Liczby audytu wpisane i datowane; progi TRAIN 30/10, VALIDATION 15/5, REGRESSION 15/5, co najmniej trzy nagrania; preview `required/eligible/missing`; faza O z próbą 10 korekt. Progi oznaczone jako propozycja pilota. |
| P1-3 zakres ponownego rozpoznania | zamknięta w części | Histogram stanów z `classify_position` (istnieje: `domain/image_geometry_completeness.py:120`), domyślnie `uncertain`+`deferred`, pilot 100 zdjęć, szeroki zakres opt-in, guard admission w `application/jobs.py`. Pozostała część to nowa uwaga P1-6 poniżej. |
| P1-4 checkpoint na C | zamknięta | Rozmiar 106 729 511 B i SHA potwierdzone w pliku; checkpoint Mumii `f896da71…` istnieje w `attempt-3`. TASK-0994 kopiuje z receipt; TASK-0957 ma warunek ochrony katalogu. |
| P1-5 para wykonawca/audytor | zamknięta | Codex `gpt-6.1-sol` wykonuje, Claude Code `claude-fable-5-1` audytuje; 14 wierszy tabeli zgodnych z sekcjami `Recommended execution` (sprawdzone wyrywkowo: 0996, 0997, 0998, 1004). |
| P2-1 granulacja | zamknięta | 1002, 1003 wydzielone; szacunek 9–21 dni. |
| P2-2 GPU | zamknięta | Dzierżawa tylko dla runów siatek aplikacji; trener symboli na CPU bez zmian; okno operatora. |
| P2-3 archiwalna 777 | zamknięta | Odczyt aktywnego profilu klasycznego i historii. |
| P2-4 preset | zamknięta | TASK-1005 z raportów iteracji (443/666/728 kroków, 900,3 s); formuła z liczby targetów. |
| P2-5 `GAME_SECTIONS` | zamknięta | Potwierdzone w `admin-navigation-state.ts:15`. |

Nowy kierunek operatora (wspólna geometria Mumii/777, TASK-1006) jest opisany
spójnie: jeden kandydat od jednej bazy, równe wagi gier i nagrań, bramka osobno
dla każdej gry, dziedziczenie wyłączeń obu linii, wymagana decyzja rozszerzająca
D-527. Dane do niego są odległe (777a2: 0 korekt), co plan mówi wprost.

## Nowa uwaga P1

**P1-6 — „Niepewna siatka” jest stanem z konstrukcji ścieżki neural; plan nie
określa, jak ponowne rozpoznanie i doszkalanie zmienią to, co operator widzi.**

Fakty (kod i baza, 2026-10-14):

- `classify_position` daje `ok` tylko dla planszy `complete`, która ma
  ręczne zatwierdzenie albo `source_revision_accepted`
  (`image_geometry_completeness.py:131-139`). W przeciwnym razie `uncertain`.
- Ścieżka neural zapisuje każdą rewizję źródła ze statusem `needs_review`
  na stałe, także dla plansz z dyspozycją `automatic`
  (`images/neural_pending_geometry.py:150`, `images/pipeline_store.py:329-336`:
  `accepted` tylko dla `rolloutMode` klasycznego). Decyzja bramki
  `confident` (`geometry_core/gate.py`) nie jest nigdzie utrwalana.
- Baza: 777a2 ma 37 993 rewizje źródła, wszystkie `needs_review/auto/neural_grid_v1`;
  0 plansz na zaakceptowanej rewizji. Mumie: 54 914 `needs_review` i 44 `accepted/manual`.
  Stąd 37 990 zdjęć `geometry_incomplete` przy 341 564 planszach `complete`
  i 373 wierszach kolejki. D-541 nazwała już ten licznik „siatką
  niepotwierdzoną”, nie błędem cięcia, i wyłączyła go z kolejki.

Konsekwencje dla planu:

1. Nowa automatyczna rewizja V3 z TASK-0999 (tabela „Stan celu przy zapisie”:
   „nie tworzy human approval”) będzie znów `needs_review`, więc po ponownym
   rozpoznaniu wszystkich plansz licznik `uncertain` pozostanie 341 564.
   Operator nie zobaczy żadnej zmiany w stanie zdjęć ani w „Diagnostyce
   siatek zdjęć”; D-484 nadal będzie traktować każde zdjęcie 777a2 jako
   niekompletne.
2. Bramka jakości (TASK-0997) mierzy poprawę na kontrolnych etykietach,
   co jest właściwe, ale plan nie podaje, jaki wskaźnik operacyjny ma się
   poprawić w samej grze (np. odsetek pozycji `ok`, liczba zgłoszeń „Zła
   siatka”, liczba odroczeń), ani jak go odczytać przed i po.
3. Wymaganie operatora „sporo siatek jest niepewnych” nie jest w planie
   rozłożone na dwa różne zjawiska: siatki faktycznie błędne (mierzalne
   tylko etykietą lub zgłoszeniem) oraz siatki niepotwierdzone z konstrukcji.

Korekta (bez nowego taska, zmiana trzech sekcji i jednej decyzji):

- Sekcja „Stan danych”: dopisać powyższe liczby rewizji i zdanie, że
  `uncertain` w 777a2 obejmuje 100% automatycznych plansz niezależnie od
  jakości siatki.
- Sekcja „Ponowne rozpoznanie” i TASK-0999: rozstrzygnąć, czy pewna decyzja
  bramki nowej wersji (`confident`, wszystkie 24 węzły, pewny binding) może
  ustawić `source_revision_accepted` zgodnie z literą D-484 („zaakceptowana
  przez silnik bez zastrzeżeń”). Zalecam: tak, jako jawnie włączana opcja
  przebiegu z własnym kodem powodu i zapisem wersji bramki, domyślnie
  wyłączona w pilocie 100, bez zmiany historycznych rewizji i bez tworzenia
  human approval. Wymaga to decyzji przy akceptacji (D-541 wyłączyła
  „walidację gotowych siatek” z tamtego planu, nie na zawsze) oraz testów:
  `confident` → `ok`, `needs_review` → `uncertain`, cofnięcie wersji nie
  cofa akceptacji już zapisanych rewizji.
- TASK-0997/1003: dodać wskaźnik operacyjny przed/po dla gry: liczby
  pozycji `ok/uncertain/deferred`, zgłoszeń „Zła siatka” i odroczeń z
  powodami; raport operacji pokazuje różnicę. Bez tego operator nie potrafi
  odebrać efektu planu na swojej kolekcji.
- Jeżeli operator nie zgodzi się na akceptację silnika, plan ma to zapisać
  wprost: celem jest wyłącznie poprawa geometrii mierzona etykietami, a
  licznik „niepotwierdzonych” pozostaje bez zmian z założenia.

## Uwagi P2

**P2-6 — TASK-1000 zależy od TASK-1006.** Pełna sekcja Admina czeka na
eksperyment wspólnego modelu, który jest bramkowany danymi obu gier i może
nigdy nie przejść. Zależność 1000 powinna obejmować 0993–0999 i 1002–1005;
1006 ma tylko dostarczyć stan „kandydat wspólny: brak / odrzucony / zaliczony”,
który sekcja wyświetla, gdy istnieje.

**P2-7 — Etykietowanie może zacząć się dziś.** Faza O zaczyna się „po
TASK-0993”, ale obecny edytor zapisuje już dokładne 24 węzły z rewizją i
zatwierdzeniem; wyklucza je tylko akcja „Zamień na szkic z czterech
narożników”. Plan powinien dopuścić zbieranie korekt od razu z instrukcją
unikania tej akcji, co skraca ścieżkę krytyczną o cały etap A.

**P2-8 — Zatwierdzenie bez zmiany jako etykieta.** Plan definiuje etykietę
jako „aktualna zatwierdzona przez człowieka geometria”. Nie rozstrzyga, czy
zatwierdzenie niezmienionej propozycji modelu liczy się tak samo jak korekta.
Dla ról kontrolnych jest to pożądane (pełne zdjęcia 9/9 szybciej), dla TRAIN
grozi utrwaleniem błędów bazy. Zalecam: snapshot zapisuje `corrected` vs
`approved_unchanged` per plansza; TRAIN wymaga udziału korekt (np. co
najmniej połowa), preview pokazuje oba liczniki.

**P2-9 — Kopia checkpointów z C jest operacją na stacji operatora.** TASK-0994
opisuje kopię jako część zakresu kodu. Odczyt C przez agenta i zapis do
zarządzanego katalogu D wymagają jawnego kroku operatora albo zgody w
Outcome; testy taska używają fixture'ów. Dopisać to do „Dependencies”.

**P2-10 — Minimum kontrolne a pilot grid-only.** Pięć pełnych zdjęć w każdej
roli kontrolnej daje 90 plansz etykiet na 30 plansz TRAIN. Proporcja jest
poprawna dla D-483, ale przy pierwszym runie grid-only metryka kompletności
zdjęcia i tak nie może się poprawić (etap ekranu zamrożony). Plan powinien
powiedzieć, że dla grid-only bramka D-483 ma być „bez pogorszenia”, a
poprawa ścisła jest wymagana na NME/poprawności komórek.

## Potwierdzone fakty rewizji 2

- `admin-navigation-state.ts:15` eksportuje `GAME_SECTIONS`.
- `classify_position` i `classify_image` istnieją (`:120`, `:143`).
- Checkpoint 777 v2: 106 729 511 B; checkpoint Mumii `f896da71…` w `attempt-3`.
- Tabela modeli ma 14 wierszy w kolejności tasków, każdy z dokładnym modelem
  i poziomem; audyt z innej rodziny niż wykonawca.
- Zmiana TASK-0957 jest wyłącznie warunkiem ochrony, bez upoważnienia do
  usuwania.

## Proponowane testy dodatkowe (do P1-6)

- Rewizja `confident` z pełnymi węzłami i pewnym bindingiem przy włączonej
  akceptacji silnika → pozycja `ok`, zdjęcie `complete` przy 9/9.
- Ta sama rewizja przy wyłączonej opcji → `uncertain`; bez różnicy w cropach.
- Raport operacji podaje liczby pozycji przed/po i zgadza się z ponownym
  odczytem `classify_image`.
- Rollback wersji po przebiegu nie zmienia statusów rewizji zapisanych w
  przebiegu; nowe joby używają wcześniejszej wersji.

Przegląd statyczny, bez zmian w planie i kodzie. Jedyny zapis to ten raport.

## Uzupełnienie po odpowiedzi operatora (2026-10-14)

Operator potwierdził, że „sporo niepewnych siatek” to licznik „Siatka
niepotwierdzona”, nie zaobserwowane błędne cięcia. Odczyt bazy (tylko do
odczytu) doprecyzowuje P1-6:

| Gra | Plansze z `structuredDisposition = automatic` | Zdjęcia, w których każda plansza jest `automatic` | Odroczone sloty (`incomplete_lattice`) |
| --- | --- | --- | --- |
| 777a2 | 341 564 z 341 564 | 37 993 z 37 993 | 373 |
| Mumie | 492 171 z 492 215 (44 ręczne) | 54 723 | 1 153 |

Każda zapisana plansza neural przeszła bramkę jako `automatic`; sloty, które
jej nie przeszły, są odroczone, nie zapisane jako plansze. Status
`needs_review` rewizji źródła jest więc stałą ścieżki neural, nie oceną.
Licznik 37 990 niekompletnych zdjęć 777a2 nie niesie informacji o jakości
modelu 777 v2. Zmierzona luka to 373 odroczone sloty (0,1% plansz).

Zalecenie dla rewizji 3, zmieniające priorytety planu:

1. **Etap 0 (mały, bez treningu i GPU):** akceptacja silnika dla ścieżki
   neural zgodnie z D-484: rewizja źródła z kompletem plansz `automatic` dostaje
   `accepted` przy nowym imporcie; osobny podgląd i, za zgodą, backfill
   istniejących rewizji 777a2/Mumie z własnym kodem powodu i wersją bramki.
   Zdjęcia z odroczonym slotem pozostają `incomplete_missing`/`deferred`.
   Wymaga decyzji (D-541 wyłączyła to z tamtego planu, nie na stałe).
   Efekt: licznik pokazuje realne braki, czyli 373 sloty, nie 37 990 zdjęć.
   Zastrzeżenie do zapisania w UI: `automatic` nie dowodzi poprawności;
   model 777 v2 miał na zbiorze deweloperskim 92,3% zdjęć kompletnych i
   poprawnych, więc część zaakceptowanych siatek może być błędna.
2. **Pomiar przed doszkalaniem:** operator przegląda losową próbę
   (np. 100 zdjęć 777a2) w Reviewerze; zatwierdzenia i korekty tej próby
   stają się jednocześnie pierwszymi etykietami REGRESSION/VALIDATION
   (TASK-1002/0995). Odsetek błędnych plansz w próbie decyduje, czy
   doszkalanie 777a2 jest potrzebne teraz.
3. **Kolejność planu:** ścieżka nowych gier (TASK-0994, 1004, 0998) i edytor
   (0993) nie zależą od wyniku pomiaru i mogą iść pierwsze; trening
   (1005, 0996, 0997, 1006) i ponowne rozpoznanie (0999, 1003) dopiero po
   pomiarze i fazie O. TASK-0999 bez etapu 0 nie zmienia nic, co operator
   widzi.
