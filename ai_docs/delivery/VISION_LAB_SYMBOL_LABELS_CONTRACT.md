# T06a — kontrakt narzędzi etykiet symboli

Status: accepted, 2026-09-27. Niezależny audyt Sol medium: PASS po korekcie trzech P2.
Dokument wykonawczy D-458/TASK-0671. Nie jest zgodą na operacje danych ani trening.
T06a dostarcza narzędzia i adaptery; T06b pozostaje otwarte do uzyskania
rzeczywistych zatwierdzeń. T07 nie rozpoczyna się przez samo ukończenie T06a.

## Stan i granice

Odczytany snapshot 0cdc0770… to folder-v1: 1466 źródeł, 1194 data i 272 historyczne
777 comparison_only, 6 lokalnych gier. Brak records/approved_labels.json i
słowników w manifeście. AnnotationState nie zawiera symboli/słowników.
Stan rev268 / SHA 084bc39de16502de46f6237cbc2fb453a9dc00665ab20d1319301f44f6efa314
pozostaje bez zmian. D-447 dopuszcza lokalne słowniki i lab_human_approved;
D-453/D-456 nie dopuszczają symboli 777 i nie tworzą podziału danych symboli.

Entry T06a: zweryfikowany snapshot i dostępny geometry store, możliwość
bezpiecznego skonfigurowania oddzielnego symbolstore. Puste słowniki/etykiety
nie blokują narzędzia. Entry T06b/T07 nie zostają uznane za spełnione.
Nie otwieramy DB, nie importujemy produkcyjnego training_job/storage/psycopg,
nie zmieniamy geometry state, receipts, fingerprintów ani snapshotu.

## Właściciele i konfiguracja

Nowe symbol_contracts.py (Pydantic, extra=forbid), symbol_labels.py (czysta
kwalifikacja), symbol_store.py (persistencja), symbol_crops.py (render/binding),
symbol_snapshot.py (adapter folder/DB), symbol_cli.py (backup/restore).
Reuse annotations.exclusive/write_atomic/read_checked/digest i
snapshot.canonical/reject_links/safe_file/verify; bez importu eksportera
scripts/vision_lab_export.py, który ma zależności DB.

Nowa opcja --symbols / VISION_LAB_SYMBOLS; brak jawnej konfiguracji oznacza
SYMBOL_DIRECTORY_NOT_CONFIGURED (HTTP 503) tylko dla tras symboli. Brak automatycznego
zapisu w repo albo zgadywania root. Zalecana konfiguracja operatora:
LAB/symbols/<snapshot_manifest_id>. CLI i env rozwiązują absolute path raz
przy starcie. Testowalne create_app(..., symbol_root=None). Root nie może być
równy, wewnątrz ani rodzicem snapshot/annotations/manifests/runs (jeśli
skonfigurowane); kontrola znormalizowanych ścieżek i reparse na przodkach.
Rozdzielenie dotyczy katalogów docelowych, nie wspólnego LAB jako ich rodzica.
GET pustego magazynu zwraca rev0 bez tworzenia katalogu ani blokady symboli; pierwszy zapis
tworzy store. Snapshot mismatch/integrity error nie inicjuje nowego pustego stanu.

Stan: {schema_version:1,snapshot_manifest_id,catalog_digest,revision,
dictionaries,dictionary_approvals,decisions,receipts,history}, koperta {payload,sha256=digest(payload)}.
Nie dodajemy pól do istniejącego AnnotationState. UI ma oddzielnego właściciela
stanu symboli. Snapshoty po rebase nie dziedziczą symbolstore automatycznie.

## Słownik

DictionaryVersion jest niezmiennym rekordem: game_id, version (rosnący int
per gra), digest, entries [{id,code,display_name}], actor, created_at.
Nie przechowuje statusu ani approved_at. Jedynym źródłem zatwierdzenia jest
osobny niezmienny DictionaryApproval: game_id, version, dictionary_digest,
actor, decided_at, revision, request_id. API wylicza status draft|approved
i approved_at z tego rekordu; status nie jest drugim źródłem prawdy.

