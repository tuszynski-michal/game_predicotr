---
title: Version 0.6 execution plan
status: accepted
last_updated: 2026-08-12
---

# Plan zakresu wersji 0.6

## Cel

Uprościć następny etap pracy operatora po selekcji zdjęć. Pierwszy pion 0.6
obejmuje ulepszenia pierwszego workspace’u Admina `Gry` oraz workspace’u
`Import layoutów`. Szczegółowe wymagania i zadania zostaną rozpisane przed
zmianą kodu, po analizie obecnego UI, kontraktów API i rzeczywistego przepływu
importu.

## Stan wejściowy

- wersja 0.5 jest zamknięta na `v0.5.16`,
- domyślnym selektorem pozostaje `fast-image-selector-v10.9`,
- niejednoznaczne przypadki zachowują ręczne review i zachowanie fail-closed,
- lokalna kolejka runów selekcji może nadal przetwarzać dane operatorskie,
- `sequence_number` pozostaje wartością domenową i musi być jednoznaczny przed
  kalkulacją Targetu,
- `massImportAllowed` pozostaje zamknięte.

## Pierwszy planowany pion

1. Zinwentaryzować problemy i zbędne kroki w workspace’ach `Gry` oraz
   `Import layoutów` na rzeczywistym przepływie właściciela.
2. Ustalić docelowy przebieg od wybrania gry i źródła do utworzenia,
   obserwowania, wznowienia i odbioru importu.
3. Zaktualizować wymagania Admina, kontrakt API i architekturę tylko tam, gdzie
   wymaga tego zatwierdzony przebieg.
4. Realizować zmiany małymi pionami z testami, bez naruszania historii runów,
   decyzji ręcznych ani trwającej kolejki selekcji.

## Poza automatycznym zakresem

Niewykonane elementy 0.5 — TASK-0208, TASK-0150, TASK-0076, TASK-0080–0089,
pełna publikacja około 500 000 layoutów, kolejne gry i końcowy hardening — nie
przechodzą automatycznie do pierwszego pionu 0.6. Każdy z nich wymaga jawnego
priorytetu, osobnego zadania i aktualnej bramki akceptacji.

## Następny krok

Przygotować pierwsze zadanie 0.6 na podstawie wspólnego przeglądu workspace’ów
`Gry` i `Import layoutów`; przed implementacją zapisać konkretne problemy,
oczekiwane zachowanie i kryteria odbioru.
