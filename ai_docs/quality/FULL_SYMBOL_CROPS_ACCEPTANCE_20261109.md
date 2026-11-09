---
title: Odbiór pełnych symboli 3×5 i instrukcja operatora
status: active
last_updated: 2026-11-09
---

# Pełne symbole 3×5 — odbiór implementacji

Zakres: `delivery/FULL_SYMBOL_CROPS_PLAN_20261108.md`, gałąź
`codex/full-symbol-crops`. Implementacja T0–T5 ma niezależne audyty Opus PASS
oraz wykonane właściwe kontrole kodu. T5 jest zamykane jako v1.7.577.
Ten dokument nie jest wynikiem rzeczywistego treningu modelu.

Kontrola Opus R1 T5 zwróciła REVISE: błędna ścieżka prawdziwego manifestu,
brak realnych nazw zdjęć i brak części testów błędów/opóźnionych odpowiedzi.
Wcześniejsze zielone fixture nie dowodzą tych integracji. Jedna runda
poprawek zakończyła się właściwymi testami i focused R2 PASS0P0/0P1.
Wynik implementacji jest gotowy do akceptacji operatora; wdrożenia nie wykonano.

## Pokrycie planu

| Część | Implementacja i dowód | Stan |
|---|---|---|
| T0 /1163 | Wersjonowany terminalowy audyt, discovery CLI, odrębne auth/limit/timeout, receipt i brak zastępczego PASS. Limit1800s, host1860s, idle60s. | v1.7.572, Opus PASS |
| T1 /1164 | Kontrakt24węzły/15visibility, source-pixel masks, rzeczywisty nadzór, ekspozycja i input-edge threshold wyłącznie A. | v1.7.573, Opus PASS |
| T2 /1165 | Niezależne15quadów/stanów, human provenance, dwa ślepe przebiegi, u/δ/oracle, chroniony świeży REG i istniejący ledger. Alembic0182. | v1.7.574, Opus PASS |
| T3 /1166 | Rzeczywiste wycinki klasyfikatora, stałe instancje i brak kompensacji nowych błędów, reportv6/gate, currentness i Alembic0183. | v1.7.575, Opus PASS |
| T4 /1167 | Jeden trwały eksperyment R0–R3, logiczne4800/7200, TRAIN ancestry bank, trained rastry, ONNX, checkpoint A, osobne BASE/WIDE30+30, independent API replay, input stamp i current support. | v1.7.576/a9951e94, Opus R2 PASS |
| T5 /1168 | Lokalny zwykły/ślepy edytor, snapshot-bound targets/asset, poprawny live/frozen licznik, panel v6, realny HTML/15PNG i domyślne regresje trzech P2 z T4. | v1.7.577, Opus R2 PASS |

Właścicielski raport testów: [TASK-1168_VERIFICATION.md](TASK-1168_VERIFICATION.md).
Poprzednie wyniki i granice fixture są w raportach TASK-1163–1167. Testy
rzeczywistego ONNX i PostgreSQL wykonano; nie zastępuje ich opinia audytora.
Zmiany T5 nie modyfikują wyjść sieci, więc nie powtarzano niezmienionych
eksportów ani pełnych4800-step prób. Obejmują je wcześniejsze dowody T1/T4.

## Wykonana weryfikacja

- API/SDK: live konflikt pojedynczej planszy, niezależne frozen coverage,
  dotychczasowe freshness/apply guards, odczyt celów bez etykiet, scope/pin,
  selected asset/no-store, real PostgreSQL/RLS i zimny odczyt. Własny cleanup
  potwierdził0baz/0ról; bez operatorowej bazy.
- UI: zwykłe zapisy i CAS, ślepy24/15, brak previous pass/draft/prediction,
  pending exact retry bez canvas hydration, reset scope, sourceXY invariance
  zoom/pan/resize i odrębność obwiedni. Właściwe desktop/mobile viewporty,
  brak overflow, zielone przyciski i gap12px zweryfikowano na fixture.
- HTML:55testów,15rzeczywistych PNG na model, oddzielne pixel/file SHA,
  źródłowo zweryfikowany T3 RGB wejścia NN, strict pins i matching, portable
  producer oraz dwa nowe procesy CLI. Brak tensora pozostaje jawny.
- Handoff P2:15testów bounded-reader/atrybucji i domyślny test identycznych
  nodes BASE/WIDE potwierdzają fail-closed. To delty T5, nie retroaktywny
  dopisek do audytowanego T4.
- Runda poprawek po Opus R1: prawdziwy publish_json/pages/index/root i dwa
  nowe procesy CLI→30PNG, lokalny brak renderu jednej z9plansz oraz ochrona
  obcych wyjść —50scoped PASS. Nazwy istniejących importów:9unit i1realPG
  z coldreader/cleanup PASS. Opóźnione odpowiedzi i error/empty/retry/budget:
  78interakcji PASS. Minimalne poprawki UI mają nowy Admin build PASS po
  jednym kontrolowanym ponowieniu środowiskowego EPERM. Nie sumować tych
  zestawów z poprzednimi jako rozłącznych testów.
- Admin: interakcje, lint, typy i pełny build PASS. Reviewer:60regresji
  geometrii/propozycji/proxy PASS, typy PASS, pełny build PASS. Root strict
  mypy pięciu API modułów PASS54,06s; Python HTML/guards mają osobne scoped
  mypy/lint PASS. Cały globalny mypy nie ma deklaracji PASS — historyczny
  Row-vs-tuple odtworzono także na wcześniejszym HEAD.

To kontrolowane fixture, także z prawdziwymi pikselami/plikiem i bazą,
nie zatwierdzenia operatora ani pomiar poprawy nowego modelu na Mumie A2.

## Po wdrożeniu: zbieranie danych i trening

