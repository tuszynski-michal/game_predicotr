---
title: Supervised representative image ranking architecture
status: accepted
last_updated: 2026-08-18
---

# Architektura rankera reprezentantów

Browser materializuje `manual-image-selection-output-v1.json` po decyzji i
`manual-image-selection-trace-v1.json` dopiero na żądanie. Worker weryfikuje
checksumy względem wskazanych lokalnych folderów, oblicza cechy i zapisuje
content-addressed manifest kohorty. Tabele `representative_ranking_*` są
append-only i nie przechowują obrazów.

`ranker.py` zawiera kontrakty zamrażania, deterministyczny split, trening MLP,
eksport ONNX oraz bramkę promocji. Snapshot przypina wersję cech, model,
checksum, standaryzację i status. `shadow_recommendations` jest wywoływane po
ukończeniu v10.21 na już utworzonych grupach; wynik trafia do diagnostyki, a
decyzja domenowa pozostaje niezmieniona.

Aktywacja przyszłego v10.22 będzie osobnym manifestem i fingerprintem. Do czasu
jawnej zgody właściciela snapshot z innym statusem niż `shadow` jest odrzucany.
