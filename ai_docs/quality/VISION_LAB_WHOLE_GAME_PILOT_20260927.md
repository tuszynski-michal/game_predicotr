# T03k — pilot geometrii całymi grami D-456

2026-09-27. Wykonawca operacyjny gpt-6-sol / medium. Aktualny etap:
**odczytowa propozycja requestu i manifestu, bez freeze**. Kod T03k tworzy
osobny wykonawca; nie uruchamiano jego testów ani mutacji przed zamrożeniem kodu.
Niezależny audyt exact requestu, dry-run nowej polityki i osobny GO są przed apply.

## Zatwierdzony podział i dokładne identyfikatory

Przydział wynika wyłącznie z zaakceptowanej decyzji D-456, nie z wyników modelu.
Seed 20260927. purpose `geometry`, geometry_policy
`lab-geometry-whole-game-pilot-v1`, measurement_source_ids=[], difficulties={}.

| Gra w katalogu | Dokładny game_id | Partycja | Zdjęcia kohorty | Pełne siatki 5 × 3 |
| --- | --- | --- | ---: | ---: |
| 777 | local-eaf89db7108470dc3f6b23ea | development | 11 | 30 |
| blazing zd | local-8f24e7200f37e017db540839 | development | 10 | 30 |
| gang zd | local-ca1a5075dbd40725f464d429 | development | 11 | 30 |
| mumie wybrane | local-7a0650634c7a607f30c93774 | validation | 11 | 30 |
| reels | local-6348b5c02c3090a3f795c6a5 | final_test | 10 | 30 |
| tresure zd | local-d0e1a94c35b78ceb9211ee6a | unseen_game | 10 | 30 |

Łącznie 63 zdjęcia / 180 pełnych targetów. Development 32 zdjęcia/90 siatek,
validation 11/30, final_test 10/30, unseen_game 10/30. Wszystkie targety
to aktualnie zaakceptowane pełne ręczne 5 × 3; wybrane 777 zachowują skuteczną
własną kwalifikację D-453. Nie dodano żadnych nowych geometrii ani akceptacji.

## Request i manifest proposal

Dokładny request:
`C:/Users/tuszy/Documents/game_predicotr/artifacts/vision-lab/t03k-whole-game-pilot-request.json`.
request_id `d456-whole-game-pilot-rev267`, expected_revision267, actor operator.
Kohorta to jawna lista 63 source_id, game_partitions zawiera dokładnie sześć
identyfikatorów gier całego katalogu. unseen_game_id jest identyfikatorem Treasure
z tabeli. Request nie został wykonany; walidacja nowym typem i dry-run nastąpią
po zamrożeniu kodu T03k. Nie zmieniać ID lub bindings w celu obejścia konfliktu.

Pełny wynik przygotowania, w tym `manifest_proposal`:
`C:/Users/tuszy/Documents/game_predicotr/artifacts/vision-lab/t03k-prepare-pilot-run1.stdout.json`.
Helper odczytowy: `artifacts/vision-lab/t03k-prepare-pilot.py`.

Manifest proposal zawiera wersję, decyzję D-456, politykę, mapę gier,
snapshot_manifest_id, katalogowy snapshot_id, seed, dokładną kohortę oraz
180 rekordów source_id/source_sha256/source_relative_path,
snapshot_image_relative_path, game_id/name, partition, board_index, revision,
topology, wszystkie nodes z provenance i geometry_sha256. Nie zawiera etykiet symboli.
`split_fingerprint` jest jawnie null do czasu rzeczywistego dry-run nowego
freeze; nie wymyślono fingerprintu i nie przedstawiono propozycji jako zamrożonego splitu.

Snapshot manifest ID:
`0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2`.
Katalogowy snapshot_id:
`e8c0cfc703923b1937221d4a86c096d871034707c51bb9873e75fb0051c2d544`.
Ścieżka snapshotu:
`C:/Users/tuszy/Documents/game_predictor_vision_data/snapshots/0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2`.

## Kontrola całego grafu i integralności

Nowy odczyt Catalog potwierdził 1466 źródeł. `build_components` na rzeczywistym
stanie267 uwzględnia wszystkie SHA, siedem rodzin unresolved i related links;
powstało 1017 komponentów. Sprawdzono partycję każdego źródła każdego komponentu,
także bez targetów: **0 komponentów przecina proponowane partycje**.
Nie oznaczano żadnego provenance jako verified; cała gra ma jedną partycję
według jawnej mapy, bez pozornej FamilyDecision dla całej gry.

Stan przed/po identyczny: rewizja267, split null, SHA-256
`f4fabe1790b6922ce297ab61e118371aa3eb91a509606c478d67a7a2b75726ae`.
Ścieżka stanu:
`C:/Users/tuszy/Documents/game_predictor_vision_data/annotations/0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2/state.json`.
Porównano również cały checksummed payload przed/po. Proces PID33956,
exit0, stderr0, limit60s, około9,5s. Nie wykonano AnnotationStore.mutate.

## Odczyt środowiska i wag — bez instalacji

