# TASK-1257 — Niezależny pierwszy trening geometrii gry

## Status

`done`

## Goal

Pierwszy własny detektor i siatka gry uczą się wyłącznie z oznaczeń tej gry, od losowej inicjalizacji obu sieci. Ocenę Mumii oprzeć na zdjęciach, poprawkach i końcowych 15 polach.

## Context

Operator zatwierdził wykonanie całości na gałęzi roboczej i koszt przygotowania oraz testów. Istniejące historyczne zakresy i zakaz stosowania na żywych danych pozostają ważne. Weryfikacja na 100 nowych planszach czeka na nagranie. Ślepej próby nie używamy do projektu ani strojenia.

## Recommended execution

gpt-6.2-astra, high. Całość wymaga spójności przygotowania, treningu i pochodzenia. Wykonawca integruje analizę korekt, pion treningu oraz testy w jednym commicie. Zmiana zakresu lub kosztu wymaga ponownej oceny.

## Relevant docs

- requirements/SUPERVISED_MODEL_IMPROVEMENT.md, architecture/SUPERVISED_MODEL_IMPROVEMENT.md
- delivery/PRIVATE_GAME_GRID_MODELS_PLAN_20261118.md, quality/MUMIE_PRIVATE_GRID_PILOT_20261118.md
- process/decisions/DECISION_LOG_2026.md, D-618

## Scope and technical notes

1. Przeanalizować pary historyczne na części treningowej Mumii w trybie tylko do odczytu. Zmierzyć przemieszczenia zewnętrznych i wewnętrznych węzłów w jednostkach rozmiaru pola. Rozróżnić mierzalne przesunięcie od wymagającej oceny zawartości weryfikacji ucięcia. Zestawić pełne zdjęcia i częściowe oznaczenia w kontekście gotowości detektora.
2. Pierwszą nową operację prywatnej gry skierować na pełne screen+grid z pustymi wagami obu komponentów. Brak pełnych zdjęć blokuje start z konkretną przyczyną. Poprawki pojedynczych plansz nadzorują węzły. Tylko model z udokumentowanym niezależnym początkiem tej gry może inicjować dalsze prywatne treningi. Poprzedni model i przypisanie służą porównaniu i kontroli aktualności. Przypiąć sposób startu do operacji, procesu i artefaktu oraz sprawdzić po wznowieniu. Zachować starsze operacje i wspólne gry. Historyczne role i zakaz przecieku między podziałami obowiązują również od zera.
3. Admin i API pokazują tryb i braki danych. Utrzymać zgodność publikacji, kwalifikacji i ślepego pilota, udokumentować pochodzenie. Niewłaściwy tryb, brak dowodów lub zmiana przypisania blokują operację. Nie wykonywać rzeczywistego treningu, migracji na bazie operatora ani wdrożenia. Profil każdej nowej gry powstaje z jej własnych przykładów. Nie stosować granic zmierzonych na Mumii do innych gier.

## Expected files

- scripts/mumie_grid_pilot*.py, testy i raport Mumii
- application/grid_correction_learning.py, worker images/grid_training_handler.py i grid_training_child.py, stosowne schematy, adaptery, Admin i wygenerowany klient
- dokumenty wymagań, architektury, decyzja, stan projektu i mapy

## Acceptance criteria and verification

- Pomiar na historycznych TRAIN i testy geometrii oraz wycinania 15 pól na kontrolowanym zdjęciu.
- Testy uruchomienia z pustymi wagami, szkolenia obu etapów i wznowienia, obcego modelu/gry, kontynuacji, braku pełnych zdjęć, potwierdzona obsługa historycznych operacji. Sprawdzenie zwykłego punktu wejścia API i panelu, typów i lint zmienionych plików.
- Ocena kandydata względem przypisanej bazy nadal wymaga wszystkich bramek. Pomiar skuteczności pozostaje odrębnym pilotem.
- Uruchomić pytest dla zmienionych pionów, testy Admina, kontrolę dokumentacji i mapę. Zamknąć task skryptem po sprawdzeniu.

## Outcome

Commit: v1.7.686 / `7c71402d2c23b33d643a77a86db39bf9fe511b10`.

### Changed

- Wersja porównawcza, pochodzenie wag i ekspozycja danych mają odrębne znaczenie. Prywatny detektor i punkty zaczynają od zera, kolejne przebiegi mogą kontynuować własne wagi. API, proces treningu, SQL 0194, rejestracja, ewaluacja i Admin obsługują tę samą decyzję. Zmiana jest wspólna dla prywatnych gier; dane jednej gry nie inicjalizują modelu kolejnej.
- Podgląd i pomiar historycznych par Mumii w jednostkach wielkości pola. Spośród 508 korekt bezpośrednio po automacie 264 miały wyraźnie zaniżoną górną granicę. Wszystkie 589 dokładnych rewizji TRAIN pochodziło z 461 zdjęć. Na czterech planszach porównano 120 końcowych wycinków. Szczegóły i instrukcję zawiera raport pilota.
- Nowy ślepy sprawdzian wiąże kandydata z niezależną grą, wersją porównawczą i chwilą zamrożenia. Wymaga zapisu pełnego pola. Historyczne sprawdziany zachowują swój kontrakt.

### Verification results

- Test kontrolny całego procesu na CPU przeszedł w 73,62 s. Obie sieci trenowano z pustych wag, wybrano epokę, wyeksportowano i uruchomiono oba modele ONNX oraz sprawdzono zgodność z PyTorch na rzeczywistych rozmiarach wejścia. Osobny test potwierdził uwzględnienie zdjęć częściowych w koszcie epoki. Zestaw testów API 69/69. W szerszym zestawie workera pozostała zastana asercja starej listy wariantów treningu; test zależny od zegara przeszedł po powtórzeniu.

- Na kontrolowanych obrazach sprawdzono rzeczywistą inicjalizację i aktualizację obu sieci PyTorch, maskowanie częściowych zdjęć i wznowienie. Testy produkcyjnego renderera obejmują wszystkie 15 pól oraz przykłady utraty treści na obwodzie i przy linii wewnętrznej.
- PostgreSQL 18 na osobnej tymczasowej bazie: migracje, przypięcie operacji, rejestracja pierwszej własnej wersji po potwierdzeniu eksportu, odmowa dla obcego właściciela i start kolejnego treningu z przypisanych własnych wag.
- Zaliczone 71 interakcji Admina, 10 testów publicznego wrappera, typecheck i ESLint Admina, zgodność OpenAPI i wygenerowanego klienta. Zestaw rejestru, publikacji i dowodów pilota 43/43; wspólny odbiór mechanizmu, geometrii i pilota 17/17. Testy HTTP uruchomiono z dostępem do lokalnej pętli zdarzeń Windows, a testy pilota z krótkim katalogiem tymczasowym. Ukierunkowane sprawdzenie typów 12 modułów przeszło. Szerszy przebieg z pełnymi importami przekroczył limit czasu.

### Not completed

Rzeczywisty trening, ślepa ocena nowej wersji na 100 świeżych planszach i wdrożenie pozostają poza tym zleceniem. Skuteczność na przyszłych zdjęciach wymaga pomiaru. Operator dostarczy świeży folder.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1257 — niezależny trening, diagnoza cięcia i odbiór | gpt-6.2-astra | high | Przepływ przez dwa modele i trwałe wersje wymaga wspólnej weryfikacji. | Testy integracyjne; bez dodatkowego płatnego audytu. |