1. W geometrii otwórz **Etykiety zawartości zdjęć**. Wybierz istniejący
   zamrożony zestaw, zdjęcie i planszę. Obrysuj całą widoczną grafikę każdego
   pola i zaznacz widoczność; „10” to jeden symbol. Zapis zatwierdza etykiety
   do nauki geometrii, a nie klasy symboli lub nowe cięcie planszy.
2. Otwórz **Pomiar powtarzalności etykiet** dla wybranych zdjęć treningowych
   i walidacyjnych. Dwa przebiegi zaczynają od pustych oznaczeń. Wskaż24punkty
   i15niezależnych obwiedni. Powiększenie/przesuwanie dotyczy tylko podglądu.
   Potrzebne jest minimum30plansz z10zdjęć na grę; pomiar jednej osoby jest
   powtarzalnością wewnątrzoperatorską, nie zgodnością niezależnych ekspertów.
3. Odśwież gotowość. Żywe nowe etykiety i zapisane frozen pins mają osobne
   liczniki. Zapisana kohorta jest migawką; następne przygotowanie zamraża
   nowe kwalifikujące się etykiety. Kontrole, kopie, wcześniejsze użycie i
   bufory nie przechodzą do TRAIN. Braki są blokadą konkretnego dowodu,
   a nie zakazem zwykłych propozycji do ręcznej korekty.
4. Rzeczywisty eksperyment uruchom dopiero po zgodzie na trening i gotowym
   preflight. Przycisk **Ulepsz siatki z korekt** zachowuje osobny opt-in
   pełnych symboli. Plan ma1200kroków na wymagane ramię i wspólne7200s;
   start/wznowienie nie odnawia zużycia. REG nie służy do doboru parametrów.
5. Ocenę propozycji i kwalifikację automatu czytaj osobno. Automat wymaga
   własnych30dobrych i30błędnych rzeczywistych źródeł każdego używanego
   wariantu w B i REG; braku nie zastępuje wspólny próg. Zastosowanie modelu
   jest odrębną akcją wymagającą aktualnego raportu i potwierdzenia.

Zdjęcia wystarczają, nagrywanie filmu nie jest wymagane. Obsługiwany układ to
3rzędy×5kolumn na stronie3×3. Kolejna gra wymaga własnego dowodu jakości;
zgodność układu pozwala na propozycje, nie dziedziczenie kwalifikacji automatu.
Progi produktu i znane grupy zdjęć nie są gwarancją niezależności statystycznej.

## Lokalny eksport HTML

Istniejący katalog zapisanego porównania zawiera inputs.json,
learning-final.json, evaluation-final.json, wyniki base/candidate i zdjęcia.
CLI czyta te wyniki, nie uruchamia modeli ani nie tworzy domenowych zapisów.
Podanie magazynu artefaktów automatycznie pakuje przypięte source/cohort/detail;
operator nie tworzy production-cells/index.json ręcznie.

PowerShell z katalogu projektu:

```powershell
$comparisonDirectory = Read-Host 'Katalog zapisanego porównania'
$artifactDirectory = Read-Host 'Główny katalog artefaktów'
& '.\.venv\Scripts\python.exe' '.\scripts\render_grid_correction_comparison.py' `
  --directory $comparisonDirectory --artifact-root $artifactDirectory
```

Wynik: comparison.html i lokalne PNG. Nieoznaczone plansze służą porównaniu
wzrokowemu; ich jakości nie nazywa się potwierdzoną. Brak/mismatch dowodu
pokazuje niedostępność i pełne zdjęcie, bez zgadywania dopasowania.

## Wdrożenie i przywrócenie wersji

Nie wykonano merge/push, migracji operatora0182/0183, restartów, treningu,
zmiany defaultu ani importu691. Wymagają właściwych odrębnych zgód. Wdrożenie
wymaga zgodnego API/Admin/Reviewera/workera i migracji przed korzystaniem z
nowych tabel/protokołów; stare raporty i ręczne korekty zachowują interpretację.

Przywrócenie modelu odbywa się przez zachowaną historię wersji: wybór poprzedniej
wersji, osobne przypisanie gry i ewentualne ustawienie defaultu. Stare importy
nie są przez to przeliczane. Preferowany rollback modelu zachowuje nowe dane
oznaczeń i kompatybilną aplikację; downgrade bazy lub starego kodu nie jest
zastępstwem tej operacji i wymaga osobnego planu.

Otwarty residual T4P2-1/T3P2-1 dotyczy kosztu fizycznego replayu w inspektorze
i raportach; latencji nie zmierzono, a cache samych SHA nie został wprowadzony.

Residual T5R1/P2-2: HTML wymaga dokładnie tych samych węzłów predykcji co
zamrożony świadek oceny. Inny backend lub niedeterministyczne ponowne
rozpoznanie może dać unavailable pomimo podobnego obrazu. To zaakceptowane
ograniczenie dowodu, nie potwierdzona częstość problemu; nie wykonano pomiaru
na zestawie operatora. Zachowano ścisłe sprawdzenie, aby nie przedstawiać
wycinków innego wyniku jako ocenionych. Pierwsze rzeczywiste porównanie musi
sprawdzić ten warunek; nie należy rozluźniać go progiem lub dopasowaniem9/index.

Residual T5R2/P2-4 dotyczy braku testu rzeczywistego producenta pliku detail
w pakiecie audytora. Root wąsko potwierdził w kodzie producenta wspólny
artifact root oraz tę samą względną ścieżkę/SHA w zapisie i pinie, bez zmiany
kodu. Nie jest to wykonany test end-to-end. Pierwsze rzeczywiste pakowanie
musi dodatkowo potwierdzić ten warunek; niedopasowanie daje unavailable.
