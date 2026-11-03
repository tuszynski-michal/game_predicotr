---
title: TASK-1155 — rzeczywiste wejście sieci i gotowość danych
status: active
last_updated: 2026-11-03
---

# Odtwarzalne dowody T1

Wersjonowany zapis i CLI odtworzyły oba etapy preprocessingu dla planszy 462205
bez inferencji. Brak kwalifikowanego GT tej planszy uniemożliwia ilościową
diagnozę brakującego fragmentu. Odczyt istniejącym readerem potwierdził 197
aktualnych ludzkich etykiet na 134 zdjęciach; żadne nie ma kompletu 9 etykiet.
Nie jest to dopuszczenie treningu, modelu ani automatu.

## Przypadek 462205 i granica dowodu

- Source: `e1423fff-6d95-4e8c-ba73-9c8ea6b52f70`, pozycja 0, jawny atest 462205–462213.
- Oryginał 1498×1246, SHA256
  `8e713b2036210c3bf7a6e66043bf973876e18fce648af6beb4aecfa794bacdb7`.
- Kanoniczny pixel SHA256:
  `a656d341d691e56fcb161cb21f41ed48640ceacad2c6419df818956f32a57a2c`.
- Baza: `158a740f-1f54-523f-94f3-508477dbea7a`; kandydat:
  `3ed60010-7c3e-5c3b-91aa-4e03eb9bfa5e`. Bundle SHA sprawdzono przed cropem.
- Obie wersje mają identyczny zapisany obszar detektora. Crop planszy 320×192
  używa marginesu 0.15, `INTER_LINEAR` i stałego wypełnienia 114. Pixel SHA:
  `a79ab2a2d8d3f75bf83031b948f40405dbe2018479b603bc0b1669ec447ff171`.
- Screen używa istniejącego `INTER_AREA`, long-side 768 i padding do 32.
  Jego tensor ma NCHW, kształt1×3×640×768. Plansza jest dokładną próbką CHW przed stackiem.
  Oba tensory mają float32 i wartości 0–255, bez normalizacji przez 255.
  PNG uint8 i NPY float32 mają osobne hashe w rekordzie. Nie twierdzimy,
  że historyczny pełny batch plansz został zachowany.
- Crop pokazuje symbole przecięte górną granicą. Jest to obserwacja wizualna,
  nie pomiar uciętej części GT. Reader odrzuca slot 0 jako
  `GRID_ISSUE_OR_TOPOLOGY`; pozostałe 8 wymagają ludzkiego zatwierdzenia.
- Surowe punkty, peak, visibility i statystyki fit nie zostały zapisane przez
  wcześniejszy eksporter. Raw pozostaje `NOT_ARCHIVED`; fitted nodes są osobno.
- Zapisana geometria bazowa ma historyczne `automatic`. Kandydat ma
  `NEURAL_GRID_FIT_OUTLIERS`, blokowane przez T0. Nie ma zapisanego nowego
  bindingu sekwencji kandydata; raport oznacza także brak tego dowodu.
  Projekcja polityki nie autoryzuje zapisu ani akceptacji.

Historyczny JSON nie pozwala bez nowej inferencji odzyskać raw outputs.
Nowa inferencja byłaby nową obserwacją, nie odzyskaną historią; nie wykonano jej.
Liczba przypadków z dowiedzionym GT poza cropem pozostaje **nieustalona**,
nie zero. Brak dowodów nie blokuje ręcznej korekty.

## Oddzielne zakresy danych

| Źródło dowodu | Zdjęcia | Kwalifikowane etykiety | Pełne zdjęcia |
|---|---:|---:|---:|
| LIVE, 134 źródła z 197 nominalnymi bieżącymi zatwierdzeniami |134|197|0|
| Frozen TRAIN |98|146|0|
| Frozen VALIDATION |13|17|0|
| Frozen REGRESSION |13|21|0|

LIVE reader potwierdził 197/197 etykiet. Maksimum to 6 na zdjęcie. Pozostałe 1009
pozycji ma `HUMAN_APPROVAL_REQUIRED`; błędów źródła 0. Odczyt ograniczono do
134 źródeł, bez pełnej kwalifikacji 7092 plansz. Partie po 10 miały osobne
read-only repeatable-read transakcje; nie tworzą wspólnego równoczesnego snapshotu.
Pierwsze 110 użyły worktree; ostatnie 24 stabilnego main `c6f9597a` podczas edycji
T0. Reader i preprocessing miały identyczne hashe w obu checkoutach.

Frozen kohorta `8c4d3ab4-4d01-59fe-a826-46883b72ddfe` ma 788 unikalnych SHA
z 2 importów; 664 zdjęcia są wyłączone. Jej manifest SHA to
`cbfdbcfcb15543ae3b5c53ec6d3f9b32ccc48d2c02cb3b6728dcb955afae133a`.
`screenEligible=0` dotyczy tego snapshotu. LIVE potwierdza niezależnie zero
pełnych ludzkich zdjęć w odczytanym zakresie, lecz role/kopie/bufory/ancestry
nie były ponownie kwalifikowane: `screenEligiblePhotos=null`.

Istniejący raport oceny opisanych plansz podaje kandydat VALIDATION 14 dobrych/3
błędne, REGRESSION 17/4; baza odpowiednio 12/5 i 15/6. To historyczne agregaty,
bez ponownego oglądania lub wyboru tych przykładów do projektowania.
Nie kwalifikują minimów T4. Niezależność sesji i wykluczenie nieznanego
historycznego TRAIN pozostają nierozstrzygnięte; 2 importy nie dowodzą 2
niezależnych grup. Nie podano przedziałów ufności.

