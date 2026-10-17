---
title: Zarządzane bazy treningowe silnika siatki
status: accepted
last_updated: 2026-10-15
---

# Zarządzane bazy treningowe silnika siatki

TASK-1014 rozszerza istniejący magazyn modeli o opcjonalny katalog
`<artifact_root>/models/grid-engine/<profile>/<version>/training-base`.
Operator używa `D:/game_predicotr/artifacts`; worktree musi podać ten root
jawnie, ponieważ domyślne `artifacts` jest względne do bieżącego katalogu.
Nie zmienia to inferencyjnego manifestu, przypisanej wersji ani aktywacji.

Katalog zawiera `checkpoint.pt`, `weights.pt`, `bundle.json`, kanoniczny
`preset.json` oraz checksumowany `receipt.json`. Statyczny rejestr przypina
SHA-256 i rozmiary. Receipt wiąże pełny manifest modelu, run/export/snapshot,
architekturę, fingerprint presetu oraz historyczne ścieżki pochodzenia.
Ścieżki pochodzenia są dowodem, a odczyt zarządzanej bazy ich nie otwiera.

`ManagedGridEngineModelStore.require_training_base(version)` zwraca ścieżkę
checkpointu dopiero po sprawdzeniu inferencji, lineage, receipt oraz hashów
i rozmiarów wszystkich artefaktów. Brak albo korupcja blokuje odczyt.
Domyślne `require` i instalacja bez `--training-checkpoint` zachowują dawny
kontrakt inferencji.

## Instalacja i ponowienie

W worktree repozytorium, PowerShell, z dostępnym środowiskiem Python:

```powershell
$env:PYTHONPATH = 'services/api/src;services/worker/src'
@'
import subprocess, sys
from pathlib import Path
from game_predictor_api.domain.grid_engine_profiles import GRID_ENGINE_PROFILES
lab = Path('C:/Users/tuszy/Documents/game_predictor_vision_data/neural-grid-runs')
for profile, attempt in zip(GRID_ENGINE_PROFILES, ['attempt-1', 'attempt-3'], strict=True):
    version = profile.current
    source = lab / version.run_id / 'exports' / version.export_id
    checkpoint = lab / version.run_id / attempt / (version.checkpoint_sha256 + '.pt')
    subprocess.run([
        sys.executable, 'scripts/install_grid_engine_models.py',
        '--artifact-root', 'D:/game_predicotr/artifacts',
        '--source', version.profile.value + '=' + str(source),
        '--training-checkpoint', version.profile.value + '=' + str(checkpoint),
    ], timeout=120, check=True)
'@ | .\.venv\Scripts\python.exe -
```

Ta instrukcja dotyczy obecnych dwóch baz `v1`. Nowe wersje wymagają własnych
zweryfikowanych źródeł i wpisu rejestru; nie wyszukują „najnowszego” pliku.
Instalator weryfikuje źródła przed zapisem, wymaga rezerwy 5 GiB i korzysta
z blokady OS zwalnianej po awarii procesu (oczekiwanie najwyżej 10 s).
Plik `.training-base.lock` pozostaje w katalogu wersji po instalacji.
Jest nieszkodliwy: stan blokady przechowuje OS, a sam plik nie jest
przeterminowaną dzierżawą i nie wymaga usuwania przed retry.

Instalacja i odczyt odrzucają dowiązania oraz junction w całej ścieżce,
także powyżej `artifact_root`. Root umieszczony pod junction zostanie
odrzucony nawet przy poprawnych artefaktach; należy użyć zwykłej ścieżki.
Obecny `D:/game_predicotr/artifacts` jest zwykłym katalogiem.

Kopia przechodzi przez `.training-base.installing` i pliki `.partial`.
Retry zachowuje ukończone pliki dopiero po pełnej weryfikacji SHA i rozmiaru.
Niepełny plik kopiuje od początku; wznowienie odbywa się per plik, nie per
bajt. Receipt stagingu musi zgadzać się z modelem i pierwotnymi źródłami.
Odmienny receipt, obcy katalog lub dowiązanie blokuje zapis. Instalator nie
naprawia ani nie nadpisuje odmiennego opublikowanego pakietu. Przerwane
inicjalizacje receipt mogą pozostawić mały katalog `.training-base.receipt-*`;
jego usunięcie pozostaje oddzielną operacją, nie automatycznym cleanupem.

Kompletny staging jest publikowany jednym rename na tym samym wolumenie.
Nie wolno ręcznie kopiować części plików do `training-base`.
Gwarancja odmowy rename do istniejącego katalogu dotyczy Windows.
Na POSIX pusty katalog może zostać zastąpiony; OS lock chroni współpracujące
instalatory, a nie niezależne procesy ręcznie zmieniające katalog.

Błąd I/O może zostać zgłoszony przez CLI jako surowy traceback z niezerowym
statusem zakończenia. Nie jest sukcesem; własny staging pozostaje do retry.
Nie rozszerzamy w TASK-1014 istniejącego kontraktu błędów CLI.

## Odczyt bez źródeł na C

```powershell
$env:PYTHONPATH = 'services/api/src;services/worker/src'
@'
import subprocess, sys
subprocess.run([
    sys.executable, 'scripts/install_grid_engine_models.py',
    '--artifact-root', 'D:/game_predicotr/artifacts', '--check-training',
], timeout=120, check=True)
'@ | .\.venv\Scripts\python.exe -
```

Wynik tej kontroli potwierdza integralność, nie jakość nowego modelu ani
wykonanie treningu. [Raport rzeczywistej kopii i odczytu CPU](../quality/MANAGED_GRID_BASES_20261015.md)
zachowuje dowody TASK-1014. Pliki źródłowe na C pozostają zachowane;
nie ma zgody na cleanup, kopiowanie korpusu, trening lub aktywację.
