---
title: T05 — audyt i wynik pierwszej hybrydy
status: done
last_updated: 2026-09-27
---

# T05 — pierwsza hybryda D-457

## Zakres i pochodzenie

Wykonawca gpt-6-sol/high, niezależny audyt gpt-6-astra/medium.
T04 v1.7.29 / c8ae5bb711128d1eed5286ed029a7e9dbc35f40a jest bazą.
Pilot D-456 używa wyłącznie geometrii5×3, nie etykiet symboli.
Development:32 zdjęcia/90 siatek (777, Blazing, Gang); validation:
11/30 (Mumie). Reels final_test i Treasure unseen pozostają zamknięte.
Niepełne anotacje nie są etykietami nieobecności; brakujące propozycje
pozostają w mianowniku. Żadnych zgód operatora nie zastępuje predykcja.

Manifest: `1e7cc3a70a583320a1f051ef6598c35595aeefb3b94a60631d311c1da0b25bb0`.
Stan anotacji: rev268,
SHA `084bc39de16502de46f6237cbc2fb453a9dc00665ab20d1319301f44f6efa314`.
Pretrained MobileNetV3Small:10 306 551 B,
SHA `047dcff4addef86ea5bc2eff13c9614dc11f47ab1160d0a71a25e7db994f4e1f`.
Preset `D-457-v1`, digest
`cee25e97bdbeb43d262a05cb306abfdeb288613ac101e722dedbd580e8ed3425`.

## Preflight

Validation:11 unikalnych zdjęć,29/30 targetów dopasowanych;144,844s
sumy czasu dekodowania/propozycji w czterech ograniczonych partiach.
Jedna siatka niedopasowana w źródle
`d28ee875c01cb64c3f39c87cf107b11b10c612e103fec981dcf6499e84a0a825`
(2/3 matched). To wynik dopasowania kandydatów, nie jakość wytrenowanego modelu.
Każdy log ma ten sam digest protokołu, rev268 i SHA stanu; holdout_decodes=0,
started_runs=0. Dowody lokalne:
`artifacts/vision-lab/t05-preflight-validation-{0,3,6,9}.stdout.json`.

Development:32 zdjęcia/90 targetów/75 dopasowanych. Pierwsza większa partia
osiągnęła limit czasu; własne drzewo procesu zatrzymano, kolejne partie
są mniejsze i raportują postęp. Timeout nie jest błędem anotacji.
Niezależny audyt potwierdził komplet i unikalność32/11 sourceIDs względem
manifestu,0 holdoutów i niezmieniony stan. Cztery wcześniejsze logi DEV
zachowują starsze digesty2367…/9a29…; różnice w presetach to późniejsze
jawne pola determinism, letterbox_padding_rgb i reference. Matching,
źródła i preprocessing pozostały bez zmian. Nie przepisywano tych dowodów
na nowy digest; pełne realne runy muszą użyć końcowego cee25e97….

## Audyty i kontrole

- Pre-code: PASS po doprecyzowaniu bindingu protokołu, niezależności
  smoke/train i wspólnego limitu czasu obejmującego eksport/publikację.
- Końcowy audyt kodu/requestów/preflight Astra medium PASS po formalnym
  codefreeze, bez P0–P2. Root wydał GO dokładnie jednego smoke zgodnego
  z zapisanym requestem; train czeka na techniczny odbiór smoke.
- Niezależne30 testów backend (hybryda i RunManager) PASS w44,53s;
  dokładne requesty i rzeczywisty SHA pretrained/registration zgodne.
- Kontrole wykonawcy:16 nowych testów,46 powiązanych backend,36 UI,9 client;
  mypy34, TypeScript obu pakietów, lint/OpenAPI oraz build PASS. Końcowe
  mechaniczne formatowanie skryptu integracji, Ruff i diff-check PASS.
