---
title: Version 0.2 Admin acceptance
status: awaiting_owner_acceptance
last_updated: 2026-08-02
---

# Version 0.2 Admin acceptance

## Wynik techniczny

Automatyczna i przeglądarkowa bramka techniczna Admina 0.2 przeszła ponownie
`2026-08-02`. Test nie używał danych właściciela: każdy scenariusz PostgreSQL
tworzył osobną bazę, wykonywał migracje do `head` i usuwał bazę po teście.

Powtarzalna komenda:

```powershell
npm.cmd run v02:admin:acceptance
```

Każdy proces potomny ma limit 120 sekund. Raport maszynowy jest zapisywany w
ignorowanym katalogu
`artifacts/v02-admin-acceptance/acceptance-report.json` i nie zawiera sekretów
ani ścieżek wejściowych użytkownika.

## Evidence automatyczne

| Kontrola | Wynik | Zakres |
| --- | --- | --- |
| PostgreSQL integration | passed, 4 testy | publiczny przepływ M2, release i anulowanie, dwa scenariusze cleanup |
| Admin tests | passed, 140 testów | trzy workspace'y, URL, loading/error/empty, akcje, joby, import, release i cleanup |
| Admin typecheck | passed | TypeScript bez błędów |
| Admin lint | passed | ESLint |
| OpenAPI contract | passed | artefakt i generowany klient są aktualne |
| Admin API client | passed, 26 testów | kontrakt, generowanie oraz regresja LF/CRLF na Windows |
| Admin production build | passed | statyczny build Next.js |

W trakcie pierwszego przebiegu bramka wykryła dwie rozbieżności fixture'ów po
wprowadzeniu `expectedLayoutCount`. Publiczny scenariusz M2 deklaruje teraz cel
1000 layoutów, a fixture release cel 2 layoutów. Skrócono również katalog
tymczasowy pytest, aby najdłuższa ścieżka artefaktu snapshotu nie przekraczała
praktycznego limitu Windows.

## Evidence przeglądarkowe

Na produkcyjnym buildzie i pustej lokalnej bazie sprawdzono viewport
1366 × 768:

- widoczne są dokładnie trzy workspace'y: `Zarządzanie grami`, `Wersje Android`
  i `Joby`,
- `?workspace=releases` i `?workspace=jobs` odtwarzają właściwy ekran po
  odświeżeniu,
- stan pusty gier, wydań i kolejki jobów jest jawny,
- `documentElement.scrollWidth` i `body.scrollWidth` wyniosły 1351 px przy
  `innerWidth = 1366 px`, więc nie wystąpił poziomy overflow,
- konsola nie zawierała błędów ani ostrzeżeń,
- nawigacja używa natywnych przycisków, a globalny styl `:focus-visible` obejmuje
  przyciski, linki, inputy i selecty.

Przed testem zatrzymano pozostawiony od 31 lipca stary proces Admina na porcie
3000. Po odbiorze procesy uruchomione przez test zostały zatrzymane, a porty
3000 i 8000 zwolnione.

## Odbiór właściciela

Właściciel potwierdził już utworzenie i wybór gry, rzeczywisty import folderu,
przejście pełnego pipeline'u do review, działanie Symboli, lokalnego i
publicznego Reviewera oraz obserwację joba. Odczyt PostgreSQL z 2026-08-02
potwierdził job `65d6ca14-dacc-4341-b015-c187f2d7af36` w stanie
`waiting_for_review`, 739 źródeł, 4050 plansz, 60 750 cropów i 4050 pozycji
review.

Na małym kontrolowanym zestawie pozostaje potwierdzić:

1. utworzenie jednego testowego wydania,
2. nawigację `Tab`, aktywację `Enter` i widoczność fokusu w Adminie,
3. preview cleanup bez wykonywania resetu, chyba że dane są świadomie
   przeznaczone do usunięcia.

Wersja 0.2 nie jest zamknięta produktowo, dopóki właściciel nie potwierdzi tego
krótkiego odbioru i nie zostaną zaadresowane znalezione przez niego regresje.

### Regresje znalezione podczas odbioru

Pierwszy pion TASK-0142 poprawił sekcję `Import layoutów`:

- trzy główne akcje mają spójne style, zawijanie i własne stany operacji,
- zwykły `disabled` nie pokazuje już kursora trwającej operacji,
- wyjątek transportu nie pozostawia panelu zablokowanego dzięki `try/finally`,
- ikona `?` pokazuje dostępną z klawiatury legendę działania przycisków,
- kompletność i bounded lista pierwszych luk używają kart, chipów i kontrolowanego
  przewijania,
- pole numeru sekwencji i akcje wyboru źródła mają osobny responsywny układ.

Drugi pion TASK-0142 usunął blokadę natywnego wyboru folderu przy Admin API
uruchomionym w tle. Proces PowerShell wymusza widoczny stan okna, a sam dialog
ma niewidocznego właściciela `TopMost`, dzięki czemu nie chowa się za aplikacją.
Kolejność akcji zmieniono na `Rozpocznij import` → `Wybierz folder` →
`Odśwież status`.