Pierwszy draft wymaga base_version=null i otrzymuje version=1. Następny
wymaga base_version równego najwyższej zapisanej wersji (także draftowi),
otrzymuje version=base_version+1; konflikt daje DICTIONARY_VERSION_CONFLICT.
Zatwierdzić można tylko najnowszą wersję z dokładnym digestem. Nie można
zatwierdzić starszej wersji, cofnąć aktywnej ani utworzyć drugiego approval
tej samej wersji nowym request_id; identyczny retry obsługuje receipt.
active_approved_version jest wyliczanym maksimum wersji zatwierdzonych,
nie niezależnie zapisywanym wskaźnikiem. Nowy draft nie zmienia aktywnej wersji.

ID lokalne są tokenami [A-Za-z0-9_-]{1,64}; code ma 1–64 znaki, display_name
1–128 znaków po trim. ID i code są unikalne w wersji. Maksymalnie 256 wpisów;
pusty draft jest dozwolony, pusty approval odrzucony. Istniejący ID może
występować w następnej wersji wyłącznie z tym samym code; nazwę prezentacyjną
można poprawić. Usuniętego ID ani code nie można ponownie przydzielić innej
klasie; walidacja sprawdza całą historię. Unknown/unreadable/grid_issue nie
są klasami. Zmiana semantyki wymaga nowego ID i code oraz jawnej decyzji
operatora; backend nie zgaduje semantyki z nazwy.

Approve nowszej wersji oznacza dictionary_stale dla decyzji
starszej wersji, nawet gdy zachowano nazwę klasy. Nie przenosimy approval.
Zmiana semantyki klasy wymaga nowego ID; UI wyjaśnia tę regułę. Brak mapowania
lokalnych ID do DB nie blokuje lab label, ale brak integracji pozostaje jawny.
Nie tworzymy automatycznie słowników z nazw plików/modelu ani zgód za operatora.

Poprawka TASK-0715 upraszcza formularz do samej nazwy. Po jawnym dodaniu wpisu
UI generuje UUID jako id oraz `symbol_<UUID>` jako code, raz, niezależnie od
nazwy. Te pola nie są edytowalne ani wymagane od operatora. Wczytane wpisy
zachowują wszystkie istniejące ID i kody, także o starszym formacie. Przy
zapisie nazwa jest trimowana; pusta blokuje żądanie z toastem. Retry zachowuje
cały oryginalny payload. Nowa semantyka wymaga dodania nowej pozycji; korekta
samej nazwy nie generuje nowej tożsamości. API i zasady wersji są niezmienione.

## Crop i decyzja człowieka

Binding: snapshot_manifest_id,catalog_digest,game_id,source_id,source_sha256,
board_index,geometry_revision,geometry_digest,topology{columns,rows},cell_index,
quad[4 punkty],renderer_version,render_spec_digest,width,height,
pixel_sha256,byte_sha256,crop_id. Współrzędne: obraz po EXIF transpose/RGB
jak Catalog.image; cell_index row-major 0–14 dla 5 × 3 lub 0–8 dla 3 × 3.
Tylko zapisany full_approved/present human geometry i aktualne photo_accepted.
Bez preview_board od klienta i bez interpolacji/propozycji jako referencji.

Renderer lab-symbol-crop-rgb96-v1 wywołuje cell_quads i istniejący crop_cell:
RGB uint8, 96 × 96, quad całkowicie w [0,width-1] × [0,height-1], OpenCV
perspective warp z INTER_LINEAR/BORDER_CONSTANT jak obecny helper.
Wersje opencv/Pillow/EXIF pipeline zapisane w render_spec. Nie przycinamy
błędnego quad do granic; outside_source to brak cropa. Nie używamy stratnego
JPEG preview jako etykietowanego wejścia. Serializacja nowego artefaktu PNG
RGB, compress_level=6, bez metadanych. pixel_sha256=SHA256 surowych 27648
bajtów RGB row-major; byte_sha256=SHA256 dokładnego PNG. crop_id=digest
całego bindingu bez crop_id; oba hashe wymagane i rozdzielone.

