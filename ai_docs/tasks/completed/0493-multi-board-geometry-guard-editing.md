---
title: Multi-board geometry guard editing
status: done
version: v0.10.208
---

# Cel

Umożliwić operatorowi poprawienie wielu siatek jednego zdjęcia w workspace
`Rozlicz problematyczne plansze`, także gdy pojedynczy slot został wcześniej
uznany przez automat za poprawny albo ma już zapisaną decyzję.

# Zakres

- wszystkie sloty źródła są wybieralne i edytowalne,
- osobny szkic geometrii, dyspozycji, maski oraz podglądu A/B dla każdego slotu,
- atomowy zapis wszystkich zmienionych szkiców jednego zdjęcia,
- przełączanie plansz i zdjęć nie wykonuje zapisu,
- ponowna decyzja tworzy kolejną append-only rewizję,
- manifest rozliczeń obejmuje wymagane decyzje oraz jawne korekty slotów
  pierwotnie uznanych za poprawne,
- większy viewport zdjęcia, zoom i zwarty panel sterowania.

# Poza zakresem

- zmiana detektora geometrii, progów bramki albo croppera,
- automatyczne uruchomienie nowego importu,
- usuwanie historycznych rewizji decyzji,
- mutacja joba, stagingu lub danych gry poza jawnym zapisem operatora.

# Relevant docs

- `ai_docs/requirements/ADMIN_APP_V0_2.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/completed/0450-preimport-geometry-guard-decisions.md`
- `ai_docs/tasks/completed/0453-geometry-guard-resolution-admin-ui.md`

# Zależności

- board-level report v2 i checksum-bound source asset,
- append-only decyzje geometrii,
- browser-import schema v7 oraz loader manifestu rozliczeń.

# Testy

- API udostępnia końcową siatkę i diagnostykę również dla zielonego slotu,
- zapis przyjmuje jedną partię zmienionych czerwonych i zielonych slotów tego
  samego źródła,
- nierozliczone czerwone sloty nadal blokują zamknięcie manifestu,
- worker wymaga pokrycia wszystkich czerwonych slotów, ale dopuszcza jawne
  korekty zielonych slotów należących do raportu,
- obcy slot, źródło lub numer pozostaje odrzucony fail-closed,
- szkice nie giną podczas przełączania plansz i zdjęć,
- `Następne zdjęcie` nie wywołuje zapisu,
- zoom nie zmienia współrzędnych zapisywanej geometrii.

# Definition of Done

- wszystkie plansze bieżącego zdjęcia można kliknąć i edytować,
- każda plansza zachowuje własny szkic podczas przełączania,
- `Zapisz decyzję` zapisuje atomowo wyłącznie zmienione szkice bieżącego
  zdjęcia, a nawigacja nie zapisuje,
- istniejącą decyzję można ponownie otworzyć i zapisać jako następną rewizję,
- zdjęcie ma zoom i większą powierzchnię roboczą, a kontrolki są zwarte,
- API, OpenAPI, klient, worker i Admin zachowują jeden spójny kontrakt,
- skoncentrowane testy, lint, typecheck, OpenAPI i build są zielone,
- dokumentacja opisuje nową semantykę jawnej korekty zielonego slotu.

# Outcome

- Workspace pokazuje i pozwala edytować wszystkie sloty bieżącego zdjęcia:
  wymagające decyzji oraz wcześniej uznane przez automat za poprawne.
- Każdy slot ma niezależny szkic geometrii, dyspozycji, maski i podglądu A/B.
  Przełączenie planszy lub zdjęcia nie zapisuje danych, a `Zapisz decyzję`
  wysyła atomowo wyłącznie zmienione szkice bieżącego źródła.
- Wcześniejszą decyzję można ponownie otworzyć i zapisać jako kolejną
  append-only rewizję. Czerwone sloty nadal wymagają rozliczenia, natomiast
  zielone mogą otrzymać jawną korektę operatora.
- Manifest rozliczeń ma schemat v2 obejmujący wymagane decyzje i opcjonalne
  korekty zielonych slotów. Worker nadal czyta historyczny schemat v1 i
  odrzuca decyzje spoza raportu.
- API, OpenAPI i klient udostępniają dla każdej planszy siatkę symboli,
  szerszą geometrię analityczną, diagnostykę oraz historię decyzji.
- UI otrzymało większy, przewijany viewport, zoom 75–300% oraz zwarty panel
  plansz i decyzji.
- Sprawdzenie danych gry `777` o kodzie `new-siedem` nie wykazało zapisanej
  decyzji guard do cofnięcia. Nie wykonano destrukcyjnej mutacji danych;
  poprawiony ekran pozwala teraz ponownie edytować każdą utrwaloną decyzję.

## Weryfikacja

- skoncentrowane testy API i workera: 80/80,
- pełne testy Admina: 419/419,
- Ruff dla zmienionych modułów: bez błędów,
- typecheck Admina i klienta API: bez błędów,
- lint Admina: bez błędów,
- kontrola OpenAPI i wygenerowanego klienta: bez różnic,
- produkcyjny build Admina: zakończony poprawnie,
- Prettier dla wszystkich plików zmienionych w tasku: bez różnic.

Globalny `format:check` nadal wskazuje 35 wcześniejszych, niezwiązanych plików.
Nie były one formatowane ani dołączane do tego taska. Pełny mypy został
przerwany po 60 sekundach bez nowego wyniku; skoncentrowane testy Pythona oraz
Ruff przeszły poprawnie.