- Syntetyczne CUDA exact resume i ONNX parity PASS; pełna syntetyczna
  integracja registered trainer→checkpoint epoch1/best1→ONNX/bestweights/
  report→odczyt nowym managerem PASS w12,74s. Tempdir,0 zdjęć operatora,
  0 runów LAB. To nie dodatkowe próby pilota.
- Root UI read-only na3102: zatwierdzone777 seq10873-10881, zachowany
  zapis i cropy, przegląd całości domyślnie zwinięty. Selector domyślnie
  Baseline, brak ukończonego modelu przed treningiem. Baseline pokazał
  dziewięć propozycji bez zatwierdzania. Copy odróżnia rolę katalogową777
  od osobnego dopuszczenia geometrii D-453/D-456. Nie zapisano anotacji.
- Szczegółowe testy, codefreeze, wyniki runów i audyt artefaktów:
  do uzupełnienia dowodami przed zamknięciem T05.

## Ograniczenia i odbiór

Rzeczywisty smoke uruchomiony po PASS:
`8b883801a9164eeb9d72474943adf3c1`, request
`d457-hybrid-v1-smoke-20260927`. Pierwszy HTTP request bez Origin został
odrzucony przez middleware przed utworzeniem runu; ten sam idempotentny
request z wymaganym Origin utworzył jeden run. Bez nowego budżetu/retry.
Smoke odebrany technicznie: succeeded434,9289s,10/50 kroków, checkpoint1,
best1. Parity max_delta1,490116e-7, sourcecorner0,00012207px. Nowy proces
sprawdził aktualny manifest i SHA checkpointu/ONNX/bestweights/raportu,
bez importu torch. Worker zakończony; stan anotacji bez zmian.
ONNX SHA `d511a1cb12aaead1cb37f9046c0cc01a34aa92ed6549b6cad29902d1ad9518dd`,
report SHA `43dd00949957c31b80b6855c0717fd63e914ef65e15b65394a8ffeeeaae53925`.
Dowody `artifacts/vision-lab/t05-smoke-{latest,report,fresh-read}.stdout.json`.
Root wydał GO jednego train z dokładnym requestem, świeżym pretrained/head/
optimizer/RNG, bez odziedziczenia smoke i bez zmiany presetu.
Niezależny audyt artefaktów smoke Astra medium PASS bezP0–P2: wszystkie SHA,
protokół, epoch/best1,10kroków, parity i pełne mianownikiDEV90/VAL30 zgodne.
Wyłącznie właściwe partycje, stan i manifest niezmienione,0 image decodes
przez audytora. Train uruchomiony jako `34adda69c29847f389cb92e487d75ca8`,
request `d457-hybrid-v1-train-20260927`, attempt1.
Train zakończony technicznie succeeded568,5283s,20epok/200kroków.
Checkpoint resume to epoka20, wybrany best to epoka1. Dokładnie dwa realne
runy, bez retry, tuningu, trzeciej próby lub aktywacji. Freshprocess odczyt
wszystkich SHA/manifestu PASS, torch_imported=false, worker zakończony,
stan rev268/SHA niezmieniony. Dowody:
`artifacts/vision-lab/t05-train-{latest,report,fresh-read}.stdout.json`.

| Metryka (mniej = lepiej) | Baseline | Hybryda best1 |
|---|---:|---:|
| Development image-macro score | 0,156461470 | 0,153640529 |
| Validation image-macro score | 0,046131665 | 0,046985619 |
| Development valid/missed/invalid | 75/15/0 | 75/15/0 |
| Validation valid/missed/invalid | 29/1/0 | 29/1/0 |
| Development raw NME median/p95 | 0,017048382 / 0,099433992 | 0,013545957 / 0,090710060 |
| Validation raw NME median/p95 | 0,014808585 / 0,036336785 | 0,014148191 / 0,034493513 |

