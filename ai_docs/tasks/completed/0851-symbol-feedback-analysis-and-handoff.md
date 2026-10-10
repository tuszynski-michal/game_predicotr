# TASK-0851 — Korekty operatora jako dowód jakości rozpoznawania symboli

## Status

`done`

## Goal

Ocenić RGB na nowych zatwierdzeniach audytu 777, sprawdzić ograniczoną poprawę
na niezależnych źródłach i przygotować odtwarzalną notatkę dla Claude Code.

## Context

Operator nadal koryguje błędy i prosi o wykorzystanie tych przykładów do
dopracowania mechanizmu oraz przekazanie skuteczniejszej metody do dalszego przebiegu.

## Dependencies / entry conditions

Aktualna metoda D-494: zamrożona głowica SpatialSymbolCnn, oryginalne RGB
64px /127.5−1; biblioteka dodatkowo potwierdza klasę. Nowe zatwierdzenia nie
zmieniają tych wag ani zamrożonej biblioteki. TASK-0832/0833 pozostają zatrzymane.

## Recommended execution

gpt-6.1-sol / high. Jeden wykonawca; brak delegacji. Zatrzymać wdrożenie
poprawy, jeśli niezależna kontrola nie wykazuje poprawy lub tożsamość cropa jest niezgodna.

## Relevant docs

- AGENTS.md, README.md, CURRENT_STATE.md, PLAN_STANDARD.md, TASK_TEMPLATE.md,
  DEFINITION_OF_DONE.md w ai_docs/process lub katalogu głównym dokumentacji.
- ai_docs/process/DECISION_LOG.md — D-491–494, D-465/466.
- ai_docs/requirements/ADMIN_APP.md; ai_docs/architecture/API_CONTRACT.md.
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md.
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md.

## Scope

- Tylko zatwierdzone aktualne piksele i etykiety audytowanych plansz 777.
- Snapshot tylko do odczytu, bounded rendering z weryfikacją SHA, raport
  zamian i rozdzielenie błędów cięcia od błędów klasyfikacji.
- Deterministyczny podział po źródle; żadna komórka testowa nie może być wzorcem.
- Ograniczone porównanie obecnego RGB z kandydatem wykorzystującym nowe
  referencje człowieka lub stabilność obrazu, bez treningu/aktywacji CNN.
- Trwała implementacja tylko uzasadnionej metody, testy i notatka przekazania.

## Out of scope

Wznowienie TASK-0832/0833, masowe przepisywanie predykcji, automatyczne
zatwierdzanie, zmiany geometrii, aktywacja modelu, push i wdrożenie.

## Acceptance criteria

- [x] Aktualna jakość zmierzona na rzeczywistych zatwierdzeniach, z ograniczeniami.
- [x] Kandydat oceniony bez przecieku źródeł; brak przewagi oznacza brak wdrożenia.
- [x] Zatwierdzone dane, geometrie i aktywny checkpoint pozostają bez zmian.
- [x] Notatka opisuje przyczynę poprzedniej poprawy, dowody, wersje, komendy
  i zasady bezpiecznego zastosowania do pozostałych pending.
- [x] Właściwe testy, lint/typecheck, nowy proces, Outcome i osobny commit.

## Technical notes

Korekta etykiety jest referencją wyłącznie dla dokładnych zatwierdzonych
pikseli. Zmiana siatki nie jest błędem klasyfikatora na poprzednim cropie.
Niezmienione automatycznie wybrane symbole zatwierdzone przez Save są decyzją
operatora, lecz słabszym dowodem niż ręczne nadpisania; raport rozróżnia te grupy.
Train/validation/test rozdzielane po zdjęciu, bez exact duplikatów między splitami.
Propozycja nigdy nie staje się zatwierdzeniem bez działania operatora.

## Expected files

- Nowe: scripts/evaluate_grid_audit_feedback.py, testy i raport lokalny.
- Możliwe: services/worker/src/game_predictor_worker/symbols/audit_rgb_classifier.py
  oraz scripts/recognize_grid_audit_symbols.py, po wykazaniu przewagi.
- Nowe: ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md.
- Dokumentacja: własna sekcja CURRENT_STATE, task, decyzja jeśli zmieni się polityka.

## Test cases / Verification

Ograniczone procesy do 120 s, snapshot zapytań 15 s, rendering wznawialny.
Powtórna kontrola z nowego procesu. Jednostkowe testy izolacji źródeł,
integralności manifestów i zachowania domyślnego RGB. Faktyczne komendy
i wyniki zapisane w Outcome. Bez testów obciążeniowych i sztucznej skali.

## Risks / open questions

