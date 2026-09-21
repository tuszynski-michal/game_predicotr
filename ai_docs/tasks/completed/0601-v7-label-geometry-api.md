---
title: TASK-0601 V7 label geometry calibration API
status: done
---

# TASK-0601 — API, OpenAPI i klient kalibracji geometrii etykiet V7

## Status

done

## Goal

Lokalny Admin API tworzy i wznawia wyłącznie server-owned sesje kalibracji,
udostępnia bezpieczny obraz po normalizacji EXIF oraz wyprowadza profil wyłącznie
z niezmiennego snapshotu, bez odblokowania V7.

## Context

TASK-0600 zapisał framework-free stan sesji, ale nie pozwala jeszcze UI wybrać
źródła, zobaczyć obrazu ani wysłać operacji. HTTP musi zachować granicę:
przeglądarka nie podaje ścieżki, nazwy pliku ani danych źródła; konfiguracja
operatora wskazuje manifest korpusu, a API rozwiązuje przypięte SHA po swojej
stronie.

## Dependencies / entry conditions

- TASK-0599 i TASK-0600 są ukończone; `v7-calibration-v2` wymaga pięciu SHA,
  dwóch grup ujęć i `contained` dla każdego slotu profilu.
- D-409 rezerwuje `reels_test`: split `holdout` nie może utworzyć sesji ani
  udostępnić assetu przez ten pion.
- Założenie D-413: pierwsza wersja API zapisuje profil, ale nie pozwala HTTP
  tworzyć adopcji. Adopcja wymaga niezależnego raportu walidacyjnego z TASK-0605;
  endpoint listy ma więc charakter odczytowy i zwraca pusty katalog do czasu
  tej walidacji.

## Recommended execution

`gpt-5.6-terra` z `xhigh`, końcowy review `gpt-6-astra` z `medium`. Zmiana
warunków profilu, dopuszczenie ścieżki z przeglądarki, holdoutu lub utworzenie
adopcji bez raportu walidacyjnego wymaga eskalacji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `.tmp/V7_LABEL_GEOMETRY_CALIBRATION_UI_PLAN.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- Konfiguracja operatora manifestu korpusu i server-owned runtime root.
- Resolver przypadków `calibration` jednej rodziny, przypiętych do sesji po
  `caseId` i SHA; odrzucenie holdoutu, reference-only, nieznanego przypadku,
  junctionu/dowiązania, unsafe manifestu i checksum driftu.
- Router, modele OpenAPI i obsługa błędów dla create/read/operate/export
  sesji, canonical assetu oraz listy/odczytu/profilu geometrii.
- Normalizacja EXIF z bajtów zweryfikowanych SHA i zwracanie obrazu PNG bez
  ujawniania ścieżki źródła.
- Niezmienny profil z eksportu dokładnej rewizji oraz regeneracja sprawdzonego
  klienta Admin API.

## Out of scope

- Ekran Admina, IndexedDB, ręczne klikanie i rzeczywiste anotacje.
- OCR, observer, jakość, ranking, output JPEG, aktywacja V7 i zmiana bramki.
- Tworzenie adopcji; TASK-0605 najpierw musi utrwalić i zweryfikować raport
  walidacyjny dla własnego korpusu gry.

## Acceptance criteria

- [x] Żądanie sesji przyjmuje wyłącznie `geometryFamilyId` i identyfikatory
  przypadków z operator-owned manifestu; źródła są calibration-only i należą
  do jednej rodziny.
- [x] Asset jest dekodowany z jednorazowo odczytanych, checksummowanych bajtów,
  normalizuje EXIF i nie akceptuje ani nie zwraca ścieżki; drift trwale blokuje
  sesję.
- [x] Mutacja zachowuje receipt-before-revision, wynik eksportu i profil wiążą
  dokładną rewizję oraz snapshot; profil niespełniający bramki nie jest
  zapisywany.
- [x] OpenAPI i wygenerowany klient zawierają wszystkie endpointy; mutacje są
  chronione istniejącym `LocalAdminIntent`.
- [x] V7 start nadal zwraca `SEMI_AUTOMATIC_SELECTION_V7_BLOCKED`.

## Technical notes

- `GAME_PREDICTOR_V7_LABEL_GEOMETRY_CORPUS_MANIFEST` jest opcjonalną
  konfiguracją operatora. Bez niej endpointy kalibracji zwracają kontrolowane
  `V7_CALIBRATION_CORPUS_UNAVAILABLE`, a V7 nie otrzymuje fallbacku.
- `sourceId` ma postać pochodnej z `caseId` i SHA; jest resolve'owany wyłącznie
  przez przypiętą sesję. API porównuje bieżący fingerprint całego manifestu i
  aktualny inwentarz źródeł z sesją przed odczytem, mutacją, eksportem i
  profilem. Różnica utrwala `blocked_source_drift`.
- Canonical asset pozostaje pochodną w pamięci. API najpierw odczytuje plik do
  pamięci, weryfikuje SHA tych samych bajtów, a potem wykonuje
  `ImageOps.exif_transpose`; nie serwuje pierwotnego JPEG-a przez `FileResponse`.
- Profil jest content-addressed i zawiera checksumę eksportu sesji. Zapis profilu
  następuje dopiero po `calibrate_v7_label_geometry` i statusie `passed`.
  Adopcje są tylko odczytywalne do TASK-0605, aby dowolny SHA z żądania nie
  stał się pozornym raportem walidacyjnym.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/{config.py,main.py}`,
  `api/router.py`, `security/local_admin.py`, `v7_calibration_sessions.py`,
  `scripts/export_admin_openapi.py`, `packages/admin-api-client/openapi/`.
