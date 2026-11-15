---
title: Pomiar tempa nauki uczenia korekt siatek (TASK-1207)
status: accepted
last_updated: 2026-11-13
---

# Pomiar tempa nauki uczenia korekt siatek (TASK-1207)

Cel: sprawdzić, czy niższe tempo nauki (`learning_rate` 2e-5 zamiast 1e-4 presetu
`grid-corrections-v1`) zapobiega pogorszeniu modelu przy ponownym uczeniu (D-612).

Metoda: dwa przebiegi trenera z gałęzi TASK-1205 (z progiem kroku 0) na GPU RTX 4050,
uruchomione plikowo poza kolejką jobów (bez bazy i rejestracji), z tą samą specyfikacją,
ziarnem i kohortą co oryginalne runy; zmieniono tylko tempo nauki. Metryka: VALIDATION
`boardCorrectRate` (photo-macro) reguły wyboru checkpointu.

| Przebieg | Baza (krok 0) | 600 | 1200 | 1800 | Koniec |
|---|---|---|---|---|---|
| `abe39bce` + kohorta `7e239be4`, 1e-4 (oryginał `fedc6bcf`) | 0,678 | 0,573 | 0,520 | 0,573 | 0,626 po 3600, kandydat `01767a49` |
| `abe39bce` + kohorta `7e239be4`, 2e-5 (`ef35e01a`) | 0,678 | 0,573 | 0,573 | 0,573 | early stop, `GRID_TRAINING_NO_IMPROVEMENT` |
| `bf327cfa` + kohorta `0630f2cc`, 1e-4 (oryginał `2d2c2085`) | 0,743* | 0,681 | **0,806** | 0,743 | kandydat `abe39bce` |
| `bf327cfa` + kohorta `0630f2cc`, 2e-5 (`535a4302`) | 0,743 | 0,743 | 0,743 | 0,681 | early stop, `GRID_TRAINING_NO_IMPROVEMENT` |

\* krok 0 oryginalnego runu nie był mierzony; wartość z pomiaru 2e-5 (ta sama baza i
VALIDATION).

Wnioski:

- Niższe tempo nie zatrzymuje spadku `abe39bce` (0,678 → 0,573 już po 600 krokach przy
  obu tempach), a w przypadku, w którym 1e-4 dało realną poprawę (0,743 → 0,806), 2e-5
  nie daje żadnej. Tempo nie jest przyczyną; zostaje 1e-4.
- Kontynuacja z modelu korekt sama w sobie nie szkodzi: `bf327cfa` też pochodził z
  presetu korekt. Różnica to ilość nowych danych: 179 nowych plansz TRAIN w `0630f2cc`
  wobec 45 w `7e239be4`. Przy małym przyroście trening odchodzi od checkpointu wybranego
  na małej VALIDATION (16–19 zdjęć), co jest zgodne ze zjawiskiem „szczęśliwego szczytu”
  przy wyborze najlepszego kroku.
- Próg kroku 0 (TASK-1205) zadziałał na prawdziwych danych w obu przebiegach: brak
  kandydata zamiast gorszego modelu.

Artefakty: `artifacts/grid-training/runs/ef35e01a-3161-5f55-b739-7867a0ced45f` i
`535a4302-b7b8-5b6e-8fcd-7c329513be08` (po ~228 MB, plik `MEASUREMENT.txt`; do usunięcia
przez operatora).
