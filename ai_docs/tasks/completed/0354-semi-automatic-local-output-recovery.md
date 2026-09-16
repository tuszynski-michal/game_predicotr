# TASK-0354 — Lokalny output i recovery półautomatycznej selekcji

Status: `done`

## Cel

Zapisać automatycznie wybrane JPEG-i do lokalnego katalogu operatora bez
zmiany bajtów, z trwałym manifestem, pojedynczą operacją oczekującą,
checksum-bound acknowledgement i wznowieniem po restarcie przeglądarki.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `.tmp/TASK-0350-0357-semi-automatic-selection-plan.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Zakres

- `semi-automatic-image-selection-output-v1.json` z pełną tożsamością runu,
  wyborów, luk, konfliktów, checkpointu synchronizacji i historii;
- lokalny writer File System Access API, który kopiuje niezmienione bajty,
  ponownie sprawdza SHA-256 i nigdy automatycznie nie nadpisuje innej treści;
- recovery jednej zapisanej przed mutacją operacji oczekującej;
- idempotentna synchronizacja i checksum-bound acknowledgement istniejącego
  endpointu API;
- IndexedDB przechowujące wyłącznie uchwyty katalogów i mały stan UI, bez
  Blobów JPEG.

## Poza zakresem

- zakładka, konfigurator, upload i progres (TASK-0355);
- REVIEW_MODE i EDIT_SOURCE_MODE (TASK-0356);
- ręczne dodawanie lub zastępowanie wyborów;
- zmiany schematu PostgreSQL i nowe endpointy API.

## Invarianty

- oryginalne bajty JPEG pozostają niezmienione;
- inna zawartość pod `seq_<start>-<end>.jpg` jest konfliktem i nie jest
  nadpisywana;
- manifest należący do innego runu blokuje zapis;
- acknowledgement następuje dopiero po ponownym odczycie lokalnego pliku i
  zgodności SHA-256;
- wznowienie rozstrzyga pending operation przez obecność i checksumę celu;
- IndexedDB nie przechowuje Blobów ani bajtów obrazów.

## Weryfikacja

- testy manifestu, walidacji tożsamości i deterministycznego serializowania;
- zapis nowych bajtów, idempotentny replay i konflikt bez nadpisania;
- recovery po przerwaniu przed i po zapisie pliku;
- acknowledgement dopiero po zgodności checksummy;
- test struktury lokalnego rekordu bez Blobów;
- lint, typecheck i testy Admina oraz kontrola formatu.

## Outcome

- Dodano manifest outputu v1 związany z dokładnym runem, źródłem, granicami i
  fingerprintami oraz z jedną journalowaną operacją oczekującą.
- Adapter File System Access API kopiuje oryginalne bajty, wykonuje read-back
  SHA-256, chroni identyczne pliki i blokuje odmienną zawartość.
- Koordynator synchronizacji uzgadnia awarie przed i po zapisie, ponawia samo
  acknowledgement po utracie odpowiedzi i nie pobiera ponownie zgodnego JPEG-a.
- IndexedDB v1 zapisuje wyłącznie uchwyty katalogów, checksummę manifestu i
  mały stan widoku; walidator odrzuca dodatkowe pola z Blobami.
- Rozszerzono typowany klient Admina o istniejący asset źródłowy i
  checksum-bound acknowledgement. Nie zmieniono API ani OpenAPI.
- Dodano siedem testów Admina oraz test transportu klienta; testy Admina,
  lint, typecheck i build klienta przechodzą.
