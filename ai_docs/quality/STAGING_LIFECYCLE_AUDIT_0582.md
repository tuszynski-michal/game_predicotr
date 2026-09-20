# TASK-0582 — wynik naprawy i audytu stagingów

Data: 2026-09-20. Gra 777: `bfc4f949-5c14-4850-b02a-db99610bcfa5`.

## Naprawione mechanizmy

- Lista stagingów otrzymuje tożsamość/status importu niezależnie od limitu
  historii jobów. Importowany staging nie oferuje ponownego preflightu,
  importu ani operacji modyfikujących. Ponowiony start zwraca istniejący job;
  transakcyjna kontrola chroni przed nowym importem po zmianie modeli.
- Nowy import wymaga kompletnej geometrii całych zdjęć. Utrzymano gate TASK-0581.
- Usuwanie nieużywanego stagingu sprawdza referencje w magazynie właściwej gry.
  Regresja PostgreSQL obejmuje nową sesję repozytorium i usunięcie nieużywanego
  stagingu po nieudanym preflighcie. Ochrona wyników i ręcznych decyzji pozostaje.
- Korekta pojedynczej planszy z `quad=null/needs_manual_review` może otworzyć
  szkic `initialQuad` z przypiętej rewizji źródła 0. Walidowane są checksum,
  pozycja, sekwencja i granice geometrii. Szkic nie staje się zatwierdzoną
  geometrią ani przykładem treningowym przez sam odczyt. Użytkownik poprawia
  planszę w „Zatwierdzanie cięcia siatki → Niepełne siatki do ręcznej korekty”.
- Atomowy zapis checkpointu ponawia wyłącznie Windows sharing/lock violations
  (maksymalnie 5 prób, łącznie 0,5 s oczekiwania); pozostałe błędy zachowują
  stary indeks i raportują errno/winerror. Historyczny błąd joba `25bb58f8`
  nie zawierał przyczyny systemowej, więc jej jednoznaczne ustalenie jest
  niemożliwe. Nie przedstawiamy tej hipotezy jako potwierdzonej diagnozy.

## Rzeczywiste dane — odczyt bez zmian

17 fizycznie gotowych stagingów, 12 zaimportowanych stagingów i 13 importów.
Manifesty przypięte do wykonanych importów mają 0 odroczonych całych źródeł.
Późniejsze, zbędne preflighty nie są źródłem prawdy o wykonanym imporcie.

11 916 pojedynczych plansz oczekuje na ręczną korektę. Wszystkie mają dostępny
szkic i pliki; audyt nie wykrył błędnego dopasowania pozycji/sekwencji ani
geometrii poza granicami źródła. Próbka correction-context każdego z 13 importów
zwraca HTTP 200. To potwierdza dostęp do edytora, nie jakość ręcznej korekty
ani wykonanie przyszłego cięcia.

Wykryto 10 191 dodatkowych rekordów plansz według checksum źródła i pozycji,
w dwóch importach stagingu `9c7de0ca-6eda-4b43-977d-d4684cb6b58b`
(„117829 - 128268 cut”):

- `7d10ae0a-60ee-404c-a8b6-38fb3c416ba3`: 10 235 plansz;
- `f4ef3449-4ac2-46de-9dbc-23525cd864ed`: 10 191 plansz.

Nie ma powielonych numerów sekwencji canonical. Duplikatów nie usuwano:
potrzebny jest preview wyboru zachowywanych wyników i ich zależności oraz
osobna zgoda przed operacją destrukcyjną.

Staging `ac700907-21e5-4d91-9646-71f48940d9f8` ma nieudany preflight i nie ma
źródeł, review ani pending geometry. Naprawiono routing powodujący fałszywą
blokadę usuwania; rzeczywistego stagingu nie usunięto.

Audyt odtwarza `scripts/audit_staging_lifecycle.py --game-id <UUID> --report <path>`
uruchomiony Pythonem z `.venv`. Używa transakcji read-only, timeoutów SQL i
limitów wyników. Lokalny raport: `artifacts/admin-audit/staging-0582.json`.

## Weryfikacja i wdrożenie

102 testy API/workera, 1 izolowany test PostgreSQL i 56 testów Node: PASS.
Ruff, mypy, admin typecheck, Prettier i zgodność OpenAPI/klienta: PASS.
ESLint: 0 błędów i wcześniejsze ostrzeżenie next/no-img-element.
Nie uruchamiano pełnych testów repozytorium ani builda produkcyjnego.

API potwierdza naprawę w nowych żądaniach. Bezczynny worker general został
przeładowany; zweryfikowano działanie nowych procesów. Stary runtime manifest
zawierał także obce procesy po ponownym użyciu PID, więc zatrzymano wyłącznie
dwa procesy Python ze zweryfikowaną komendą/tokenem. Nowy manifest zawiera
wyłącznie bieżący worker i jego konsolę. Ogólna poprawka managera procesów
pozostaje poza zakresem tego zadania; nie używać starego manifestu do Stop.

## Ocena dalszego postępowania

Zalecane jest zachowanie obecnej gry i korekta istniejącej kolejki, a następnie
kontrolowane uporządkowanie podwójnego importu. Nowa gra powieliłaby pracę;
sama nie naprawia mechanizmu ani nie przenosi nauki cięcia. W tym zadaniu nie
usuwano geometrii lub treningu, nie implementowano ich przenoszenia między
grami i nie tworzono nowej gry. Nie można obiecać braku wszystkich przyszłych
błędów ani uznać oczekujących ręcznych korekt za wykonane.