Preview zwraca binding i PNG w base64 (limit 256 KiB na PNG), bez trwałego
zapisu. UI pokazuje dokładnie te piksele. Commit przesyła oczekiwany binding,
nie dowolne PNG/path; backend ponownie renderuje i wymaga dokładnej równości
bindingu. Zmiana renderera, geometrii, źródła lub cropa daje HTTP 409, bez decyzji.
Zatwierdzony PNG trafia create-only do crops/<byte_sha256>.png przed atomową
publikacją state. Crop jest zapisywany do pliku tymczasowego na tym samym
wolumenie, flush/fsync i weryfikowany, następnie publikowany create-only.
Nie udostępnia się częściowego pliku pod docelowym hashem. Istniejący
identyczny plik jest retry, inny hash to błąd
integralności. Awaria może pozostawić nieużyty immutable crop, nigdy zgodę
do nieopublikowanego cropa. Brak automatycznego cleanupu.

SymbolDecision jest niezmienna: decision_id=digest(request), origin
lab_human_approved, binding, dictionary_version/digest, symbol_id dla approve,
action approve|unknown|unreadable|grid_issue|withdraw, actor='operator',
revision globalna symbolstore, decided_at UTC z serwera. Aktualna decyzja
per(source,board,cell) wynika z historii; withdraw odnosi się do decision_id.
Stany inne niż approve nie mają klasy i nie kwalifikują próbki. Brak approval
oznacza nieprzejrzane, nie negatywną etykietę. Zmiana klasy to nowa decyzja,
bez nadpisania poprzedniej. Predykcje nigdy nie są requestem approval.

## Atomowość i TOCTOU

Każdy preview/kwalifikujący odczyt/mutacja bierze blokady w jednej kolejności:
1 annotations.exclusive(annotation_root), 2 exclusive(symbol_root), jeśli
symbolstore istnieje lub jest mutowany. Żaden kod nie bierze odwrotnej kolejności.
Pod blokadą geometrii używa AnnotationStore._load() i _view() na kopii albo
małego publicznego read_locked wrappera tych samych funkcji; nie wywołuje
read()/mutate() ponownie (brak reentrantlock). Snapshot geometrii to cały
checksummed payload, nie kilka niezależnych API odpowiedzi. Zamrożona
geometria/source binding jest sprawdzana pod tym samym lockiem co symbol CAS
i publikacja state. Preview token nie daje prawa późniejszego zapisu bez recheck.
Catalog.image ponownie kontroluje source SHA przed decode. Crop i approval
nie mogą się rozjechać z równoległym zapisem geometry.

Mutation: request_id ma 1–128 znaków, expected_revision>=0, actor Literal operator,
op (discriminant). Receipt sprawdzany przed CAS: identyczny ID+canonical
payload zwraca istniejący wynik/revision (z aktualnie wyliczoną kwalifikacją);
inny payload daje REQUEST_ID_CONFLICT. Po zgodnym CAS walidacja, create-only
crop, +1 revision i dokładnie jeden event/receipt, write_atomic. Zajęta blokada daje HTTP 409,
bez ukrytej pętli/zapisu częściowego. Symbolmutacja nigdy nie ustawia
geometry split_stale. Późniejszy geometry drift wyklucza etykietę na odczycie.

## API (proponowane rozszerzenie istniejącej aplikacji)

- GET /symbols?game_id=&source_id=&offset=0&limit=50&read_token=: metadane
  lokalnych decyzji i eksportowanych wpisów DB, z origin, bezpiecznym sample_id,
  label_valid, reasons, training_blockers, total, revision i read_token.
  Sortowanie: source_id, board_index lub board_id, cell_index, origin, sample_id.
  Limit 1–100. Brak filtrów zwraca wszystkie metadane, nigdy obrazy.
  Każda odpowiedź ma trainable=false.
