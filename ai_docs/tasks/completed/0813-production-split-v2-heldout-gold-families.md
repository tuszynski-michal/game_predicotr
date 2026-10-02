---
title: TASK-0813 — podział produkcyjny v2: rodziny złote wyłączone z treningu
status: done
last_updated: 2026-10-02
---

# TASK-0813 — podział produkcyjny v2: rodziny złote wyłączone z treningu

## Status

`done`

## Goal

Nowy snapshot z polityką `production-geometry-split-v2`, w którym część
plansz G leży w rodzinach źródeł całkowicie nieobecnych w treningu, tak aby
ocena na zbiorze złotym miała niepusty podzbiór „rodzina niewidziana”.

## Context

TASK-0801 (`production-geometry-split-v1`, ziarno 801) dał zbiór złoty 102
zdjęć / 459 plansz G, ale wszystkie w rodzinach widzianych w treningu.
Operator polecił 2026-10-02 wymusić niezależny podzbiór złoty przed
treningiem. Operator przyjął też, że rodziny są wizualnie podobne (jedno
nagranie, ruchoma kamera) — to cecha danych, nie błąd podziału.

## Dependencies / entry conditions

- TASK-0801 w repo (`v1.7.155`); snapshot v1
  `production-geometry-snapshots\3ff448c6…727d` pozostaje nietknięty.
- Manifest kandydatów TASK-0800 bez zmian.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Zmiana polityki podziału decyduje o
wiarygodności oceny. Audyt zawieszony decyzją operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/tasks/completed/0801-production-geometry-training-snapshot.md`
- `ai_docs/quality/GRID_V3_TRAINING_SNAPSHOT_20261002.md`
- `ai_docs/delivery/GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` (etap V3-A)

## Scope

- Polityka `production-geometry-split-v2` obok v1 (v1 bez zmian zachowania i
  testów).
- Budowa nowego snapshotu (raz), raport, wpis w przewodniku.

## Out of scope

- Trening, zmiany próbki przeglądu etykiet (próbka z TASK-0801 losowana z
  całego manifestu pozostaje ważna), zmiany v1.

## Acceptance criteria

- [x] v2 = v1 plus krok „rodziny złote wyłączone”: przed wyborem
      developmentu deterministycznie wybierane są rodziny zawierające
      plansze G, które w całości nie wchodzą do treningu; ich zdjęcia
      niezłote zasilają development.
- [x] Reguła wyboru (rozstrzygnięta): rodziny z G sortowane malejąco po
      liczbie plansz G na 1 000 zdjęć rodziny przechodzących filtr (remis:
      identyfikator rodziny); dobierane kolejno, dopóki wyłączone rodziny
      zawierają mniej niż 30% wszystkich plansz G **i** dodanie kolejnej nie
      podniesie utraty puli treningowej (zdjęcia po filtrze) powyżej 20%.
      Co najmniej jedna rodzina jest zawsze wybrana. Wynik i liczby w
      raporcie.
- [x] Development: 600 zdjęć (300 S + 300 B) z rodzin wyłączonych; jeżeli
      nie wystarcza, dobór dodatkowych całych rodzin jak w v1.
- [x] Trening: 6 000 zdjęć (3 000 S + 3 000 B) z pozostałych rodzin, reguły
      warstw i limit rodziny jak w v1.
- [x] Manifest: `familySeenInTraining` poprawne; raport podaje liczbę
      plansz G w rodzinach widzianych i niewidzianych.
- [x] Testy rozłączności i determinizmu dla v2; testy v1 bez zmian i
      zielone.
- [x] Nowy snapshot opublikowany atomowo; v1 nietknięty.
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

Jeżeli progi 30% / 20% nie dają się pogodzić (np. jedyna rodzina z dużą
liczbą G to zarazem największa rodzina treningowa), zatrzymaj się z tabelą
rodzin (zdjęcia po filtrze S/B, plansze G) i dwoma najlepszymi wariantami
zamiast wybierać po cichu. Kopię obrazów wykonaj z ponownym użyciem plików
snapshotu v1, jeżeli mechanizm publikacji na to pozwala bez osłabienia
weryfikacji SHA (twarde dowiązania albo kopia z v1 z kontrolą sumy);
inaczej zwykła kopia ze źródła.

## Expected files

- Istniejące: `vision_lab/production_split.py`,
  `vision_lab/production_snapshot.py`,
  `scripts/vision_lab_production_snapshot.py`, testy z TASK-0801,
  `ai_docs/quality/GRID_V3_TRAINING_SNAPSHOT_20261002.md` (sekcja v2),
  `ai_docs/guides/VISION_LAB_LOCAL.md`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests -q -p no:cacheprovider -k "production_split or production_snapshot or no_production_storage_imports"
.\.venv\Scripts\python.exe -m ruff check services scripts
```

Limit 120 s na testy; budowa snapshotu do 900 s, raz.

## Risks / open questions

- Wyłączenie rodzin zmniejsza różnorodność treningu; raport ma pokazać
  utratę puli.

## Outcome

### Changed

- `services/worker/src/game_predictor_worker/vision_lab/production_split.py`: polityka
  `production-geometry-split-v2` obok v1 (`SplitConfig.policy_version`, progi
  `heldout_gold_share = 3/10`, `heldout_max_pool_loss = 1/5`); funkcja
  `select_heldout_gold_groups` (reguła z kryteriów, tabela kandydatów w
  `plan.heldout_selection`, błąd `HELDOUT_GOLD_THRESHOLDS_IRRECONCILABLE`, gdy progi
  się wykluczają); rodziny wyłączone otwierają listę developmentu, dodatkowe rodziny
  dobierane w kolejności ziarna jak w v1; `assert_disjoint` dodatkowo
  `HELDOUT_FAMILY_IN_TRAINING` i `HELDOUT_FAMILY_OUTSIDE_DEVELOPMENT`; `split_summary`
  dla v2 podaje plansze G w rodzinach niewidzianych i sekcję `heldoutGoldFamilies`.
  Opis polityki v1 (`describe`) jest bajtowo ten sam, więc ID v1 się nie zmienia.
