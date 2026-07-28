# Local manual imports

Umieść tutaj pliki `.csv` albo `.jsonl` zgodne z `layout-import-v1`.

Admin API przyjmuje wyłącznie ścieżkę względną wobec tego katalogu. Zawartość
plików jest lokalna i ignorowana przez Git; ten plik zachowuje sam katalog w
repozytorium.

Deterministyczny plik akceptacyjny M4 można odtworzyć na Windows:

```powershell
npm run m4:import:fixture
```

Pełny test 500 000 rekordów używa osobnej bazy
`game_predictor_m4_acceptance_test` i osobnego katalogu artefaktów:

```powershell
npm run m4:import:acceptance
```

Udany przebieg usuwa bazę testową. Błąd zachowuje ją do bezpiecznego retry i
diagnostyki; nie modyfikuje bazy deweloperskiej.
