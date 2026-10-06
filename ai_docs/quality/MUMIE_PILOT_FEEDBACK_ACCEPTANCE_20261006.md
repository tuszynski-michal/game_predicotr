---
title: TASK-0883 — odbiór wspólnego feedbacku Mumii
status: pass
last_updated: 2026-10-06
---

# Zakres i pochodzenie

Entry: TASK-0882, v1.7.224/8b37241fdd6eb9d29b35691d4e91f3d6a88cb18e.
0883 łączy istniejącą wspólną pulę korekt z trwałą ochroną źródeł kontrolnych,
aktualnymi pikselami oraz osobnym eksportem geometrii.
Nie tworzy nowych etykiet człowieka, nie trenował nowego modelu na predykcjach
i nie aktywował modelu w bazie operatora.

## Kryteria odbioru

| Kryterium TASK-0883 | Dowód |
|---|---|
| Aktualne zatwierdzone piksele, bez uczenia predykcji | Current source/revision/render/approval identities; fresh byte→decoded pixel verification; old fingerprints unchanged without pilot descriptor; tests preview/freeze/builder/reuse/first epoch |
| Osobne targets i podział po źródłach | Exact24-node human-approved geometry export; visibility/outside mask; symbol cell cohort; whole-photo alias family; brak obietnicy whole-recording |
|100 rzeczywistych zdjęć w ograniczonych krokach | Zamrożona selection34/33/33;5×20 source handler, każdy krok poniżej20s;900expected/897structurally valid/13455fullcells;99ordered proposals/1unbound |
| Nowy proces i utracona odpowiedź bez duplikatów |0882 durable import/binding receipts;0883 actual PostgreSQL read-only export/resume w nowym interpreterze; controls create-only/fresh retry161existing/0new |
| API/UI/kontrakt/build i regresje | Focused tests, strict typecheck, Ruff/format, Admin request warnings/lint/tsc/build, fresh OpenAPI check; niezmieniony Reviewer zachowuje build i interakcje0882 |
| Konkretne preview i instrukcja | MUMIE_MAIN_APP_DEPLOYMENT_PREVIEW_20261006.md; MUMIE_MAIN_APP_OPERATOR_GUIDE_20261006.md; read-only actual DB/services/virtual Git merge/model availability |

## Nowe bramki

- Protected-source descriptor jest przypięty do gry, kwalifikacji R2
  oraz fingerprintów kohorty/datasetu/config. Chroni24 całe zdjęcia przez
  byteSHA i exif-normalized RGB SHA. Alias po reencoding nadal jest chroniony.
- SQL eliminuje protected source przed istniejącymi limitami64/source i4000/class.
  Weryfikacja faktycznych plików dotyczy wybranych unikalnych źródeł ograniczonej
  kwalifikującej puli; nie dekoduje wszystkich zdjęć przed limitem.
  Nie ma nowego ukrytego admission cap ani fallbacku do niezweryfikowanej cache.
- Brak/drift descriptoru blokuje nowy Mumie TRAIN. Freeze/publish oraz builder,
  ponowne użycie datasetu i pierwsza epoka niezależnie ponawiają ochronę.
  Upload i korekta pozostają dostępne.
- Frozen truth ma127 rzeczywistych ocen:93lab_human_approved i34batch_crop_review,
 136 proof files i jawne mapowanie10 symboli laboratoryjnych do kodów katalogu.
  AI audit chroni źródła, ale nie tworzy truth.
- Promocja nowego production_training porównuje dokładny sourcepixel/dims,
  slot/cell/quad/croppixels i bieżącą ludzką etykietę. Konflikt daje OPEN;
  brak bieżących porównań daje NO_CONFLICT/0. Missing/drift proof to osobny
  integrity error. Nie przepisywać historycznej truth.
- Preview guard jest read-only. Activation lockuje również pending current
  owner rows FOR SHARE. Actual drugi LOGIN UPDATE został zablokowany SQLSTATE55P03,
  a po zakończeniu transakcji przeszedł. R2 lab_import, inne gry i receipt
  replay zachowują wcześniejszy kontrakt.
- Geometry export zachowuje wszystkie24 wartości double bez projekcji/rounding.
  W nowej ścieżce quad musi być dokładnie zgodny, bez legacy tolerance0.01px.
  Każdy obecny revision render jest SHA-verified przed wyborem exact/legacy.
  Usunięcie lattice ze wszystkich snapshotów ze starym SHA nie daje fallbacku.