Development score lepszy o1,80%, ale zamrożona nadrzędna metryka validation
gorsza o1,85% względnie (nie punkty procentowe accuracy). Poprawa mediany
i p95 validmatches nie unieważnia braku poprawy image-macro. Mianowniki90/30
obejmują braki z kosztem1. Zero-delta homografia validation0,045842421 jest
osobną referencją, nie baseline. Brak dowodu przewagi hybrydy — rekomendacja:
nie promować i pozostawić baseline domyślny. Bez zmiany wyboru/metody po wyniku.

Checkpoint20 SHA:
`0ddbf6641b2b7d7902039225ff9794221d0b10879b3570018efcb63c38ec98ed`.
Bestweights SHA:
`8b15264f9b955d4b1e9598b211e2a513499e81d81551b65a498b33e7814ef657`.
ONNX SHA:
`d511a1cb12aaead1cb37f9046c0cc01a34aa92ed6549b6cad29902d1ad9518dd`.
Trainreport SHA:
`b3dca6660c385cd375b893aadf21669863ddcfb9e809e05f43414513508558c6`.
Parity: delta1,490116e-7; sourcecorner0,00012207px, PASS.
Bestweights/ONNX są identyczne jak w smoke: niezależny deterministyczny
start dał tę samą epokę1, wybraną jako best. Nie przenoszono uczonych wag,
optim/RNG/history ze smoke; ostatni checkpoint/history runów są odrębne.

Końcowy audyt artefaktów Astra medium PASS bezP0–P2. Niezależny odczyt
weights_only/CPU potwierdził bindingi wszystkich checkpointów, puste
optimizer/history/best{} w obu ep0, tensor-exact ep0 i ep1 między runami,
odrębny last20 i best1 oraz wybór minimum pełnej historii. Dokładnie dwa
runy attempt1, procesy zakończone, budżety zachowane. Audyt nie dekodował
obrazów. Odbiór techniczny nie oznacza przewagi jakości.

Root UI po nowym uruchomieniu aplikacji: domyślny Baseline, po odświeżeniu
listy oba ukończone modele z bestepoch1. Wybrany train34adda69 i żądanie
podglądu na DEV777 seq10873-10881 zwróciły hybrid-mobilenet-v1 i dziewięć
propozycji needs_review/HYBRID_GATE_UNCALIBRATED z cropami. Screenshot
obejrzany; bez zapisów i zgód. Po QA SHA anotacji nadal084bc39….
Nie testowano fizycznego Androida ani restartu całego Windows; nowe procesy,
odczyt zapisanych artefaktów i productionbuild sprawdzone. Serwisy lokalne
8102/3102 pozostawione do podglądu. Konfiguracja ponownego startu w guide.

## Definition of Done i STOP B

- Porównanie development/validation, pierwszy checkpoint w galerii,
  ONNX parity i wymuszony review: spełnione.
- Testy nowego zachowania, regresje, lint/format/typecheck/build i pełny
  kontrakt backend/OpenAPI/client: PASS.
- Oddzielny audyt pre-code, code/request i rzeczywistych artefaktów: PASS.
- Trwałe runy, budżety, restart odczytu, wersjonowane artefakty i niezmienione
  dane: potwierdzone; bez ukrytych zmian produkcyjnych i bez nowych zgód.
- Dokumentacja, Outcome i CURRENT_STATE zaktualizowane. Osobny commit
  `v1.7.30` / `4072dd53a260677e60a24c49f870e7ef1a58c093`;
  staged check/stat/list i show/stat/status PASS,38 własnych plików.
  Cudze zmiany i incidental next-env zachowane poza commitem.
- STOP B. Dalszy etap C wymaga osobnego uruchomienia. Pełny protokół T03
  rodzin/pomiaru pozostaje odroczony. Model nie jest rekomendowany do promocji.

Nie deklarujemy kalibracji confidence, działania nowej gry ani jakości3×3. Gate pozostaje
uncalibrated i wymaga ręcznego review. Brak aktywacji produkcyjnej,
push/merge lub naruszenia holdoutów. Końcem zakresu jest STOP B.