Kontrole po zmianach: 130 testów Admina, cztery skupione testy API, Ruff,
PowerShell syntax, typecheck Admina, ESLint i produkcyjny build pierwszego pionu
przeszły. Pełny mypy uruchomiony poza standardowym skryptem nie zakończył się w
limicie 60 sekund; po przerwaniu nie pozostał osierocony proces. Potwierdzenie
widoczności natywnego dialogu przez właściciela pozostaje częścią trwającego
odbioru.

Trzeci pion TASK-0142 poprawił katalog gier. Cały obszar kafelka dostępnej gry
wybiera teraz kontekst, ale osobne przyciski `Edytuj`, `Archiwizuj` i
`Przywróć jako szkic` zachowują własne działanie. Zapis edycji ma dodatkowe
uzgodnienie przez odczyt gry: jeżeli backend osiągnął żądany stan, przejściowo
utracona lub niepełna odpowiedź mutacji nie powoduje fałszywego błędu w UI.
Regresja API jawnie sprawdza zmianę `expectedLayoutCount`. Po poprawce przeszły
132 testy Admina, jego typecheck i ESLint oraz dwa skupione testy katalogu API.

Czwarty pion TASK-0142 usunął przenoszenie `Otwieranie…` pomiędzy grami oraz
równoległe, niewidoczne selektory. Komponent importu ma cykl życia przypisany do
identyfikatora gry, backend dopuszcza jeden natywny selektor naraz, a helper
Windows pokazuje widocznego właściciela z wpisem na pasku zadań i wymusza fokus.
Po zmianie przeszły 133 testy Admina, typecheck, ESLint, pięć testów API importu,
Ruff i kontrola składni wszystkich 20 skryptów PowerShell. Ręczne potwierdzenie
widoczności poprawionego dialogu pozostaje częścią odbioru.

Piąty pion TASK-0142 uprościł wejście do sekcji `Symbole`: usunięto powtórzony
tytuł, podtytuł i opis techniczny, etykietę zmieniono na `Liczba symboli`, a
input otrzymał spójne style hover, focus i disabled oraz responsywny układ.
Regresję zabezpieczają dwa testy kontraktowe; cały zestaw Admina obejmuje teraz
135 przechodzących testów.

Szósty pion TASK-0142 zastąpił nieskuteczne próby uruchamiania dialogu Windows
przez backend standardowym selektorem folderu przeglądarki. Kliknięcie
`Wybierz folder` nie wysyła requestu i nie uruchamia PowerShella; po wyborze UI
przesyła JPEG-i pojedynczo, pokazuje postęp i finalizuje kontrolowany staging do
jednorazowego tokenu. API waliduje liczbę, rozmiar, względne nazwy oraz zawartość
plików, sprząta anulowane i wygasłe wybory, a CORS jawnie dopuszcza wymagany
`PUT` i `X-Image-Relative-Path`. Historyczne piony drugi i czwarty opisują
odrzucone próby naprawy dialogu systemowego i nie stanowią już bieżącego flow.
Po zmianie przeszło 136 testów Admina, 24 testy klienta API, siedem skupionych
testów API importu, Ruff oraz kontrola zgodności OpenAPI. Właściciel potwierdził,
że selektor przeglądarkowy otwiera folder, przesyła pliki i tworzy job importu.

Siódmy pion TASK-0142 uporządkował katalog i konfigurację gry. Stabilny kod ma
mniejszy rozmiar i znajduje się bezpośrednio pod nazwą, natomiast cel layoutów
jest osobną, niższą linią z dodatkowym odstępem. Kontrola wysokiego wpływu
`Wyczyść dane layoutów gry` została przeniesiona pod wszystkie cztery zwykłe
sekcje konfiguracji. Dwa nowe testy kontraktowe zabezpieczają hierarchię karty i
kolejność czyszczenia; zestaw Admina obejmuje 138 przechodzących testów.

Ósmy pion TASK-0142 usunął awarię rzeczywistego image importu na pierwszym
checkpointcie. Handler zapisywał `schemaVersion`, mimo że wspólny wewnętrzny
kontrakt jobów wymaga `schema_version`. Test regresyjny przeprowadza payload
handlera przez prawdziwy walidator checkpointu, a runtime zachowuje teraz
stabilny kod i bezpieczny komunikat domenowego `JobError`. Job folderu `777`
wznowiono bez ponownego uploadu; druga próba zakończyła się `completed`,
`739/739`. Dziewięć skupionych testów workera i Ruff przeszły.

