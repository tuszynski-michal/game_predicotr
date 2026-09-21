---
title: TASK-0593 — V7 manual output decisions
status: done
last_updated: 2026-09-21
---

# TASK-0593 — Ręczne decyzje outputu V7

## Goal

Umożliwić trwały ręczny pierwszy zapis, checksum-bound `manual_replace`,
ręczne przypisanie bez dowodu OCR oraz ostatnią stronę 1–8 plansz, bez
utraty historii ani automatycznego zastąpienia pliku.

## Context

T08 bezpiecznie zapisuje wyłącznie automatyczny pierwszy rezultat pełnej
strony. Operator musi móc jawnie potwierdzić zakres bez OCR, zaakceptować
pierwszy rezultat półautomatu, dodać ostatnią krótszą stronę i zastąpić
istniejący wynik lepszym kandydatem. Podmiana ma odróżniać historyczną
operację od bieżącego właściciela pliku.

## Dependencies / entry conditions

- TASK-0584–0592 są ukończone; `V7OutputWriter` ma przypięty manifest,
  atomowy journal, owner targetu i wspólną blokadę katalogu.
- V7 pozostaje zablokowane przez API do T12. T09 buduje warstwę domenową i
  filesystemową; T10 połączy ją z formularzem i widokiem.
- Przyjęte założenie: ręczne przypisanie bez OCR wymaga jawnego pola
  `operator_confirmed_range=True`, a zapisuje `manual_no_ocr` jako metodę
  decyzji. Nie jest ono liczone jako automatyczny sukces OCR.

## Recommended execution

`gpt-6-astra`, reasoning `xhigh`: zmiana rozszerza trwały protokół plikowy i
jego recovery o świadomą podmianę. Przed commitem wymagany review
`gpt-6-astra`, reasoning `medium`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0592-v7-output-journal-and-recovery.md`

## Scope

- Rozszerzyć journal T08 o rozróżnienie `automatic_first`, `manual_first`,
  `manual_no_ocr` i `manual_replace`, źródło decyzji oraz pełną historię
  generation/owner.
- Dodać jawny ręczny pierwszy zapis dla pustego targetu, także zakresu 1–8;
  nazwa nadal wynika z rosnących granic zakresu.
- Dodać ręczne przypisanie bez OCR wyłącznie po potwierdzeniu operatora,
  utrwalając metodę niekwalifikującą się do metryk automatu.
- Dodać `manual_replace`: wymaga oczekiwanego SHA aktualnego targetu, aktualnej
  generacji i ownera, kopiuje nowy oryginalny JPEG przez temp, a po publikacji
  zapisuje nowego ownera bez zmiany historycznej operacji.
- Uzupełnić recovery o rozróżnienie starego i nowego SHA podczas replace,
  crash po publikacji przed commitem, retry tej samej komendy, `cancelled` /
  `superseded` oraz kontrolowaną barierę starego writera.

## Out of scope

- Endpointy HTTP, mutacje bazy, UI, OCR, automatyczny wybór bez dowodu,
  zmiana bramki aktywacji, trening i jakikolwiek zapis w realnym katalogu
  użytkownika.

## Acceptance criteria

- [ ] Półautomat może zatwierdzić pierwszy output do pustego `cut`; utracona
  odpowiedź zwraca tę samą committed operację.
- [ ] `manual_replace` wymaga aktualnego ownera, generacji i starego SHA;
  obcy/zmieniony target zostaje konfliktem bez nadpisania.
- [ ] O1/H1 → ręczna O2/H2 → restart utrzymuje O1 jako historię i O2 jako
  current owner; crash po publikacji O2 przed commitem poprawnie kończy O2.
- [ ] Ręczny wybór bez OCR wymaga jawnego potwierdzenia zakresu i pozostaje
  oznaczony jako ręczny, nie jako sukces automatu.
- [ ] Ręcznie wybrany zakres 1–8 tworzy `seq_1-8.jpg`; automatyczny pierwszy
  zapis nadal odmawia zakresu innego niż pełne 9.
- [ ] Zatrzymany G1 między walidacją a publikacją nie może zastąpić decyzji
  G2; operacje `cancelled` i `superseded` są odtwarzalne po restarcie.

## Technical notes

1. `manual_replace` ma osobny fingerprint obejmujący operation ID, target,
   źródło, nową generation, expected previous SHA, expected previous owner i
   jawne potwierdzenie operatora, że nowe zdjęcie nadal przedstawia zakres.
   Ponowienie z dowolną różnicą zwraca konflikt idempotencji.
2. Pod wspólną blokadą writer najpierw odtwarza journal, potem sprawdza pełny
   manifest, current owner, generation i SHA targetu; po copy temp robi tę samą
   kontrolę bezpośrednio przed replace. Gwarancja obejmuje worker/API/recovery
   używające tej blokady. Zewnętrzny proces NTFS może zmienić plik po kontroli;
   przypadek wykrywalny przed replace zostaje konfliktem, a ochrona przed
   wrogim procesem nieuczestniczącym w blokadzie nie jest obiecywana.
3. Replace recovery interpretuje target H1 jako nieopublikowaną O2, H2 jako
   published O2, a inną checksumę jako conflict. Dopiero `committed` O2 staje
   się current owner; O1 nie porównuje już targetu z H1.
4. `manual_no_ocr` zapisuje explicite `operator_confirmed_range`; nie istnieje
   ścieżka, w której sąsiednie OCR nadaje zakres ręcznie wybranemu zdjęciu.

## Expected files

- Istniejące: `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_output_writer.py` — writer/journal/recovery T08.
- Istniejące: `services/worker/tests/test_v7_output_writer.py` — testy
  crash/idempotency/lock T08.
- Istniejące: wymagania, architektura, `CURRENT_STATE.md`, `TEMP PLAN V7.md`.
- Nowe: brak planowanych modułów; API/UI zostają T10.

## Test cases

- Pusty target + `manual_first` → dokładny SHA, committed owner i retry po
  utraconej odpowiedzi.
- Manual no-OCR bez potwierdzenia → błąd; z potwierdzeniem → committed metoda
  ręczna bez auto proof.
- `seq_1-8.jpg` ręcznie → poprawna nazwa i SHA; automatic first 1–8 → błąd.
- O1/H1 → O2/H2 → restart → H2/current O2 oraz historyczna O1 bez konfliktu.
- O2 crash po temp/publish przed commit → recovery; H1/H2/obcy SHA prowadzą
  odpowiednio do wznowienia/commitu/konfliktu.
- Podmiana ze starym SHA lub ownerem po zmianie G2 → conflict bez dotknięcia
  bajtów. Bariera G1/G2 kontroluje kolejność, nie timing.
- `cancelled` / `superseded` nie wznawiają publikacji po restarcie.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_v7_output_writer.py services/worker/tests/test_v7_run_state.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection/v7_output_writer.py services/worker/tests/test_v7_output_writer.py
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/semi_automatic_selection/v7_output_writer.py --ignore-missing-imports --follow-imports=skip
```