- GET /symbol-dictionaries?game_id=: lista wersji/metadanych słownika,
  ten sam offset/limit/read_token; pełne entries tylko GET
  /symbol-dictionaries/{game_id}/{version}. Ta trasa obsługuje wyłącznie lokalny
  version jako dodatni int. Wpis DB ma origin=db_snapshot i dictionary_digest,
  nigdy lokalny numer wersji. Pełny słownik DB jest zwracany wyłącznie
  w read-only podglądzie db_approved; listy nie mieszają przestrzeni ID.
  Maksymalnie 100 wersji na odpowiedź.
- POST /symbol-crops: discriminated union. kind=lab_cell wymaga source_id,
  board_index,cell_index,expected_geometry_revision i zwraca binding+png_base64.
  kind=db_approved wymaga wyłącznie sample_id zwróconego przez adapter i
  zwraca origin=db_approved, read_only=true, snapshot/source/review/crop
  provenance, byte_sha256, media_type i dokładne crop_bytes_base64 oraz
  dictionary {origin:db_snapshot,digest,entries}. Słownik DB ma limit 256
  wpisów; większy daje DB_DICTIONARY_UNSUPPORTED bez ucinania klas.
  To ograniczenie narzędzia, nie modyfikacja danych lub słownika DB.
  Brak mutacji i receipt w obu wariantach. Nie przyjmuje ścieżki od klienta.
  DB sample_id=digest(snapshot ID oraz dokładnej projekcji approved_labels).
  Lookup pochodzi z checksumowanego eksportu, nie z treści requestu.
- POST /symbols: discriminated union: op=dictionary_draft z game_id,
  base_version|null,entries; dictionary_approve z game_id,version,digest;
  label_decide z binding,dictionary_version,dictionary_digest,action,
  symbol_id|null; label_withdraw z decision_id. Wspólne mutationfields powyżej.
  Wynik {revision,request_id,result_id,replayed,label_valid,reasons,
  training_blockers,trainable:false}. Mutacje etykiet przyjmują wyłącznie
  binding lokalnego lab_cell; DB sample_id/DB dictionary nie może być
  zatwierdzony, wycofany ani przekonwertowany na lab approval tym API.
- POST /symbol-backups z {} -> {backup_id,revision}; operator explicit.
  Brak HTTP restore (nie przyjmujemy ścieżek od klienta).

Nazwy operation_id: list_symbol_labels,list_symbol_dictionaries,
get_symbol_dictionary,preview_symbol_crop,save_symbol_decision,
create_symbol_backup. Closed proxy rozszerzyć o te dokładne metody/ścieżki
i queryallowlist; zachować Host/Origin/JSON/no-store. OpenAPI generuje klient;
wrapper i test requestów w tym samym pionie. Nie tworzymy drugiego serwera.
POST body limit 1 MiB (przed parsowaniem JSON), magazyn maksymalnie 64 MiB
według istniejącego helpera; najwyżej 10000 decyzji bieżących, historia
ograniczona limitem pliku, brak cichego GC. Wyczerpanie limitu daje HTTP 409
STORE_LIMIT_REACHED bez zmian.

read_token jest nieprzezroczystym digestem: wersja schematu widoku, symbol
revision, geometry revision, digest całego geometry payload (w tym rodzin,
kwalifikacji, review i splitu), catalog_digest, snapshot manifest digest,
wersja adaptera oraz kanoniczne filtry i sortowanie. Serwer odtwarza token
pod obiema blokadami przed wyliczeniem każdej strony. Offset>0 wymaga tokenu;
różnica daje PAGE_VIEW_CHANGED (409), bez strony częściowej. Klient zaczyna
od nowa, nie dokleja stron. Dotyczy także listy słowników. W ten sposób
zmiana geometrii/rodziny/holdoutu bez zmiany symbol revision nie jest pomijana.

