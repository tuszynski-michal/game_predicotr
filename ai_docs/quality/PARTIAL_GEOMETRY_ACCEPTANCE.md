---
title: Odbiór ręcznej geometrii niepełnych plansz
status: engineering_accepted
last_updated: 2026-09-07
---

# TASK-0505–0509 — niepełne plansze

## Wynik i granice odbioru

Odebrano kod ręcznego workflow wraz z niezależnymi audytami
`gpt-6-astra high`. Brak znanych blockerów kodu w przejrzanym zakresie.
Nie jest to odbiór wdrożenia na danych operatora: migracje 0100/0101 nie
zostały zastosowane, usług nie restartowano, importów nie przeliczano.

Lewy/prawy bok może być rzeczywiście niepełny. Brak góry lub dołu planszy
oznacza błąd wcześniejszego przycinania źródła: UI ostrzega i zaleca poprawę
źródła. Ręczne rozliczenie nie odzyskuje pikseli i nie kwalifikuje geometrii
do uczenia. Brak ozdobnej ramki nie oznacza automatycznie niepełnych symboli.

## Wykonane kontrole

| Kontrola | Wynik |
|---|---|
| API — zmienione moduły serii 0505–0508 | 182 passed |
| Worker — zmienione moduły i EXIF 1–8 | 120 passed |
| Dodatkowe regresje dwóch rogów, samej ramki i końcowych slotów | 13 passed, również niezależny audyt |
| Admin — testy helperów i kontraktów | 431 passed |
| Reviewer — testy helperów i kontraktów | 183 passed |
| JSDOM obu rzeczywistych edytorów | 6 passed |
| Klient API: żądania i generowany kontrakt | 54 passed |
| Ruff, format Python zmienionych plików | passed po dwóch korektach formatowania |
| Mypy zmienionych źródeł + skryptu odbioru | 41 plików, passed; `--follow-imports=silent` |
| Typecheck Admina i Reviewera | passed |
| ESLint Admina i Reviewera | passed |
| OpenAPI export i check generated | passed |
| Prettier zmienionych plików web/klienta | passed |
| Produkcyjne buildy Admina i Reviewera | passed |
| Globalne `npm run format:check` | 31 wcześniejszych problemów formatowania poza zakresem; automatyczną zmianę next-env Reviewera po buildzie przywrócono |

Grupy testów mogą się pokrywać; nie sumować ich jako liczby unikalnych testów.
Globalny formatter nie uzasadnia formatowania obcych zmian i całego auto-cropa.

Regresje obejmują: wszystkie sloty row-major, końcowe 499996–500000,
maskę 15/15, dwa rogi z maską 0/5/9/14, rozdzielenie proper-cell i paddingu,
przejścia pełna→partial→partial, zachowanie FK/ID/historii, brak zatwierdzeń
dla nowych pikseli, idempotentne ponowienie po utracie odpowiedzi, zakaz
sklejenia różnych rewizji w replay źródła, fail-closed błędną projekcję
deferred, brak zapisów przy nawigacji, restart szkiców i konflikt rewizji.

Audyt 0508 wykrył i doprowadził do poprawienia: fail-open synchronizacji
deferred, odwróconych locków state/sekwencja, braku nowego state przed
backfillem, pomijania partial w explicit reinference zakończonego importu,
scope replay oraz niepełnego pionu signed HTTP guard. Odbiór audytora:
137 testów plus 16 po poprawce locków. Końcowy audyt 0509: 13 testów nowych
regresji, brak dalszych blockerów odbioru inżynierskiego.

## Trzy istniejące źródła — odczyt bez zmian

Uruchomiono `scripts/verify_partial_geometry_sources.py` na trzech JPEG-ach
z `C:\Users\user\Documents\777\1-19809 cut`. Skrypt nie zapisuje obrazów,
manifestów ani DB. Przed i po sprawdza checksumę wejścia.

| Plik | Wymiary kanoniczne | SHA-256 |
|---|---|---|
| seq_1-9.jpg | 1080×802 | cf3482ff4a49c8df7a0bcd8cdb7b1f8c3baad6d39ed590998554d39b6ee622e6 |
| seq_10-18.jpg | 1080×751 | 567ccc8bfc43356624c6b9559f37642f97410bf61c28a695a0eca43f0abebde6 |
| seq_100-108.jpg | 1080×730 | 3176de8092dd16a492ecf8307dac8cd0d49668534befbdaef805af0c99d3929c |