Sprzęt zgłaszany przez nvidia-smi: NVIDIA GeForce RTX 4050 Laptop GPU,
6141 MiB VRAM, sterownik591.62. To sprzęt dostępny do przyszłej konfiguracji,
nie dowód działającego treningu CUDA w bieżącym interpreterze.

Istniejące główne środowisko:
`C:/Users/tuszy/Documents/game_predicotr/.venv`, Python3.12.10,
PyTorch **2.12.1+cpu**, torchvision **0.27.1+cpu**. Odczyt runtime:
torch.version.cuda=null, cuda_available=false, cuda_device_count=0.
numpy2.4.6, onnxruntime1.28.0, pillow12.3.0 są obecne według dist-info.
`pyproject.toml` przypina torch2.12.1/torchvision0.27.1; architektura T04
przewiduje osobne środowisko PyTorch/torchvision z CUDA13.0, bez zmiany głównego.
Nie znaleziono istniejącego oddzielnego pliku constraints przy przeglądzie
nazw plików repo; nie tworzono go ani nie instalowano zależności.

Sprawdzone konkretne lokalizacje nie istnieją:
`C:/Users/tuszy/Documents/game_predictor_vision_data/.venv`, `.../venv`,
`.../checkpoints`, `C:/Users/tuszy/.cache/torch/hub/checkpoints`.
TORCH_HOME nie ustawiony; torch.hub wskazuje ostatnią ścieżkę i pusty cache wag.
Przegląd nieignorowanych plików repo nie zwrócił .pt/.pth/.onnx. Nie oznacza
to braku wag gdziekolwiek na komputerze; nie wykonywano szerokiego skanu dysków.

Dowód runtime: `artifacts/vision-lab/t03k-runtime-readonly.stdout.json`,
PID18904, exit0, stderr0, limit60s, około10s. Importowano istniejące torch i
torchvision wyłącznie dla odczytu wersji/CUDA/cache; bez treningu, inferencji,
pobierania wag, instalacji lub zmiany środowiska.

## Następny krok i ograniczenia

Po code freeze i audycie: zwalidować dokładny request nowym kontraktem,
wykonać dry-run i uzupełnić rzeczywisty split fingerprint, odebrać manifest.
Realny apply wymaga osobnego GO oraz backupu, jednego CAS267, nowego odczytu,
identycznego retry i kontroli całego payloadu. Będzie to odrębna operacja.
Propozycja manifestu nie została jeszcze opublikowana jako zamrożony artefakt
pod danymi labu. Nie uruchamiano testów kodu T03k, usług, freeze ani treningu.
Pilot pozostaje ograniczony do 5 × 3; bez pomiaru czasu, symboli, 3 × 3
i strojenia na final_test/unseen. Nie zmieniono przypisania gier z D-456.

## Dry-run typed requestu po code freeze — PASS

Po sygnale koordynatora wykonano dokładny request przez aktualny
`SplitRequest.model_validate_json` i istniejący `freeze_splits`, wyłącznie
w pamięci. Oczekiwane wejście rev267/SHA oraz SHA pliku requestu sprawdzono.
Źródłowy AnnotationState w pamięci i cały payload na dysku pozostały identyczne.

Wynik ma przyszłą rewizję268, 63 assignments, 180 geometry_target_fingerprints
i partycje90/30/30/30. Measurement pusty; game_partitions identyczne z D-456.
Każdy target manifestu jest zgodny z przypisaniem splitu; katalogowy snapshot_id
i snapshot_manifest_id pozostają odrębnymi, prawidłowymi identyfikatorami.

- Split fingerprint: `3ebcc3a401a17295c5509cbe5d1f59886fa7a87588427c6bed671665dbe63572`.
- Typed request fingerprint: `be7281f865ca83f575335f55b2b129cd56c2c35c9321b397c700dd45650ea0cd`.
- Manifest ID / digest(payload): `1e7cc3a70a583320a1f051ef6598c35595aeefb3b94a60631d311c1da0b25bb0`.

Dokładna koperta manifestu jest w polu `manifest_envelope` artefaktu
`C:/Users/tuszy/Documents/game_predicotr/artifacts/vision-lab/t03k-typed-dryrun.stdout.json`.
Ma postać `{payload, sha256=digest(payload)}`. Payload zachowuje całą pierwotną
propozycję poza `status='frozen'` i rzeczywistym `split_fingerprint` powyżej.
Status frozen jest przygotowaną treścią przyszłego artefaktu, nie deklaracją
wykonania freeze na realnym store. Koperty nie opublikowano pod LAB/manifests.

Proces PID34544, exit0, stderr0, limit60s, około7s. Stan przed i po: rewizja267,
SHA `f4fabe1790b6922ce297ab61e118371aa3eb91a509606c478d67a7a2b75726ae`.
Nie wykonano backup write, AnnotationStore.mutate, realnego freeze, testów
kodu, usług ani treningu. Apply nadal czeka na osobny GO i wymagany odbiór.