## Kwalifikacja i holdout

qualify_symbol_sample zwraca label_valid:bool, reasons:list,
training_blockers:list, trainable:false. label_valid oznacza wyłącznie ważną
decyzję człowieka i jej binding, nie kwalifikację do treningu. Wymaga bieżącego
zatwierdzonego słownika, istniejącej klasy, ważnej geometrii/photo review
i zgodnych source/crop hash. Dla DB stosuje odpowiednie niezmienne reguły
eksportowanego review zamiast lokalnej geometrii.

training_blockers zawsze zawiera SYMBOL_SPLIT_NOT_FROZEN. Niezależnie
ujawnia SYMBOL_LABEL_INVALID, SYMBOL_ROLE_EXCLUDED dla comparison_only,
SYMBOL_PROVENANCE_UNRESOLVED przy brakującym lub unresolved pochodzeniu
komponentu, SYMBOL_PROVENANCE_CONFLICT i HOLDOUT_NOT_RELEASED, gdy dotyczą
próbki. 777_v2_declared samo nie dowodzi zweryfikowanego pochodzenia.
Nie przemianowujemy 777 i nie kopiujemy kwalifikacji geometrii. Ważna etykieta
historyczna może być widoczna jako metadata z label_valid=true, ale nigdy
nie ma trainable=true. Nowe lokalne zapisy/preview comparison_only są blokowane
SYMBOL_ROLE_EXCLUDED przed odczytem obrazu. T06a nie implementuje podziału
symboli ani nie uznaje dalszych bramek T06b/T07 za spełnione.

Przed Catalog.image lub czytaniem crop bytes sprawdzić aktualny frozen
geometry split: w D-456 wszystkie źródła gry final_test/unseen_game blokowane
przez game_partitions, nie tylko 63 assignments; dodatkowo komponenty grafu
powiązane z holdout. Stale/malformed split daje HOLDOUT_POLICY_UNRESOLVED,
nie fail-open. Metadata słownika/source może być widoczna, obrazy/cropy nie.
Nie zmieniamy istniejących legacy tras galerii w tym tasku; nowe UI T06a
nie pobiera images/geometry/asset przed tym sprawdzeniem. Brak splitu nie
oznacza automatycznej blokady pustego bootstrapu; jeśli split istnieje,
nie wolno go ignorować. Read metadata ma blocked_reason bez decode.

## Adapter DB — tylko eksport, bez sesji DB

Folder-v1 zwraca db_labels=[]/DB_LABELS_UNAVAILABLE i dictionaries=[];
to normalny jawny brak, nie exception infrastruktury. Dla DB schemaVersion1
snapshot.verify sprawdza manifest/files/frozen_identity; adapter czyta
approved_labels.json (lista projekcji istniejącego eksportera),
records/<game_id>/{symbols,rules_version_symbols,rules_versions,
image_symbol_review_cells,recognized_boards,image_board_search_fast_documents}.jsonl.
Nie importuje exporter/storage. Każdy plik musi być w checksummed files;
path confinement/reparse i limit 64 MiB na plik metadanych, maksymalnie
100000 rekordów. Brak wymaganych metadanych daje DB_METADATA_UNSUPPORTED
i brak ważnych etykiet,
bez zgadywania z symbolId. Uszkodzona checksum/referencja daje integrity error.

