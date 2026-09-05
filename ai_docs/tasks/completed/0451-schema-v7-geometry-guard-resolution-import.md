# Task 0451 — Schema v7 i wykonanie decyzji bramki geometrii

Status: done

## Goal

Powiązać zamknięty manifest decyzji przedimportowych z nowym browser-importem
schema v7 i zastosować decyzje pełna/częściowa/odrzucona w workerze bez
mutowania surowego raportu bramki ani tworzenia fałszywych cropów.

## Scope

- browser-import schema v7 z checksum-bound manifestem decyzji,
- fail-closed walidacja manifestu w API i workerze,
- zachowanie surowego wyniku bramki oraz jawne rozliczenie wszystkich błędów,
- ręczna pełna geometria przechodząca normalne invariants,
- częściowa plansza z cropami tylko dostępnych komórek i bez kanonizacji,
- odrzucona plansza bez recognized board, cropów i kolejki ręcznej,
- kompatybilność odtwarzania schema v5 i reprocess schema v6,
- testy kontraktu i projekcji workera.

## Out of scope

- UI kolejki i edytora decyzji,
- operatorskie ponowienie joba `86128f3c-7a0b-4197-bc58-5641e3c03876`,
- automatyczne oznaczanie obecnych ośmiu plansz jako częściowe,
- zmiana progu 98% lub algorytmu `structured_lattice_v3`.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/process/DECISION_LOG.md` (D-339, D-340)
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- nowe browser-importy używają schema v7 i fingerprint obejmuje manifest decyzji,
- API odrzuca obcy, otwarty albo niezgodny manifest przed utworzeniem joba,
- worker ładuje artefakt content-addressed i odrzuca każdy drift bez fallbacku,
- surowy raport bramki zachowuje wynik automatyczny, a start przechodzi tylko po
  rozliczeniu każdego błędnego slotu i braku nowych błędów,
- pełna korekta tworzy 15 komórek, częściowa wyłącznie dostępne komórki, a
  odrzucona nie tworzy projekcji planszy,
- częściowa plansza nie blokuje źródła i nie trafia do stagingu layoutów,
- schema v5 i v6 nadal się odtwarzają,
- skoncentrowane testy, lint, typecheck i build są zielone albo niezależny
  wcześniejszy blocker jest jawnie udokumentowany,
- dokumentacja oraz `CURRENT_STATE.md` opisują wynik.

## Outcome

- Browser-import schema v7 przypina opcjonalny, zamknięty manifest rozliczeń;
  API sprawdza jego grę, staging, oba manifesty wejściowe i checksumę przed
  utworzeniem nowego joba, a fingerprint obejmuje jego tożsamość.
- Worker ładuje artefakt wyłącznie z zarządzanej przestrzeni, weryfikuje każdą
  decyzję i wymaga dokładnego pokrycia surowych odroczeń. Pełne korekty ponownie
  przechodzą invariants, częściowe tworzą tylko dostępne cropy i sparse
  observations, a odrzucone nie tworzą projekcji planszy.
- Plansza `pending_partial` nie blokuje zakończenia źródła, nie trafia do
  stagingu layoutów i nie może zostać zaakceptowana jako pełny kanoniczny
  layout. Historyczne schema v5 i reprocess schema v6 nie ładują wejścia v7.
- Dodano pola postępu rozdzielające surowy wynik od liczby full/partial/rejected,
  zaktualizowano OpenAPI, klienta Admina i dokumentację.
- Weryfikacja: 139 skoncentrowanych testów API/workera, Ruff, OpenAPI check,
  typecheck klienta i Admina oraz 12 testów `job-state` zakończyły się sukcesem.
  Pełny Python mypy został przerwany po 60 sekundach bez wyniku; mniejsze
  uruchomienie z `--follow-imports=skip` nie jest miarodajne z powodu celowo
  pominiętych lokalnych modułów i nie ujawniło błędu wykonawczego.
- Nie uruchomiono ani nie zmieniono joba `86128f3c…`. UI kolejki, audytowa
  rekonstrukcja jego raportu v1 i operatorski start nowego importu pozostają
  osobnymi taskami.
