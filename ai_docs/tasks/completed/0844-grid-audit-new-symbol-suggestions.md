---
title: TASK-0844 — nowe podpowiedzi symboli dla proponowanych siatek audytu
status: done
last_updated: 2026-10-05
---

# TASK-0844 — nowe podpowiedzi symboli dla proponowanych siatek audytu

## Status

`done`

## Goal

Przeliczyć symbole wszystkich nadal otwartych propozycji siatek 777 biblioteką
wzorców i pokazać wyłącznie nowe podpowiedzi w istniejącym Reviewerze.

## Context

Operator 2026-10-05 zlecił rozpoznanie symboli proponowanych siatek oraz ponowny
ręczny przegląd wszystkich pól. Stare zatwierdzone etykiety nie mogą być
podpowiedziami dla nowego cięcia. Jest to korekta istniejących plansz 777,
nie trening ani nowy import V3 objęty D-489.

## Dependencies / entry conditions

- TASK-0840/0841 wdrożone; audyt `silent-grid-777-20261004` ma 975 pozycji.
- Odczyt kolejki przed zadaniem: 917 otwartych, 58 poprawionych.
- Biblioteka `symbol-reference-library-v1`, polityka `no-bulk-approve-v2`.
- Polecenie operatora obejmuje wykonanie przeliczenia i pokazanie wyniku lokalnie.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`. Jedno zadanie łączy trwałe artefakty, istniejący
kontrakt API i podgląd Reviewera. Bez delegowania. Niezależny review wymagany
przy zmianie zasad zatwierdzania lub zapisie danych domenowych; ten zakres
obejmuje wyłącznie podpowiedzi i odczyt danych.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — Korekta cięcia siatki
- `ai_docs/architecture/API_CONTRACT.md` — TASK-0840, D-488
- `ai_docs/process/DECISION_LOG.md` — D-464–466, D-488–489

## Scope

- Zgodne rozszerzenie `GridAuditProposalResponse` o nowe podpowiedzi związane
  z dokładną komendą podglądu, źródłem, rewizjami i sumą audytu.
- Trwały, wznawialny CLI wykorzystuje istniejący odczyt biblioteki wzorców
  i bezstratny PNG istniejącego `geometry-preview`; nie zapisuje bazy.
- Reviewer używa tylko nowych podpowiedzi. Wynik niepewny pozostaje pusty.
  Zmiana narożników lub kwalifikacji unieważnia podpowiedzi starego cięcia.
- Uruchomienie dla otwartych plansz, odczyt w nowym procesie i odbiór UI.

## Out of scope

Trening, nowe modele, automatyczne zatwierdzanie, zmiana geometrii i istniejących
decyzji człowieka, przebiegi Śliwki/Arbuza, migracje, push i merge.

## Acceptance criteria

- [x] Wszystkie nadal otwarte plansze mają przeliczony wynik lub jawny błąd.
- [x] W podglądzie żółtej siatki nie pojawiają się stare zatwierdzone symbole.
- [x] Niepewne symbole pozostają do ręcznego wskazania; propozycje nie są wyborami.
- [x] Nowe cięcie, zmiana źródła, rewizji albo audytu nie otrzymuje starego wyniku.
- [x] Wznowienie po restarcie odzyskuje artefakty bez ponownej kalkulacji gotowych pozycji.
- [x] Zwykła korekta zachowuje podpowiedzi zapisanych symboli i swoje zapisy.
- [x] Backend, OpenAPI, klient, wrapper i test żądania pozostają zgodne.

## Technical notes / plan wykonania

1. Dodać checksum-bound artefakt nowych podpowiedzi obok niezmiennego audytu.
   Każda plansza ma komendę podglądu i 15 wyników. Publikacja manifestu jest
   atomowa. Brak artefaktu oznacza brak podpowiedzi; uszkodzony artefakt daje
   jawny błąd. Poprawione plansze są pomijane.
2. Rozszerzyć istniejący odczyt jednej propozycji; serwer kontroluje scope,
   źródło, rewizje i topologię. Klient porównuje całą komendę podglądu.
3. Przeliczyć crops 64×64 z PNG renderera istniejącą biblioteką. Pewny wynik
   wymaga zgodnego jednomyślnego głosu 7/7 obu opisów. Niepewny wynik ma null.
   Referencje należące do plansz tego audytu są wykluczone, aby stara błędna
   geometria nie głosowała za własnym wynikiem.
4. Uruchomić testy, formatowanie i kontrolę typów, przeliczenie i odbiór lokalny.
   Wdrożenie lokalnego podglądu jest częścią polecenia „pokaż mi siatki”.

## Expected files

- Istniejące: aplikacja i schema `grid_audit_proposals`, zależność w `main.py`,
  `board-geometry-correction-target.ts`, OpenAPI i wygenerowany klient,
  testy kolejki API/Reviewera/klienta, wymagania i kontrakt.
- Nowe: `application/grid_audit_symbol_suggestions.py`,
  `scripts/recognize_grid_audit_symbols.py`, test CLI i niniejszy task.

## Test cases

Nowe podpowiedzi zamiast zatwierdzonych etykiet; brak/stale/uszkodzony artefakt;
zmiana narożników i kwalifikacji; brak automatycznego przypisania; niepewny
wynik; restart i idempotencja; zwykła korekta bez zmian.

## Verification

Testy API i CLI przez `.venv/Scripts/python.exe -m pytest`, Ruff i Mypy zmienionych
modułów. Testy Reviewera (`test`, `test:geometry`), lint, typecheck i build;
testy i typecheck klienta oraz kontrola OpenAPI. Każdy skończony krok ma timeout
do 120 s. CLI pracuje w ograniczonych rundach, zapisując postęp na dysku.

## Risks / open questions

Nowy wynik jest podpowiedzią, nie dowodem poprawności siatki. Brak pewnej
propozycji pozostaje widoczny. Użytkownik przejrzy wszystkie pola. Brudne
pliki zastane przed zadaniem pozostają poza commitem.

## Outcome

Rozpoznano wszystkie 917 otwartych plansz audytu `silent-grid-777-20261004`:
10 425 podpowiedzi i 3330 wyników niepewnych (`symbolId=null`) z 13 755 pól.
58 wcześniej poprawionych plansz pominięto. Końcowy odczyt kolejki: 975 total,
917 open, 58 corrected, bez zmiany decyzji człowieka ani rewizji geometrii.
Wszystkie przeliczane plansze miały kwalifikację pełną, bez explicit qualification.

Zastosowano istniejące `symbol-reference-library-v1`, `no-bulk-approve-v2`,
jednomyślny głos 7/7 opisów shape/hue i combined/CNN. Biblioteka została zamrożona
z 5653 referencjami; wykluczono 192 referencje plansz tego audytu. Po pierwszej
rundzie użyto istniejącego `vote_batch` zamiast osobnych głosów dla każdego pola;
reguła decyzji pozostała taka sama. Przebieg zakończył się w pięciu ograniczonych
rundach (75, 218, 229, 238 i 157 plansz), bez błędów i bez zmiany danych domenowych.

- Niezmienny audyt: SHA-256
  `90df51daa981b304167d3ddeddc75ff2ae5b242564dc1dc8dc0227456c479f19`.
- Checkpoint: iteration `d5b3e588-f2f2-4d4b-b2fb-9b5a72a6d52b`, SHA-256
  `1731869da3d082c43968c55bbc3fee0e2f58066ebcabf50191fb53164fb35f6c`.
- Artefakty: `artifacts/grid-audit-proposals/bfc4f949-5c14-4850-b02a-db99610bcfa5/`
  `silent-grid-777-20261004/symbol-suggestions/`; każdy payload ma własny manifest.
- Zamrożona biblioteka, cursor i status: `artifacts/grid-audit-symbols-20261005/`.
  SHA-256 biblioteki: `5be7ab9f7470ea3174cde032df5c0d4992ba545b41defdfcb69ee7e362a4707f`.
- Odbiór nowego procesu: `complete=true`, `coveredOpenBoards=917`, `processed=0`.
  Test odtwarza utratę odpowiedzi po publikacji, odzyskanie bez renderowania oraz
  reset cursora, gdy brakuje artefaktu. Pliki pozostają dostępne po restarcie API.
- Lokalny Reviewer przebudowano i uruchomiono na 3001. Sprawdzono w UI p00271:
  10/15 nowych podpowiedzi, pola niepewne puste, wszystkie decyzje symboli puste.
  Podgląd pozostawiono otwarty dla operatora. Screenshot:
  `.runtime/task0844/reviewer-new-symbols.jpg`.
- API rozszerza istniejący GET, bez nowego endpointu ani tabeli. Checksum mismatch
  ma 409; malformed artifact ma 422. Zmiana źródła/rewizji/topologii odrzuca wynik;
  klient porównuje całą komendę, włącznie z narożnikami i kwalifikacją.
- Reviewer nie wywołuje starego odczytu etykiet dla audytu. Pozostałe korekty
  zachowują istniejącą ścieżkę. Podpowiedź nie jest przypisaniem ani zatwierdzeniem.

Weryfikacja:

- `pytest` dwóch modułów API/CLI: końcowo 31/31; dwa istniejące moduły biblioteki:
  52/52. Regresje obejmują wznowienie po utracie odpowiedzi oraz kody HTTP.
- Reviewer: 209/209 testów jednostkowych i 19/19 testów interakcji.
- Klient API: 79/79 testów, w tym odczyt nowych podpowiedzi istniejącym wrapperem.
- Ruff check/format zmienionych siedmiu plików; lint i typecheck Reviewera,
  typecheck klienta, kontrola OpenAPI oraz production build Reviewera — PASS.
- Strict Mypy pięciu wskazanych modułów — PASS. Konfiguracja pomocnicza w
  `.runtime/task0844/mypy.ini` pomija dalszy graf importów projektu i Torch,
  zachowując typy Pydantic i NumPy. Próba całego grafu przekroczyła 60 s i została
  przerwana; potwierdzono zakończenie własnych procesów. Pełnego typecheck repo
  ani pełnej suite backendu nie uruchamiano.
- Końcowe logi oraz podsumowanie: `.runtime/task0844/`.

Wznowienie w PowerShell, z katalogu repozytorium:

```powershell
.venv/Scripts/python.exe -m scripts.recognize_grid_audit_symbols `
  --game-id bfc4f949-5c14-4850-b02a-db99610bcfa5 --game-code 7 `
  --output-dir artifacts/grid-audit-symbols-20261005 `
  --library-cache artifacts/grid-audit-symbols-20261005/reference-crops.npz `
  --max-seconds 80
```

Kod 3 oznacza ograniczoną rundę do wznowienia tym samym poleceniem; kod 0 oznacza
kompletność otwartej kolejki. Cursor jest jedynie checkpointem; końcowy odczyt
sprawdza dostępność i checksum wszystkich otwartych pozycji. Zmiana geometrii
po rozpoznaniu ukrywa podpowiedzi i wymaga ręcznego wskazania symboli.

Definition of Done i cztery kroki zaakceptowanego zakresu spełnione. Nie wykonano
treningu, aktywacji modelu, zapisu/cleanup danych, push ani merge. Android device
acceptance nie był częścią zakresu; istniejące kontrolki i dotykowy workflow
pozostały bez zmian. Operator przejrzy wszystkie symbole przed ich zatwierdzeniem.

Commit przygotowany: `v1.7.189`; pełny hash zostanie dopisany po commicie.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0844 | gpt-6.1-sol | high | Zgodne rozszerzenie istniejącej kolejki i trwałe propozycje bez zapisu domeny. | Samodzielny przegląd; niezależny review przy zmianie zatwierdzania lub zapisach domenowych. |