- Pierwsze zatwierdzenie dobrego geometry0 może użyć aktualnego source lattice
  i manifestu bez zbędnego recrop. Stale/system/unapproved exact lattice nie
  jest human target. Jawna poprawna konwersja do czterech rogów i stara ścieżka
  zachowują wcześniejsze zaokrąglenia oraz fingerprinty.

## Weryfikacja

Receipts: C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-v3-deployment-20261004.
Zbiory testów częściowo się nakładają; nie sumować poniższych liczności.

| Kontrola | Wynik |
|---|---|
| Root geometry/legacy/snapshot final |67PASS/2.04s;0883-root-geometry-final |
| Feedback+existing cohort/dataset/training/catalog |53PASS/34.67s;0883-feedback-regression-root |
| New bounded preview regression |38PASS/15.08s;0883-feedback-bounded-tests |
| Installer preview/restart/concurrency |15PASS/5.75s;0883-controls-installer-final-tests |
| Controltruth/promote+legacyregistry/lab |51PASS/22s;0883-control-truth-tests-final |
| Independent new modules |55PASS/4.76s; auditor fresh interpreter |
| Exactexport app-role PostgreSQL/coldresume |1PASS/15.07s;0883-root-pg-export-final |
| Actual promotionSELECT/locking/teardown |1PASS/17.91s;0883-control-truth-postgres-final |
| Controls prepared apply and fresh retry |161existing/0new;24sources/136proofs/127controls; both real readersPASS |
| Root strict real-import Mypy4modules |PASS47.16s;0883-root-types-final |
| Feedback strict scoped7modules |PASS6.94s;0883-feedback-types-final |
| Controltruth strict real-import Mypy4modules |PASS25.36s;0883-control-truth-mypy-final |
| API composition strict scoped (1233modules) |PASS14.97s;0883-main-types-scoped-progress-final |
| Admin warnings/request4tests,ESLint,tsc |PASS;0883-control-truth-admin-* |
| Admin production build |PASS44.09s;0883-admin-build-final |
| OpenAPI current |PASS14.62s;0883-openapi-check-final |
| Installed grid models777/Mumie |Both available; check-only2.17s;0884-installed-grid-models-preview |

Scoped feedback check zachowuje normalne śledzenie własnych/API/storage
zależności i strict. Pomija analizę implementacji third-party torch/torchvision,
bez globalnego wyłączenia no-any-return. Pierwotne zimne full dependency
checks przekroczyły120/60s; runner zakończył własne drzewa procesów.
Pełnego graphPASS nie wnioskować ze scoped wyniku.
Final composition check jest raportowany osobno w proof.

Niezależny rzeczywisty odczyt24preparedJPEG i127quad→RGB96 powtórzył source/crop
SHA, wymiary i piksele wszystkich frozen PNG.127 exactbindings jest unikalnych,
bez sprzecznych zamrożonych ludzkich etykiet. To kontrola integrity,
nie population accuracy i nie nowy wynik CNN.

## Niezależny audyt

Niezależny gpt-6.1-sol/high audit kodu, rzeczywistych źródeł,
criteria/plan i wszystkich23 receipts zakończył się PASS. Brak otwartych
P0–P2. Dane operatora pozostają niezmienione.

## Dane, usługi i ograniczenia

W bazie operatora nadal0143,0 źródeł/boards Mumii. Nie wykonano migracji,
scalenia MAIN, importu registry, aktywacji ani restartu usług.
Prepared feedback ma final descriptor
25fedbdf124dfd1cf8038addb9f8a176817b2b2361cff62fe0f8f9a18f1d7812.
161 plików zainstalowano wyłącznie pod odrębnym prepared-feedback;
live artifacts/data descriptor pozostał nieobecny.

Full backup/restore bazy operatora nie wykonany. Preview uwzględnia około48GiB
danych i dostępne miejsce; backup i zweryfikowany recovery są warunkiem
0144/0145. RównoległyRGB0878 pozostaje aktywny i wymaga bezpiecznego checkpointu.
Próbny Git merge0882 pokazał dwa konflikty dokumentów; po finalcommicie0883
preview musi używać aktualnego HEAD. Nie jest dowodem wykonania merge.

NN geometry pozostaje propozycją wymagającą review. Brak nowych human labels
całego100-photo zestawu uniemożliwia raport accuracy populacji.
Whole-recording split dla nowych DB uploadów, fizyczny Android i nowy refitV5
pozostają poza tym taskiem.