Adapter odtwarza warunki _eligible_legacy_label na surowych rekordach,
wiąże projekcję z cell/board/review revision/source i actual copied crop
pod `assets/<crop_relative_path>` w rejestrze snapshotu (dokładnie
_copy_referenced_artifacts eksportera). Sprawdza sourceSHA,
cropSHA, symbol game/status, owner i approved_crop/geometry equality.
Dokładne mapowanie crop_relative_path do eksportowanej ścieżki musi być zgodne
z exporterem, nie dowolną ścieżką systemu. Schemat exportera v1 obsługuje
legacy_file; virtual_source jawnie DB_ASSET_MODE_UNSUPPORTED (bez recropu
i bez podszywania się pod zatwierdzenie nowych pikseli). Słownik DB ma
wersję digest uporządkowanych symbols+rules_version_symbols+rules_versions;
origin=db_snapshot, nie lab approval. Nie mieszamy go z lokalnym słownikiem.
DB decision read-only, origin=db_approved; brak syntetycznego actor/operator
i brak zmiany starego review. Fixtures pokrywają pozytywny eksport i każde
wykluczenie; brak realnych DB danych nie jest fałszywym PASS operacyjnego zbioru.

GET /symbols pokazuje DB provenance i przyczyny wykluczenia. Przycisk
„Podgląd eksportowanej etykiety” używa kind=db_approved; panel nie pokazuje
kontrolek lokalnego approve/withdraw. Przed otwarciem pliku cropa serwer
rozwiązuje sample_id, sprawdza rolę oraz holdout całego źródła/komponentu
pod blokadą geometrii. comparison_only pozostaje dostępne tylko jako
metadane w tym panelu. Następnie sprawdza ograniczoną ścieżkę assets,
reparse, rozmiar (maksymalnie 4 MiB), faktyczny byte SHA zgodny z approved
crop i inventory. Zwraca oryginalne bajty JPEG/PNG, bez recropu/transkodowania.
Media type wynika ze zweryfikowanego formatu obrazu; uszkodzony lub inny
format daje DB_CROP_FORMAT_UNSUPPORTED. Podgląd może dekodować tylko po
przejściu roli/holdoutu; nigdy nie wylicza ani nie udaje lokalnego RGB96 bindingu.
Brak cropa lub błąd integralności blokuje podgląd i label_valid, nie uruchamia
fallbacku do obecnej geometrii. Metadane nie wymagają dekodowania holdoutów.

## Backup, restart i błędy

Backup pod obiema blokadami przygotowuje oddzielny tymczasowy katalog na
tym samym wolumenie: state.json, wszystkie lokalne cropy wskazane przez
historię i checksumowany inventory. Fsync plików, weryfikacja kompletności,
a następnie atomowy rename całego katalogu do backups/<digest(payload)>.
Backup ID jest digestem dokładnego payloadu, bez losowania. Istniejący
kompletny identyczny katalog jest retry; konflikt albo niekompletny cel
jest błędem, bez nadpisywania. Pozostałość tymczasowa po awarii nie jest
publikowanym backupem; ponowienie może użyć nowego katalogu tymczasowego.
Nie wykonuje automatycznego cleanupu. DB snapshot nie jest kopiowany:
inventory przypina jego ID/digest i wymagane immutable pliki; odtworzenie
wymaga tego samego zweryfikowanego snapshotu.
CLI python -m game_predictor_worker.vision_lab.symbol_cli --snapshot ...
--annotations ... --symbols ... backup|restore; restore wymaga --backup-id
i --destination, nowego pustego celu poza korzeniami chronionymi. Waliduje
wszystkie SHA i snapshot binding; nigdy nie nadpisuje aktywnego magazynu.
Restore również buduje i sprawdza katalog tymczasowy, po czym publikuje
jednym rename do nieistniejącego celu. Identyczny kompletny cel jest retry;
jakakolwiek różnica lub częściowy cel daje konflikt bez usuwania plików.
Awaria przed rename nie daje częściowo działającego odtworzonego magazynu.
Odtworzenie nie przywraca geometrii: odczyt ponownie wylicza jej aktualność.
Restart zachowuje słowniki/receipts/decisions/cropy; brak RAMasset zależności.