- Nowe: API application service, router, schemas i testy V7 label geometry.

## Test cases

- Manifest calibration `777` → session z dziewięcioma slotami na SHA; request
  `reels_test`/holdout → stabilny błąd bez stanu.
- Operacja, utracona odpowiedź i ponowienie → ten sam receipt; rewizja nie
  zmienia się drugi raz; inny payload z tym UUID → konflikt.
- Zmiana JPEG-a, nazwy/katalogu albo manifestu po utworzeniu → asset/mutacja
  odmawia i trwałe `blocked_source_drift` pozostaje po restarcie; identyczny
  inwentarz pod innym fizycznym korzeniem także blokuje sesję.
- Symlink/junction i `..` nie prowadzą do odczytu assetu; błędna checksum
  assetu jest konfliktem.
- JPEG z EXIF orientation → PNG ma kanoniczny wymiar/orientację; odpowiedź nie
  zawiera ścieżki systemowej.
- Kompletna sesja → immutable profil; niekompletna lub p95 > 0.04 → profil nie
  jest zapisany; start V7 pozostaje zablokowany. Zapis eksportu działa również
  pod długim katalogiem tymczasowym Windows.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr, timeout 120 s
.venv\Scripts\python.exe -m pytest --basetemp .tmp\pytest-task-0601 services/api/tests/test_v7_label_geometry_calibration_api.py services/api/tests/test_openapi_contract.py services/worker/tests/test_v7_calibration_sessions.py -q
.venv\Scripts\python.exe -m ruff check <zmienione-moduły-i-testy>
.venv\Scripts\python.exe -m ruff format --check <zmienione-moduły-i-testy>
npm run openapi:check
npm run test --workspace @game-predictor/admin-api-client
```

## Risks / open questions

- Konfiguracja manifestu jest świadomym działaniem operatora, lecz nie jest
  produkcyjną aktywacją V7. UI TASK-0602 pokaże brak konfiguracji jako stan
  blokujący i nie będzie wybierał folderu.
- W systemie plików innym niż lokalny NTFS resolver fail-closed odrzuca
  dowiązania/reparse points; nie jest to obsługa udziału sieciowego.

## Outcome

### Changed

- Dodano server-owned API, konfigurację i bezpieczny resolver korpusu dla sesji
  kalibracji, canonical PNG po EXIF oraz content-addressed profile.
- Rozszerzono trwały eksport o dokładny snapshot rewizji i dodano kontrolę
  tożsamości profilu, fizycznego korzenia korpusu oraz junctionów w przodkach.
- Wygenerowano OpenAPI i dodano komplet publicznych wrapperów/typów klienta
  Admina dla sesji, operacji, assetów, eksportów, profili i adopcji read-only.

### Verification results

- Skoncentrowane testy API/konfiguracji/sesji/kalibracji, Ruff i compileall
  przeszły; test blokady startu V7 pozostaje w
  `services/api/tests/test_semi_automatic_image_selections.py`.
- Własny audyt końcowej regresji wykrył i poprawił zapis eksportu pod długą
  ścieżką Windows; regresja profilu niepełnej sesji przechodzi po poprawce.
- `npm run openapi:check` przeszedł, a klient Admina zbudował się i przeszedł
  58 testów. Astra Medium wykonała audit oraz re-audit: pięć uwag P2 poprawiono,
  końcowo brak P0–P2.

### Not completed

- Nie powstał ekran ani IndexedDB (TASK-0602), adnotacje rzeczywistego korpusu
  (TASK-0603) ani zapis adopcji (TASK-0605). Bramka V7 pozostaje zablokowana.

### Documentation updates

- Zaktualizowano kontrakt API, decision log, stan projektu i lokalną instrukcję
  konfiguracji operatora.

### Recommended next task

- TASK-0602 — ekran Admina i kolejka operacji użytkownika.
