---
title: TASK-1014 — Kopia baz siatki na D i odczyt z nowego procesu
status: accepted
last_updated: 2026-10-15
---

# TASK-1014 — Kopia baz siatki na D

Odwracalna kopia została wykonana w zatwierdzonym zakresie rewizji 6.
Operator root: `D:/game_predicotr/artifacts`. Każdy profil zachowuje wersję
`v1`, istniejący pakiet inferencji i aktywację. Inferencyjne manifesty miały
identyczny SHA-256 przed i po instalacji. Nie zmieniono bazy operatora,
nie uruchamiano usług, treningu, inferencji ani GPU. Źródeł C nie usunięto.

## Źródła i artefakty

### grid_profile_777_v2 / v1

- Źródłowy checkpoint: `C:\Users\tuszy\Documents\game_predictor_vision_data\neural-grid-runs\43933ac8d7d443c8b9079630a83de2e6\attempt-1\2cd19738367121e6a36cf0630b4fd7d275d1966fbe25ca73d1329fa979183fe8.pt`.
- Docelowy katalog: `D:\game_predicotr\artifacts\models\grid-engine\grid_profile_777_v2\v1\training-base`.
- Receipt: `D:\game_predicotr\artifacts\models\grid-engine\grid_profile_777_v2\v1\training-base\receipt.json`.
- Run: `43933ac8d7d443c8b9079630a83de2e6`; export: `2cd19738367121e6-round3`.

| Plik | Rozmiar B | SHA-256 |
|---|---:|---|
| checkpoint.pt | 106729511 | `2cd19738367121e6a36cf0630b4fd7d275d1966fbe25ca73d1329fa979183fe8` |
| weights.pt | 26815171 | `19b8d1382d5fe13b7e054b2d4eb846c25f7a91f680fa113b7d1d30571cdc80f9` |
| bundle.json | 5336 | `64d815d8af168f79fd53f0dcb9e80823c3006ebae3e08225fc9e25f178c27b7b` |
| preset.json | 3637 | `77e6b9ce792798b58b4c403d6d482fdfd4be43d16d3455cfe8af1345dd7381d3` |

### grid_profile_mumie_v1 / v1

- Źródłowy checkpoint: `C:\Users\tuszy\Documents\game_predictor_vision_data\neural-grid-runs\5bc981568c3f42bd96f6f9238e57aedc\attempt-3\f896da7196431be2d6dc7b863cfa69f6ec27fd63cb3d3e00ff7acd1f2b745138.pt`.
- Docelowy katalog: `D:\game_predicotr\artifacts\models\grid-engine\grid_profile_mumie_v1\v1\training-base`.
- Receipt: `D:\game_predicotr\artifacts\models\grid-engine\grid_profile_mumie_v1\v1\training-base\receipt.json`.
- Run: `5bc981568c3f42bd96f6f9238e57aedc`; export: `iteration03-f896da7196431be2`.

| Plik | Rozmiar B | SHA-256 |
|---|---:|---|
| checkpoint.pt | 53663320 | `f896da7196431be2d6dc7b863cfa69f6ec27fd63cb3d3e00ff7acd1f2b745138` |
| weights.pt | 26815171 | `473d773897aae999f2a86774d77c1139f62f36fc9b8eb80a17f68256016613a1` |
| bundle.json | 7243 | `024dc1f0d5bc46515cb4173e04c474ea864d730b4d48abd6f418bacfa9b43566` |
| preset.json | 5398 | `946b5a6cb75d836c61f2a549d0e338f4175eae1e906d26a211428ec2f6181317` |

## Weryfikacja trwałości

Osobny proces Python odczytał oba checkpointy poprzez
`ManagedGridEngineModelStore.require_training_base`, następnie neutralny
`training_core.checkpoint.load_checkpoint` na CPU (`weights_only=True`).
Odczytał także eksportowe `weights.pt` na CPU. Oba checkpointy mają
`schemaVersion=2`, `resumeMode=completed_epoch`; każdy stan modelu i eksport
ma 670 kluczy. Nie przywracano optimizer/RNG i nie wykonywano kroku treningu.
Python audit hook odrzucał każdy `open` ścieżki zawierającej
`game_predictor_vision_data`; wynik potwierdza odczyt wyłącznie z D.
Historyczne ścieżki w receipt nie są odczytywane przez resolver.

Miejsce na D: 1358091235328 B przed kopią,
1357877149696 B po kopii; wymagane 5 GiB rezerwy zachowano.
Logi poleceń, dokładne źródła i dowody w ignorowanym katalogu worktree:
`artifacts/audits/TASK-1014_REAL_COPY.json` oraz
`artifacts/audits/TASK-1014_NEW_PROCESS_READ.json`.
Trwałe receipts są w docelowych katalogach na D, poza Git.

To dowód integralności i odczytu w nowym procesie, nie restartu Windows,
nowej oceny jakości, treningu ani prawa do cleanupu C. Testy instalatora
obejmują crash procesu pod OS lockiem i wznowienie per plik, konflikt obcego
katalogu, korupcję i niezmienność inferencyjnego manifestu.

[Instrukcja operatora](../guides/MANAGED_GRID_TRAINING_BASES.md).
