# Pełne grafiki — odbiór T1–T4

2026-11-09. Końcowy odbiór narzędzia po T4 focused R2 PASS; nie dopuszczenie modelu.
Polecenia/logi i granice: `TASK-1173_VERIFICATION.md` oraz raporty T1–T3.

| Kryterium planu | Dowód i granica |
|---|---|
| Brak odrzuconych obrysów | Brak quadu nie rysuje prostokąta; unknown/fragment nie udaje pełnego symbolu. T1 i T4 ordinary export. |
| Wspólne granice i perspektywa | Dokładne zapisane24punkty; niezależne obrysy różnych rozmiarów. Brak regularnej siatki zastępczej. |
| J/10/ramki/ciemne grafiki | Rzeczywiste540PNG8%/0%, source i wejścia NN; instrukcja obejmuje ozdobne obramowanie bez tła/sąsiada. Approved J/10 ma test obrysu/klasyfikacji. Pilot bez approved content/class GT nie dowodzi pełności tych grafik. |
| Sąsiad/przycięcie | T2 nie kompensuje uszkodzeń inną poprawą; T3 D597 sprawdza realne rastry. HTML pokazuje assessment, jeżeli istnieje. Unknown bez oceny. |
| Brak rzędu/błędna geometria | Człowiek/model oddzielnie, rzeczywiste wejścia, missing/ambiguous oraz jawny incorrect match i false detections względem zapisanych punktów. Partial whole-photo None pozostaje brakiem oceny. DOM z actual evaluator, w tym position7/label0. Found index nie udaje usable index ani ID planszy. |
| Ochrona blind/korekt | TRAIN+visualExportAllowed przed pikselem/public JSON; A/B/REG poza galerią. File-only ochrona na moment capture, bez sprawdzania późniejszych blind sessions; świeży capture przed kolejną galerią. Ordinary bez zapisu, blind bez hintów. Prawdziwy PG alias/other-slot read-only. |
| Restart/replay/currentness | T1 revision/render pins; T2 immutable replay; T3 receipt/preflight/ledger i PG advance. T4 cold CLI bez PYTHONPATH i identyczne wejścia/output po nowym procesie. |
| Klasyfikacja | Klasa człowieka i zgodna/błędna dla obu marginesów tylko przy aktualnym dowodzie. Pilot bez GT/historyczny unclassified classifier nie poświadcza poprawy modelu. |
| Legacy/UI | Legacy CLI3PASS/Worker39PASS; hidden edit zablokowany; bez nodes ordinary obraz/adnotacja zachowane. Zielone przyciski i jasne opisy. |
| Kontrole | Pion pytest/Admin/PG, lint/types, DOM, cold CLI/PNG i kolekcja Worker. Geometry ma10baseline+przejściowy picker; osobno PASS. Po R1 Worker16/Canvas28PASS, kolekcja3639/19,20s; końcowy standardowy build PASS exit0/28,64s (root receipt). Pierwsza próba ma granicę helpera. Root docs/map/focusedR2 przed commitem. |

Finalny raport:
`D:/game_predicotr/artifacts/grid-symbol-crop-preview-20261109-t4-v4/index.html`.
Jedno TRAIN zdjęcie/9plansz wystarcza do odbioru narzędzia; bez rozszerzania do45.
Human/model mają osobne geometrie. Wejścia NN są per źródło/stage, bez zgadywania
ID. Brak approved GT oznacza not_evaluable. Ręcznego odbioru strony nie wykonano:
CUA blokowała file://, pojedyncze obejrzane PNG nie zastępują odbioru całego HTML.

## Przyjęte ograniczenia

- T1 P2-4: ochrona dotyczy ról wybranej kohorty i zapisanych sesji blind,
  nie wszystkich przyszłych wyborów/globalnej historii ekspozycji. T4 jej
  nie rozszerza. T1 P2-7/8 naprawiono z regresjami.
  T4 P2-5: file-only galeria respektuje stan ochrony z capture; nie sprawdza
  blind sesji zapisanych później. Przed kolejną galerią wymagany świeży capture.
  Nie dodano SQL/API do renderera; dawne pliki mogą pozostać historycznie dostępne.