## Operacja T03k po audycie i osobnym GO — wykonana

Powyższe sekcje propozycji i dry-run dokumentują stan historyczny rev267.
Po audycie Astra i jawnym GO koordynatora wykonano dokładnie zaakceptowany
request `d456-whole-game-pilot-rev267`, bez zmiany payloadu, identyfikatora,
przypisania gier lub seed. Świeży preview potwierdził rev267, bazowy SHA
`f4fabe1790b6922ce297ab61e118371aa3eb91a509606c478d67a7a2b75726ae`,
brak listenera8102 i brak pasujących writerów. Nie kończono cudzych procesów.

Istniejący `AnnotationStore.backup` utworzył backup przed pojedynczym CAS267:
`C:/Users/tuszy/Documents/game_predictor_vision_data/annotations/0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2/backups/9a24d4d49398759467c7447d9c44226afd1e3f1435335a205ecae4bbe9b46220.json`.
Backup ID / digest bazowego payloadu:
`9a24d4d49398759467c7447d9c44226afd1e3f1435335a205ecae4bbe9b46220`.
SHA pliku backupu jest identyczny z bazowym SHA rev267 powyżej.

Apply zakończył się rev268, history268 i receipts268. Split fingerprint:
`3ebcc3a401a17295c5509cbe5d1f59886fa7a87588427c6bed671665dbe63572`.
Aktualny state.json ma SHA
`084bc39de16502de46f6237cbc2fb453a9dc00665ab20d1319301f44f6efa314`
i digest(payload)
`7765faba543c02090a23828414056c37faae00c986f00d4843d7223f934199b7`.
Nowy odczyt Catalog/read_checked potwierdził `split_stale=false`,
63 assignments i 180 targetów, partycje development90/validation30/
final_test30/unseen_game30. Pozostała treść payloadu jest dokładnie równa
backupowi: wyłączono z porównania wyłącznie split, revision i jeden dokładny
nowy event/receipt. Zachowano 180 anotacji, 63 review, 196 timingów,
436 wpisów rodzin (7 IDs, nadal unresolved) oraz 11 kwalifikacji777.

Dokładną zaudytowaną kopertę opublikowano create-only jako
`C:/Users/tuszy/Documents/game_predictor_vision_data/manifests/1e7cc3a70a583320a1f051ef6598c35595aeefb3b94a60631d311c1da0b25bb0.json`.
Rozmiar402988 B, SHA całego pliku koperty:
`ce9aa3352e78e8ae5b1aa4e98d03a5304e9fd98a7cdbb1dd39bd9442b63c56f3`.
Manifest ID i pole sha256 koperty są digestem payloadu
`1e7cc3a70a583320a1f051ef6598c35595aeefb3b94a60631d311c1da0b25bb0`,
nie SHA całego pliku. Payload jest dokładną propozycją poza wcześniej
zaakceptowanymi status=frozen i split_fingerprint. Nie nadpisano manifestu.

Nowy proces wykonał identyczny retry tego samego requestu: SHA, rewizja,
historia i receipts pozostały bez zmian; manifest był identyczny bajtowo.
Istniejący mechanizm restore odtworzył backup wyłącznie do nowego katalogu
`C:/Users/tuszy/Documents/game_predictor_vision_data/recovery-backups/t03k-restore-rev267-9a24d4d4`.
Odtworzony state.json ma bazowy SHA rev267 i cały payload równy backupowi.
Nie odtwarzano backupu na aktywny store. Końcowa weryfikacja w kolejnym
procesie potwierdziła wszystkie powyższe warunki. Stary store82c3 pozostaje
bez zmian, SHA `22f452d0e976a9997909ece2cf9bede0073f1241574f5880fa7b3ebdbb0e0586`.

Helper operacyjny: `artifacts/vision-lab/t03k-freeze-operation.py`.
Logi poniżej znajdują się pod
`C:/Users/tuszy/Documents/game_predicotr/artifacts/vision-lab/`;
każdy ma parę `.stdout.json` / `.stderr.log`, exit0, pusty stderr,
ukryty proces i kontrolowany limit60s. Nie wystąpił timeout ani przerwanie.

| Log (prefiks) | PID | Wynik |
| --- | --- | --- |
| t03k-freeze-preview-run1 | 36808 | fresh rev267, gotowy |
| t03k-freeze-apply-run1 | 14064 | backup, CAS267→268, publikacja |
| t03k-freeze-replay-run1 | 3000 | identyczny retry bez zmiany SHA |
| t03k-freeze-restore-run1 | 34264 | restore w oddzielnym katalogu |
| t03k-freeze-verify-run1 | 30980 | końcowy nowy odczyt PASS |

Nie instalowano GPU/runtime, nie uruchamiano usług, treningu ani aktywacji.
Nie zmieniono kodu produkcyjnego. Operator nie wykonał commita; dokumentację
wspólną i commit prowadzi koordynator. Niezależny audytor zgłosił postapply
danych PASS oraz odebrał końcową sekcję raportu bez P0–P2. Audyt T03k zamknięty.