HTTP 422: schema/enum/zakres. HTTP 404: nieznane source/dictionary/decision.
409: CAS, request conflict, dictionary stale, geometry/crop drift, role
excluded, holdout, limit, lock busy. HTTP 503: nieskonfigurowany root.
Integralność/IO zatrzymują operację z jawnym kodem błędu serwera, bez
konwersji do empty/unknown i bez fallbacku na stary crop. Per-próbka metadata
wyświetla reasons; integrity całego store/snapshotu zatrzymuje cały odczyt.

## UI i testy/odbiór

Panel startuje słownikiem pustym, nie tworzy klas. Jawne „Zapisz wersję”
i „Zatwierdź słownik”; komórka ma approve/unknown/unreadable/grid_issue,
brak autosave/autopredictionapproval. Wyświetla wersję słownika i crop
rzeczywiście związany z zapisem. Actor zawsze operator. Pending blokuje
zmianę źródła/wyjście w aplikacji; retry zachowuje dokładny request_id/payload.
Po konflikcie jawny reload bez automatycznej ponownej zgody. Toasty wspólne
packages/ui, 4 s; monity i zasady zgodne z dotychczasowym labem. Nie uruchamia
treningu, nie tworzy rodzin, nie odblokowuje holdoutów. Aktualne labels
i wykluczenia są paginowane; słownik edytowany wyłącznie dla wybranej gry.

Expected files: nowe moduły powyżej; istniejące api.py/__main__.py,
ewentualny publiczny wrapper annotations.py bez zmiany zapisów; UI
symbol-label-editor.tsx i page/context; lib/boundary.ts; generowany OpenAPI
i packages/vision-lab-api-client wrapper/test. Bez zmian training_job.py.
Testy nowe test_vision_lab_symbol_labels.py, test_vision_lab_symbol_store.py,
test_vision_lab_symbol_snapshot.py; rozszerzenia API/boundary/UI/importtests.
Macierz: pusty bootstrap; słowniki wersje/approval/classconflict; recrop/
source/geometry/dictdrift; 5 × 3 / 3 × 3 i bounds; prediction/unknown; 777; holdout
przed decode; concurrent geometrywriter; CAS/retry/lostresponse; restart;
backuprestore+brakcrop/tamper; DB positive/negative/missing/virtualsource;
legacy payload/receipts/split fingerprints bez zmian; proxy/OpenAPIclient.
Regresje po audycie: zakaz cofnięcia approval i ponownego użycia ID/code;
paginacja podczas zmiany tylko geometrii/rodziny/splitu; DB preview exact bytes
i zakaz local mutate; awaria przed crop/state/backup/restore publication
oraz retry po każdej granicy; label_valid nie oznacza trainable.

Komendy z repo (każda przez Start-Process -WindowStyle Hidden, zapis PID/logów,
WaitForExit(120000), po timeout zakończenie tylko własnego procesu i kontrola
pozostałych procesów):
.venv/Scripts/python.exe -m pytest services/worker/tests/test_vision_lab_symbol_labels.py
services/worker/tests/test_vision_lab_symbol_store.py services/worker/tests/test_vision_lab_symbol_snapshot.py;
Następnie Ruff/mypy zmienionych modułów oraz osobne komendy npm.cmd run
test/typecheck/check:generated --workspace @game-predictor/vision-lab-api-client
(każdy skrypt uruchomiony oddzielnie, nie zapis ze slashem). Dla UI osobno
npm.cmd run test --workspace @game-predictor/vision-lab,
npm.cmd run lint --workspace @game-predictor/vision-lab oraz
npm.cmd run typecheck --workspace @game-predictor/vision-lab.
Repo używa npm@11.18.0, nie pnpm.
Testy wymienione są planowane, nie wykonane. Rzeczywiste zapisy danych
dopiero po audycie kodu; T06b wymaga operatora i osobnego planu operacji.
Ukończenie narzędzi nie oznacza ukończenia zbioru ani nadrzędnego T06.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T06a implementacja narzędzi i adapterów | gpt-6-sol | medium | Konkretny kontrakt pochodzenia i trwałości, bez treningu. | gpt-6-sol, medium |