- T2 P2-5: LAB temperature-only calibration nie ma rozpoznanej polityki,
  daje not_evaluable przy zachowanych licznikach. P2-6: blacklist nie obejmuje
  wszystkich maszynowych aktorów, ich decyzje nie są ludzkim GT. P2-7:
  zachowane assignment_source może konserwatywnie dać unavailable. P2-8:
  niejednoznaczny pomiar u/delta nie daje dowodu; D597 ma tylko opisany,
  sprawdzony wyjątek diagnostyczny. P2-9 przestrzeni indeksów rozdziela T4.
- T3 P2-1: koszt resolvera per-board niezmierzony, bez cache. P2-4: długi
  rzeczywisty workflow1200step bez PASS: T3 Windows native Adam/timeout120s,
  unchanged main timeout60s przy ledger fsync. Odmienne objawy, przyczyna
  nieustalona; nie udowodniono wspólnego baseline Torch i nie powtarzano w T4.
- T3 P2-5: D597 wymaga pełnej widoczności, nie kwalifikuje fragmentów. P2-7:
  duży fixture PG ma warunkowe v2 asercje; osobny mały advance/oracle/JSONB
  i cold replay są właściwym dowodem. P2-8: Admin v2 może blokować TRAIN bez
  rodowodu; operator zawęża wybór źródeł.
- Inventory T3 jest kohortowe, nie globalne. Live szkice nie są approved GT
  ani frozen referencją. Nie uzupełniono automatycznie content/render pinów
  ani klas. Brak LAB iteration pozostaje luką pomiaru.

Brak mutacji operatorowych etykiet/DB, modeli, marginesu, importu691,
treningu/GPU, aktywacji, usług i wdrożenia. Bez migracji/API zmiany T4.
T1–T4 mają niezależne terminalowe Opus PASS; zamknięcie wykonuje root. Merge/push wymaga osobnej zgody.

## Końcowy odbiór root — 2026-11-09

Focused R2 przez terminal: **PASS, 0 P0 / 0 P1**, rzeczywisty model główny
`claude-opus-5-5`, High żądane (bez niezależnego dowodu ustawienia effort).
Czas243,62s; receipt potwierdzony po rzeczywistym zakończeniu procesu.
Pakiet SHA `293ed2a525aa0176ef022b1890705afd7e4c352736518203abccb1c68b93f45a`;
raport SHA `de0b237218f0719c5c3e43cd76b2daabee88c7f6496b8479e87ad051dafa2186`.
Raport i receipt: `TASK-1173_AUDIT_claude-opus-5-5.md` i plik `.receipt.json`;
oryginalna runda1 zachowana w plikach `_R1`. Audyt był statyczny, nie zastępuje
wykonanych testów ani operatorowego pomiaru jakości modelu.

Przyjęte resztkowe P2 rundy2: P2-8 — niedostępny wycinek może zgubić opis
istniejącej oceny `missing` i wyświetlić zbyt ogólny brak odniesienia; porażka
pozostaje widoczna jako niedostępność, bez pozytywnej oceny. P2-9 — stan
`borderline` ma surową angielską etykietę zamiast polskiego opisu. Obie uwagi
dotyczą opisów zatwierdzonego content GT, którego pilot nie ma. Nie wykonano
kolejnej rundy zmian po zaakceptowanym focused review; nie osłabiono kontroli.

T1–T4 mają osobne Opus PASS. Wszystkie powyższe ograniczenia testów, danych,
ochrony capture i ręcznego odbioru pozostają aktualne. Gotowość narzędzia nie
jest rekomendacją zmiany marginesu ani dowodem poprawy modelu. Bez operatorowych
mutacji, treningu, wdrożenia i merge/push. Końcowe docs/map i task-close są
kontrolą metadanych po audycie, bez zmiany audytowanego kodu.
