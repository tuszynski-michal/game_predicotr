# TASK-0712 — Wdrożenie i uzupełnienie 70 niepełnych plansz

## Status

`done`

## Goal

Wdrożyć odebrane T1–T4 i udostępnić 1050 pozycji pilota, zachowując decyzje
operatora, atomowe pokwitowania i zgodne liczniki; odczytowo audytować inne gry.

## Context

Użytkownik 2026-09-27 osobno zlecił produkcyjny krok danych: backup, migracje,
zgodne usługi, świeży preview, apply70, liczniki i odbiór. Poprzednie ograniczenie
do samego kodu/preview nie dotyczy tego zlecenia. HEAD wejścia v1.7.16 /
a4c38cacefc62edffe116b485f6497f708ba71d2. Obce zmiany zachować.

## Dependencies / entry conditions

T1–T4 odebrane z audytem; schemat wejściowy 0125, brak aktywnych jobów i
transakcji aplikacyjnych w pierwszym odczycie. Przed mutacją wymagany
niezależny przegląd preflightu i planu backupu. Zgoda użytkownika już udzielona.

## Recommended execution

gpt-6-sol / high; niezależny audyt gpt-6-astra / medium zgodnie z T4 planu.
Jeden wykonawca wszystkich zapisów produkcyjnych; root prowadzi końcowy
odbiór przeglądarkowy i commit. Konflikty owner/revision/source/human
zatrzymują daną planszę i wymagają odczytowego wyjaśnienia, bez wymuszania.

## Relevant docs

- AGENTS.md; ai_docs/process/PLAN_STANDARD.md; ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/PARTIAL_BOARD_SYMBOL_REVIEW_EXECUTION_PLAN.md
- ai_docs/delivery/PARTIAL_BOARD_SYMBOL_REVIEW_RUNBOOK.md
- ai_docs/guides/LOCAL_OPERATION_GUIDE.md
- ai_docs/process/DECISION_LOG.md (D-451, D-452)
- ai_docs/architecture/DATA_MODEL.md
- ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md

## Scope

- Zweryfikowany backup bazy i zapis preflightu procesów/jobów.
- Zatrzymanie głównych writerów API8000/worker, migracje0126–0128,
  zgodne nowe procesy API/Admin3000/worker. Lab8102/3102 poza zakresem.
- Świeży preview po migracji, maksymalnie5 nowych plansz na apply,
  kontrola receiptów i decyzji; 70 plansz /1050 pozycji.
- Ograniczona odbudowa liczników, marker v2 i zgodne sumy grup.
- Ponowny odczyt w nowym procesie i odczytowy audyt pozostałych gier.

## Out of scope

Zmiany danych plansz poza dokładną listą70, trening, zmiana manifestów,
predykcje, lab, push/merge, automatyczny restore lub destrukcyjne cleanupy.

## Acceptance criteria

- [x] Backup zakończony poprawnie, checksum i lista odtworzenia sprawdzone.
- [x] Schemat0128 i zgodne nowe procesy usług; lab bez zmian.
- [x] 70 atomowych receiptów,1050 pozycji; brak zastanych human decisions.
- [x] Restart/retry bez nowych pozycji/eventów i resetu decyzji.
- [x] Counts ready v2, sumy grup oraz API/UI zgodne.
- [x] Odczytowy audyt innych gier z zakresem i wynikami.
- [x] Niezależny audyt, raport i Outcome; osobny commit przygotowuje root.

## Risks / open questions

Pierwszy odczyt: baza90.77GB, wolny dysk108GB. Backup pełny może być
długotrwały; proces kontrolowany, postęp raportowany, bez drugiej kopii.
Nie obiecywać pełnego testowego restore90GB bez osobnego miejsca; sprawdzić
exitcode, checksum i poprawny odczyt katalogu archiwum.

## Outcome

Operacje i odbiór zakończone. Commit `v1.7.17` /
`57e703acb16d435e03521b6ddd02d9857bfa5c72`; po commicie sprawdzono
`git show --stat` i pozostały status. Hash dopisany po utworzeniu commita.
Preflight: Alembic0125, brak aktywnych jobów i transakcji
aplikacyjnych, baza90.77GB z indeksami,108GB wolnego miejsca. Niezależny
audyt preflightu PASS. Zatrzymano wyłącznie main API8000, Admin3000 oraz
zarządzanego workera general7; lab8102/3102 i reviewer3001 zachowane.