Każde źródło: lewa maska 0/5/10 i prawa 4/9/14, po 12 realnych renderów,
identyczny pikselowo replay. Quady są izolowanymi fixture'ami na brzegu
obrazu, **nie ręcznymi referencjami położenia rzeczywistych plansz**.
Wynik nie dowodzi skuteczności detektora ani jakości auto-cropa.

## Niewykonane / ograniczenia

- Nie wykonano rzeczywistego wielotransakcyjnego testu konkurencji PostgreSQL.
  Sprawdzono granice aplikacyjne, kolejność blokad i regresje repozytoriów;
  nie uruchamiano fixture'u kasującego stałą testową bazę przez DROP FORCE.
- Nie wykonano wizualnego ani dotykowego odbioru na Androidzie. JSDOM sprawdza
  interakcje i wywołania API, a build nie zastępuje testu na urządzeniu.
- Nowy zapis kwalifikacji dotyczy managed virtual geometry. Legacy assets
  pozostają czytelne, lecz nowy zapis odmawia, zamiast ignorować metadane.
- Aktywny model nie zostaje odtrenowany. Wykluczenia obowiązują następne
  kohorty/oceny i snapshoty kotwic, nie przepisują historycznych jobów.

## Warunkowa prośba o automat v0.10.4

Nie dodano pozornej nowej wersji silnika. Automat obecnie odracza niepewną
geometrię; nowa automaska dotyczy **ręcznie wskazanego** quada.

Analiza `symbol_lattice_homography.py`, `board_cell_geometry_estimator.py`,
`structured_geometry/geometry_engine.py` i `production_workflow.py`:
estimator wymaga dowodów wszystkich pięciu kolumn/trzech rzędów oraz source
support. Nie wystarczy zamienić odrzucenia na partial. Trzeba wiarygodnie
ustalić, czy brakuje lewej czy prawej kolumny, przypisać widoczne symbole do
pełnych indeksów i wyznaczyć perspektywę niewidocznej części. Zły wybór
przesunąłby numery komórek na całej planszy.

Niezależny audyt potwierdził, że automatyczna akceptacja nie jest lekkim
rozszerzeniem. Wymaga odrębnego, opt-in eksperymentu i oznaczonych danych,
w tym negatywnych pełnych plansz i pionowych błędów auto-cropa. Zgodnie
z warunkiem operatora nie zmieniono normalnego detektora. Ewentualny lekki
wariant może tylko sugerować szkic do ręcznego zatwierdzenia; nie został
przedstawiony jako gotowy automat ani uruchomiony na stagingach.

## Jak sprawdzić po wdrożeniu

1. Po zakończeniu aktywnych jobów zatrzymać usługi w kontrolowany sposób.
   Z katalogu repo wykonać `npm run db:migrate`, potem `npm run db:current`.
   Wymagana rewizja: `0101_symbol_cell_source_availability`. Następnie
   uruchomić API/workera według `LOCAL_OPERATION_GUIDE.md` i odświeżyć stronę.
2. W Import Plansz otworzyć ręczną korektę geometrii i wybrać planszę przy
   lewym lub prawym brzegu. Zaznaczyć `Niepełna plansza`, wysunąć narożniki.
   Sprawdzić szarą maskę i licznik dostępnych pól. Brakujące pola są `?`,
   nie dostają sztucznego obrazka; wykluczenie geometrii jest obowiązkowe.
3. Przejść Następna→Poprzednia bez zapisu, potem odświeżyć. Szkic powinien
   pozostać; nie powinien powstać zapis API. Reset wraca do bazy zdjęcia.
4. Zapisać jawnie pełną geometrię źródła. Ponownie otworzyć zdjęcie:
   wszystkie sloty i oznaczenia pozostają. W Weryfikacji symboli widoczne
   pola mają aktualne cropy, a brakujących nie ma w treningu.
5. W Zatwierdzaniu cięcia siatki wykonać tę samą próbę, poprawiając dwie
   plansze przed zatwierdzeniem całego zdjęcia. Sprawdzić również kompletną
   planszę z samym `Nie używaj do uczenia geometrii` — symbole pozostają.
6. Dla uciętej góry/dołu sprawdzić ostrzeżenie i poprawić źródło przed nowym
   importem. Ręczne oznaczenie brakujących pikseli nie naprawia auto-cropa.