777 ma współdzielone warunki fotografowania; oddzielne zdjęcia nie gwarantują
niezależnych rodzin. Zatwierdzenie propozycji może zawierać przeoczony błąd.
Skuteczność na sprawdzonym audycie nie dowodzi skuteczności całej populacji.

## Outcome

### Changed

- Nowe narzędzie scripts/evaluate_grid_audit_feedback.py zamraża aktualne
  zatwierdzone piksele tylko do odczytu i ocenia RGB oraz ograniczone warianty
  najbliższych wzorców. Manifesty wiążą snapshot, cechy i checkpoint SHA.
- Pierwszy odczyt 5428 pól; końcowy poprawiony snapshot 5788 pól / 578 źródeł,
  ponieważ operator kontynuował przegląd w czasie analizy. Narożniki pobierane
  z konkretnej rewizji; 164 pola mają inne cięcie od pierwotnej propozycji.
- RGB: 100/5788 rozbieżności z operatorowymi etykietami. W grupie aktualnych
  propozycji RGB 44/3780; Cytryna 0/556, Śliwka 1/584, Arbuz 1/429.
- Referencje: 3644 pól / 341 źródeł; validation 1188 / 134; test 956 / 103.
  Każda klasa pokryta; brak dokładnych duplikatów/konfliktów między splitami.
- Wariant najbliższego wzorca 0,98: test 21 → 18 błędów, Cytryna 2 → 5.
  Nie wdrożono. safe_improvement odrzuca pogorszenie choćby jednej klasy;
  wszystkie cztery warianty nie przeszły tej bramki już na validation.
- Notatka: ai_docs/guides/SYMBOL_RGB_FEEDBACK_HANDOFF_20261005.md.
  Opisuje D-494, dowody, interfejsy, komendy i potrzebny adapter dla globalnego
  pending-only zapisu; nie myli argmax z biblioteczną confidence 0,99.

### Verification results

- 5788/5788 odtworzonych cropów ma zgodne zatwierdzone SHA.
- Odczyt REPEATABLE READ READ ONLY, statement timeout 15 s. Pierwszy plan
  zapytania przekroczył limit; MATERIALIZED scoped rozwiązał szeroki join.
- prepare snapshot / render / features / evaluate wykonane w ograniczonych
  procesach. Końcowa kontrola evaluate z nowego procesu wskazuje retain_rgb_v2.
- Testy nowego ewaluatora i regresje RGB: 28 PASS; Ruff format/check PASS.
- Kontrola historii 5788 decyzji: zero masowych zatwierdzeń. Nowy snapshot
  automatycznie wyklucza takie zatwierdzenia zgodnie z D-465.
- Końcowy smoke nowego exportera w oddzielnym procesie: 7018 pól / 626 źródeł,
  zero bulk approvals. Zbiór oceny 5788 nie został podmieniony; dla smoke
  nie uruchamiano dodatkowego renderu/inferencji ani nie dopisywano accuracy.
- Scoped Mypy PASS. Pierwsza kontrola całego drzewa zależności przekroczyła
  100 s i proces zakończył runner; brak pozostawionego procesu. Kontrola z
  follow-imports=skip po jawnych aliasach typów PASS.
- API games potwierdza game code 7 / name 777. Nie uruchomiono przebiegu
  publikującego nowe podpowiedzi; komenda handoff korzysta z istniejącego CLI.
- Dowody: artifacts/grid-audit-feedback-20261005/approved-v2/.
- Kryteria akceptacji porównane punkt po punkcie; nieudany kandydat zachowany
  tylko jako raport, bez mutacji bazy, geometrii, modelu lub sidecarów audytu.
- Commit `v1.7.197` / `fbef9096a1c937ad4884e745b48dc57bffa815af`
  (hash dopisany po commicie).

### Not completed

Brak kolejnej wdrożonej poprawy klasyfikacji: wzorce pogarszały problematyczne
klasy. Bez treningu/aktywacji CNN, nowego UI/API, globalnego adaptera writer,
wznowienia TASK-0832/0833, masowego zapisu, push lub wdrożenia.

### Documentation updates

Notatka przekazania i własna sekcja CURRENT_STATE. Polityka D-494 zachowana;
nowa decyzja architektoniczna nie jest potrzebna dla ewaluatora tylko do odczytu.

### Recommended next task

Claude Code może użyć przekazanej metody RGB na preview wybranego zakresu.
Dalszy model powinien wykorzystać silne korekty Winogron/Siedem z niezależnymi
rodzinami zdjęć i istniejącym kontraktem supervised model improvement.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
| --- | --- | --- | --- | --- |
| TASK-0851 | gpt-6.1-sol | high | Analiza referencji, izolacja testu i ochrona decyzji operatora. | Samodzielna kontrola na zamrożonym zbiorze z nowego procesu. |