Dziewiąty pion TASK-0142 usunął source-only success. `Rozpocznij import`
uruchamia teraz jeden trwały workflow od managed originals przez normalizację,
detekcję plansz, cropy, OCR i klasyfikację symboli aż do projekcji pozycji
review. Retry korzysta z manifestu i checkpointów tego samego joba, więc nie
wymaga ponownego wyboru ani uploadu folderu. OCR dziewięciu numerów strony
wykonuje jedno wywołanie modelu. Skupiony zestaw 31 testów workera, Ruff,
mypy modułu OCR i smoke test rzeczywistego modelu przeszły. Rzeczywisty job
naprawczy `65d6ca14-dacc-4341-b015-c187f2d7af36` pozostaje w kontrolowanym
przetwarzaniu; po osiągnięciu `waiting_for_review` właściciel potwierdzi sekcję
`Symbole` i utworzenie linku Reviewera.

Podczas późniejszej próby linku Windows przekazał jednocześnie `Path` i `PATH`,
co powodowało wyjątek `REVIEWER_INGRESS_COMMAND_FAILED` przed startem
Reviewera. Regresja została usunięta wspólną normalizacją po stronie API i
PowerShell. Skupione testy API przeszły 5/5, składnia 22 skryptów przeszła, a
smoke test potwierdził pojedynczy `Path` oraz proces z przekierowanymi logami.
Rzeczywisty kontroler uzyskał HTTPS Quick Tunnel, potwierdził gotowość i został
zatrzymany bez pozostawienia procesu cloudflared lub pliku stanu. Właściciel
powtarza teraz akcję z UI dla właściwej sesji i kodu. Po zmianie kodu wystarczy
restart samego procesu API; restart komputera nie jest wymagany.

W trakcie tego joba poprawiono również jego prezentację w zakładce `Joby`.
Backend zachowuje monotoniczne `2 × N` jednostek dla dwóch wznawialnych faz,
natomiast UI pokazuje aktywną fazę i rzeczywistą liczbę zdjęć, np.
`Pipeline: 282 / 739 zdjęć`. Pasek, procent i atrybuty dostępności korzystają z
tych samych przeliczonych wartości. Po zmianie przeszło 139 testów Admina,
typecheck oraz skupiony ESLint.

Jedenasty pion TASK-0142 poprawił ręczną korektę geometrii w Reviewerze. Edytor
pokazuje teraz powiększony viewport pojedynczego layoutu z marginesem zamiast
całego zdjęcia strony. Narożniki są nadal zapisywane względem oryginału, a
preview i finalny recrop korzystają z pełnego obrazu źródłowego. Zmiana nie
wprowadza niejawnego uczenia online: poprawia wybrany layout, a zaakceptowane
korekty pozostają materiałem do osobnego, wersjonowanego profilu. Testy
Reviewera przeszły 21/21, a typecheck, lint i produkcyjny build zakończyły się
powodzeniem. Lokalny build zwrócił HTTP 200 i przyjął kod testowej sesji;
wszystkie dostępne gry mają obecnie status `draft`, dlatego ręczny odbiór samego
modala geometrii pozostaje do wykonania po aktywowaniu właściwej gry.

Dwunasty pion TASK-0142 poprawił statystyki image importu w zakładce `Joby`.
Status `Wymaga review` pokazuje czas `updatedAt` jako trwałą granicę zakończenia
automatycznego importu z pipeline'em oraz obliczony czas od `startedAt`. Czas
ręcznego review nie jest doliczany i nie blokuje wyświetlenia tych informacji.
Pełne testy Admina przeszły 140/140; typecheck, lint i produkcyjny build
zakończyły się powodzeniem. Kontrola przeglądarkowa na rzeczywistym jobie
potwierdziła datę `1.08.2026, 12:49:00` i czas automatyki `45 min 53 s`.

Trzynasty pion TASK-0142 usunął fałszywy drift wygenerowanego klienta OpenAPI
na checkoutach Windows. Kontrola porównuje tę samą listę plików i ich treść po
normalizacji wyłącznie końców linii; różnica LF/CRLF jest ignorowana, natomiast
zmiana semantyczna nadal kończy bramkę błędem. Testy klienta przeszły 26/26,
`openapi:check` przeszedł, a pełna komenda `v02:admin:acceptance` zakończyła się
powodzeniem w 86,4 s: PostgreSQL 4/4, Admin 140/140, typecheck, lint, OpenAPI i
produkcyjny build.

Czternasty pion TASK-0142 usunął dwie regresje rzeczywistych danych. Reviewer i
launcher Admina dopuszczają teraz grę `draft` albo `active` przypisaną do sesji,
ale nadal wykluczają `archived`. Bootstrap symboli zapisuje opcjonalne
`resolution=None` jako SQL `NULL`, a nie JSON `null`, więc zgodne osiem grup
może atomowo przejść z `ready` do `applied`. Na jobie `65d6ca14` utworzono osiem
symboli, a produkcyjny Reviewer pokazał szkic `777 v0.2`, układ #8, kolejkę 4050
plansz i komplet symboli. Testy Admina przeszły 141/141, Reviewera 21/21, testy
bootstrapu 10/10; typecheck/lint oraz produkcyjny build Reviewera również
zakończyły się powodzeniem.