Zapisane porównanie pending ma 150 plansz/101 zdjęć, zero aktualnych ludzkich
zatwierdzeń w `inputs.json` i zero zdjęć TRAIN. Nie dostarcza bezpiecznych
par GT+predykcja good/bad do projektowej diagnostyki. Nie zastąpiono ich
przykładami REGRESSION ani przyszłej VALIDATION-B.

## Użycie diagnostyczne i ochrona historii

Odczyt metadanych 134 źródeł oznaczono `readiness_metadata_only` i
`usedForModelDesign=false`. Nie oglądano ich pikseli ani nie dobierano
na nich modelu lub progów. Sam count access nie wyklucza tych źródeł z kontroli.

Faktyczny `diagnosticUse` obejmuje wyłącznie podany wyżej source 462205,
z byte/pixel SHA. T4 musi wykluczyć ten przykład oraz znane kopie i grupy
z nowych VALIDATION-B i REGRESSION za pomocą istniejącego mechanizmu dowodów.
T1 zapisuje wejściowy dowód; nie udaje już działającej bramki T4 i nie zmienia
historycznych ról, rezerwacji, buforów, zatwierdzeń ani historii użycia.

## Artefakty i odtworzenie

Lokalnie, poza git:

- `D:/game_predicotr/artifacts/task1155-input-replay-r2/`: base/candidate JSON,
  cztery PNG, cztery NPY i końcowy `report.json`.
- `D:/game_predicotr/artifacts/task1155-preflight/`: kwalifikacja LIVE/frozen,
  partie, metadane, pochodzenie i manifest SHA; nie jest datasetem treningowym.
- `D:/game_predicotr/artifacts/task1155-verification/`: logi testów i odtworzeń.

Z worktree, przy interpreterze projektu i jego importach:

```powershell
$env:PYTHONPATH='services/api/src;services/worker/src;.'
& D:/game_predicotr/.venv/Scripts/python.exe -B -m scripts.diagnose_full_board_input replay `
  --record D:/game_predicotr/artifacts/task1155-input-replay-r2/candidate.json `
  --original D:/game_predicotr/artifacts/data/originals/8e/8e713b2036210c3bf7a6e66043bf973876e18fce648af6beb4aecfa794bacdb7.jpg
```

Komendy wykonano w kontrolowanych procesach z timeoutami ≤120 s. Oba rekordy
odtworzono w osobnych procesach; piksele i tensory obu etapów zgodne.
Nowy reader sprawdzono na jednym źródle LIVE (`max_sources=1`, 20 s): zwrócił
`partial`, 2 etykiety i kursor. Nie powtórzono pełnego preflightu 134 źródeł.
Budżet jest rozszerzalny, a strony kontynuacji nigdy nie udają pełnej gotowości.
Komenda `frozen` zweryfikowała manifest i odtworzyła historyczne liczniki788
źródeł przez istniejący GridCohortSnapshot, bez odczytu pikseli.

R2 uzupełnia rekord o pełny `archived_preset`: replay sprawdza jego kanoniczny
SHA, zgodność screen/board i obsługiwaną wersję przetwarzania. Nie jest to SHA
pliku bundle ani dowód autentyczności. Nowe procesy replay R2 potwierdziły te
same bajty RGB i tensorów co R1. Dawny katalog `task1155-input-replay/` pozostaje
przedwydaniowym dowodem R1; jego niepełne rekordy nie spełniają finalnego kontraktu.

`diagnosticUse` wiąże SHA obu rekordów z sequence/position i stabilnym kluczem
źródło/byte SHA/pixel SHA/purpose. Powtórny eksport nie tworzy nowego użycia:
T4 ma scalać klucze oraz unikalne record SHA. Nie zmienia to historycznych ról.
Readiness dotyczy wyłącznie źródeł z nominalnym current-human approval, a dwa
znane błędy wycofanego/usuniętego źródła są jawnymi odrzuceniami. Pozostałe błędy
i timeouty przerywają raport. Frozen liczy etykiety i screenEligible wyłącznie
dla used; R2 ponownie potwierdził zgodność wszystkich liczników z manifestem.

Publikacja JSON jest wyłączna i następuje po flush/fsync. Capture publikuje cały
katalog po fsync plików przez Windows rename bez nadpisania. Nie obiecuje
directory-fsync ani odporności na fizyczną utratę zasilania. Dwa testy na
jednorazowej bazie potwierdziły rzeczywiste READ ONLY oraz statement_timeout;
nie wykonywano zapisów ani nowego pełnego odczytu danych operatora.

## Weryfikacja i ograniczenia wydania

Wyniki końcowych scoped kontroli i audytu są w Outcome TASK-1155. Bez nowej
inferencji, treningu, aktywacji, usług, migracji i zapisów bazy. Przed commitem
wymagany jest niezależny audyt Opus uruchomiony przez koordynatora.

R1 oraz focused R2 zakończyły się PASS. R2 zamknął P1 kontraktu presetu i 5 P2
R1. Pozostaje zaakceptowane przedwydaniowe P2-R2-1: niepełny rekord R1 ma ten
sam identyfikator v1, lecz bieżący decoder odrzuca brak archived_preset ogólnym
ValidationError. Nie jest to rozróżniona migracja. R1 nie był wydany aplikacji
ani operatorowi; zachowano jego snapshot i manifest. T4 musi odrzucić niepełny
rekord, bez domyślania presetu. Pozostałe P3 i granice testów zapisano w Outcome.