## Risks / open questions

- T09 nie daje ochrony przed procesem spoza aplikacji, który zmienia target
  w mikroodstępie po ostatniej kontroli SHA. Protokół V1 gwarantuje porządek
  współpracujących procesów aplikacji i fail-closed dla zmian wykrytych przed
  publikacją; T10 musi tę granicę pokazać operatorowi przy konflikcie.
- T10 rozstrzygnie dostępność tych decyzji w UI i ich trwałe endpointy bez
  tworzenia równoległego workflowu.

## Outcome

- `V7OutputWriter` obsługuje teraz `manual_first`, `manual_no_ocr`,
  `manual_replace` oraz kontrolowane `cancel_pending`. Pierwszy ręczny zapis
  może mieć zakres 1–8; automatic first zachowuje bramkę pełnych dziewięciu
  plansz. `manual_no_ocr` i `manual_replace` wymagają trwałego potwierdzenia
  operatora, a ich decision kind nie może zostać pomylony z automatic proof.
- Podmiana utrwala H1/O1 i generation w fingerprintcie O2, drugi raz
  weryfikuje je bezpośrednio przed `os.replace`, a następnie przekazuje ownera
  na H2/O2. Recovery rozróżnia H1, H2 i obcą zawartość, zachowuje historię
  O1/H1 także w łańcuchu O1 → O2 → O3 oraz bezpiecznie odtwarza crash po
  publikacji przed commitem.
- Weryfikacja po poprawkach: `70 passed` dla T08/T09 i regresji T03/T04/T07;
  Ruff i mypy writer'a przeszły. Self-audyt naprawił kompatybilność
  fingerprintu automatu T08, ścisłe booleany journala oraz oba warianty
  recovery historycznego ownera. Astra Medium zatwierdziła poprawkę po teście
  dwóch kolejnych ręcznych podmian i dwóch restartów.
- Nie wykonano API/UI, OCR, aktywacji ani zapisu do katalogu użytkownika;
  integracja decyzji z formularzem i podglądem należy do T10.