Pełny `pg_dump` custom/compression1 rozpoczęty2026-09-27T01:43:05Z.
Po pomiarze rzeczywistego COPY przejęto nadzór tego samego procesu dumpa
PID36824, zachowując uchwyt i exitcode; limit zwiększono20→60min bez
restartu kopii. Dowody w ignorowanym
`artifacts/partial-board-rollout/20260927-t0712/`.
Backup zakończony exit0,22,088,367,628B; SHA
`135915d338a87c5fc5ef26cd280aa457e89e3f8a49ed1b296f166eae8b4617e1`.
Odczyt TOC exit0/4110 pozycji, łącznie1534.21s; bez pełnego próbnego restore.
Audyt bramki PASS, migracje0126–0128 exit0/3.17s.

Produkcyjny build Admina PASS. Świeży preview0125:70ready,985pozycji,
65brakujących,829full/201partial/20outside; SHA
`a964291d5517751f0761842d975fef74df4e1c77a8365d26977a6718f8e7e515`.
Świeży preview po migracji ma ten sam SHA. Apply:14 partii po5,70 receiptów,
1050 pozycji,0 konfliktów, wszystkie985 stare ID zachowane. Niezależny audyt
potwierdził niezmienione źródła, właścicieli, geometrię, obserwacje, predykcje
i kolejkę. Human decisions w pilocie:0; ich ochronę pokrywają izolowane
testy T4, nie ten pilot. Retry w nowym procesie:70 replayed/0 nowych prób,
0 eventów, identyczny końcowy preview SHA
`4444ff694bcf9ad2b7d0b24820fca1543c527ae2e7565e40c843e121fbfdc0fb`.

Liczniki odbudowane niezmienionym repository z pełną walidacją manifestu,
transakcjami do10000 rekordów i trwałym kursorem. Po16 pierwszych partiach
kontynuacja735 wywołań zajęła412.48s. Ready/v2/cursorNULL; dziesięć grup
sumuje się do7,499,687 (pending7,498,986, approved701), outside20.
Live API PASS: grupy, no-asset outside, kontekst źródła. Raport
`live-api-verification.json` przygotował root.

Usługi uruchomione po operacji: API9860 (launcher35276), Admin23576,
general39752 (launcher40784, budżet7); niezależne HTTP200. Lab4200/12968
bez zmian. Pierwszy start Admina i próbny pomiar readiness miały błędy
operatorskie (względna ścieżka Next i zachowana odpowiedź PowerShell);
poprawiono polecenie oraz pomiar i potwierdzono bieżące PID/HTTP.

Odczytowy audyt innych gier: mumie26 plansz/390full/0braków, test0 plansz.
Odrębnie potwierdzone13 braków na6 wskazanych planszach777 poza pilotem;
nie zostały uzupełnione. Bez treningu, rozpoznawania, modyfikacji manifestów,
pełnego restore, restartu OS ani push/merge. Raport:
`ai_docs/quality/PARTIAL_BOARD_SYMBOL_REVIEW_ROLLOUT.md`.
Niezależny audyt danych/liczników/usług PASS bez P0–P2.

Browser QA na rzeczywistym Admin3000 PASS: wszystkie grupy,20 kafelków
„Poza zdjęciem” z numerem i pozycją, trwały badge, dostępne przypisanie
symbolu i „Nieczytelny”, wyłączona grafika symbolu i „Niewyraźny” bez
obrazu. Kontekst planszy61882/pole1 pokazuje zdjęcie, siatkę i wyróżnienie
pola poza kadrem. Nie zapisano żadnej decyzji operatora, zaznaczenie po
odbiorze wyczyszczono. DoD porównane z planem: cały osobno zlecony krok
wdrożenia i danych spełniony;13 braków poza pilotem pozostaje odrębnym zakresem.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0712 / operacyjny T4 | gpt-6-sol | high | Backup, rewizje, trwałe wznowienie i ochrona decyzji | gpt-6-astra, medium |