- `.../vision_lab/production_snapshot.py`: `split.json` zapisuje wersję polityki z
  konfiguracji, dla v2 także `heldoutGoldFamilyGroups` i `heldoutGoldSelection`;
  blokada `HELDOUT_GOLD_SUBSET_EMPTY` dla v2 bez złota w rodzinach niewidzianych.
- `scripts/vision_lab_production_snapshot.py`: opcja `--policy` (domyślnie v1).
- Testy: `services/worker/tests/test_vision_lab_production_split.py` (+6 testów v2;
  testy v1 bez zmian, dodany tylko import `dataclasses`),
  `test_lab_production_snapshot.py` (+1 test budowy v2).
- Dane (nowy katalog; nic istniejącego nie zmieniono): snapshot v2
  `C:\Users\tuszy\Documents\game_predictor_vision_data\production-geometry-snapshots\286f2e370aa84437c63fcffe202f01260d6ca13aee317eb8c11cac2ad0f2df59\`
  (6 707 plików, 1 814 113 498 B; obrazy 1 715 762 875 B), zbudowany raz (303,8 s).
- Wynik reguły: wyłączone `299e7c72` „missing cut” (2 G / 9 zdjęć po filtrze; zawsze
  pierwsza) i `0dbd07df` „1-19809 cut” (247 G / 2 082 zdjęcia); 249 z 459 plansz G
  (54,2%) w rodzinach wyłączonych, utrata puli treningowej 2 091 / 49 727 = 4,2%;
  zatrzymanie progiem G. Progi dały się pogodzić. Rodziny wyłączone mają tylko 290 S
  (< 300), więc development dobrał `c0932585` w kolejności ziarna (łączna utrata puli
  z developmentem 10,2%; v1 11,8%).
- Podział: trening 6 000 (3 000 S + 3 000 B, 54 000 plansz, 21 rodzin, największy
  udział 8,37%), development 600 (300 S + 300 B: `0dbd07df` 180 S + 118 B,
  `c0932585` 118 S + 182 B, `299e7c72` 2 S), złoto 102 zdjęcia / 459 G — rodziny
  widziane 51 zdjęć / 210 G, niewidziane 51 zdjęć / 249 G.
- Rozstrzygnięcia: (1) reguła liczona na grupach rodzin (tu 24 grupy = 24 rodziny);
  rodzina z G bez zdjęć po filtrze byłaby pierwsza; (2) 30% to warunek kontynuacji,
  więc wynik może go przekroczyć (54,2%); (3) „progi nie do pogodzenia” = pierwsza
  rodzina ponad 20% utraty albo limit utraty zatrzymuje dobór przed 30% G → błąd, bez
  cichego wyboru; (4) kopia obrazów ze źródła, bez ponownego użycia plików v1 (twarde
  dowiązania wiązałyby pliki obu snapshotów jednym i-węzłem, a kopia z v1 nic nie
  oszczędza, bo kontrola integralności i tak czyta i dekoduje każde źródło).

### Verification results

- `pytest services/worker/tests -q -p no:cacheprovider -k "production_split or production_snapshot or no_production_storage_imports"`:
  37 passed, 1 skipped (17 s); z `label_review`: 44 passed, 1 skipped.
- `ruff check services scripts`: tylko wcześniejsze E501 w
  `services/worker/tests/test_page_geometry_preflight.py:345`; `ruff format --check`
  zmienionych plików czyste; `mypy --strict` zmienionych modułów i skryptu: brak błędów.
- Podgląd v1 nowym kodem (ziarno 801): ID `3ff448c6…727d` = opublikowany v1. Podgląd
  v2 (35,0 s) i budowa v2 dały ten sam ID `286f2e37…df59`; blokad 0, wykluczeń
  integralności 0, braków warstw 0.
- `verify_snapshot`: v2 6 706 sum zgodnych; v1 po budowie v2 6 706 sum zgodnych.
- Niezależny skrypt na `samples.jsonl` v2: 0 zdjęć w dwóch rolach, 0 SHA złotych w
  treningu/developmencie, 0 wspólnych SHA i grup rodzin development/trening, 0 rodzin
  wyłączonych w treningu, 0 naruszeń filtra i reguły jednostki, 0 węzłów poza obrazem,
  0 powtórzonych numerów sekwencji, `familySeenInTraining` 0 błędów.
- Test `real_files` z `VISION_LAB_PRODUCTION_SNAPSHOT` = snapshot v2: 1 passed.
  `checks/visual-training.jpg` v2 obejrzany: 9 siatek leży na planszach.

### Not completed

- Commit, `CURRENT_STATE.md` i przeniesienie pliku do `completed/` — należą do
  orkiestratora (polecenie).

### Documentation updates

- `ai_docs/quality/GRID_V3_TRAINING_SNAPSHOT_20261002.md`: sekcja
  „Podział `production-geometry-split-v2` (TASK-0813)” (tabela rodzin, wynik reguły,
  role, rozłączność, determinizm) i wyniki weryfikacji.
- `ai_docs/guides/VISION_LAB_LOCAL.md`: akapit o `--policy` i snapshocie v2.
- `DECISION_LOG.md` nie zmieniony (polecenie orkiestratora); wybór snapshotu do
  treningu należy do operatora.

### Recommended next task

- TASK-0802 (trening) na snapshocie v2; TASK-0804 raportuje złoto osobno dla rodzin
  widzianych (210 G) i niewidzianych (249 G).
