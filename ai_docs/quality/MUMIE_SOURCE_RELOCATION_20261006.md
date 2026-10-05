---
title: Mumie — exact source relocation evidence
status: verified
last_updated: 2026-10-06
---

# TASK-0862

The operator supplied the new parent C:\Users\tuszy\Documents\mumie and
declared each newly added directory to be a different film. The old cut
folder now lives below this parent. All2,052 filenames/source SHA match the
qualified inventory exactly. First-folder identity and the independent
third24517–50112 cut folder (2,844 files) are distinct from this relocation.

The create-only sidecar0cff2a15…1e3de4.sources.json binds the same D-502
manifest to its current full source root. Complete metadata verification
precedes feedback pixels; all18 reviewed quads re-render exactly. Labels,
class IDs, samples, whole-family graph, 264/84/9 split, immutable PNG bundle,
manifest identity and existing failed-run settings remain unchanged.
Only direct image reads relocate. Labels/catalog/bundles cannot relocate.
Output overlap checks include the actual source root. No files are moved,
deleted or copied into the previous folder and no junction is created.

Twenty-nine qualification/location tests pass, including full inventory
extra/missing/altered bytes, invalid binding/relative root, removed persisted
location after an earlier read, immutable reviewed PNGs, output overlap and
create-only retry. Twenty-eight old-adapter/training regressions pass,
including exact resumes for generations1/2/3. Ruff format/lint and scoped
mypy pass with the already explicit Torch/ONNX boundary.

Real CLI bind, new-process verify and identical bind retry return the same
manifest0cff2a15ea44aeb2fc77311845ae6d3190060891d65ef1549c4fd5e6d01e3de4.
Original decision revision18 and packc1392fb1…3f8b60 remain immutable.
Separate review checked every acceptance criterion and the plan: no open
P0–P2. Current source content drift still blocks; relocation is not a new
approval or a bypass of the source-integrity gate.

This task repairs read location only. No DB/API/UI changes, training, model
activation, merge/push or deployment. Resume TASK-0861 using the same RGB
run8da05da671d645dd9688c217ef094ce9 with its accumulated budget and admission.
