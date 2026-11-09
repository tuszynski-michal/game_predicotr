---
title: Sprawna korekta geometrii i pełne pola bez marginesu
status: accepted
last_updated: 2026-11-09
---

# Sprawna korekta geometrii i pełne pola bez marginesu

Operator zatwierdził 2–4 h na pełne pola 0%, testy i terminalowy Opus5.5/high,
a następnie zlecił połączenie z naprawą powtarzającej się planszy i powolnego
ładowania. Wykonujemy oba taski kolejno, bez kolejnej zgody między nimi.
Merge/push i wdrożenie pozostają osobnymi decyzjami po gotowym wyniku.

## Fakty, cel i granice

`BoardGeometryCorrectionWorkspace.handleSaved` wraca do początku listy.
`reviewAll` zachowuje zapisane pozycje, więc powrót nie jest przejściem dalej.
Cursor zawiera sequence i slot UUID: materializacja deferred może zmienić UUID
tej samej logicznej pozycji. Należy rozpoznawać ją po import/source/position,
bez pomijania innego źródła z tym samym numerem sekwencji.
Bieżący odczyt view=all/limit1/counts=all trwał9.156s, correction4.125s.
Ekran reviewAll wyświetla numer planszy, a nie te liczniki. To ograniczony
pomiar na danych operatora, nie benchmark ani jeszcze wynik poprawki.

Margines8% wynika z `SymbolModelJobSnapshot.crop_padding_fraction`; LAB ma0%.
Wagi bieżącego klasyfikatora to spatial-symbol-cnn-onnx-v1. Zwykłe zastąpienie
stałej naruszyłoby historyczne snapshoty i ich fingerprinty. Cel: nowe wycinki
i dalsza korekta obecnych6219 pozycji używają pełnych pól0%, z jawną nową
wersją renderowania. Stare zatwierdzone geometrie/wycinki/etykiety i importy
zachowują swój przypięty kontrakt. Zmiana cropu nie jest dowodem jakości
klasyfikacji; historyczne raporty nie kwalifikują nowego wejścia.

Bez nowej migracji, dodatkowego trenera, zmiany defaultu geometrii, treningu,
masowego zatwierdzania6219, przepisywania zapisów operatora ani restartów.
Weryfikacja istniejących danych wyłącznie read-only; disposable PG jest dozwolone.

## T1 / TASK-1174 — Następna plansza i szybka lista

Po udanym zapisie reviewAll przechodzi dalej w bieżącym zakresie; kolejka
correction nadal odświeża pierwszy nierozwiązany element. Ostatni zapis nie
wraca do początku. Jawne Od początku i ręczne poprzednia/następna pozostają.
Przy materializacji pomijamy tylko zapisaną logiczną pozycję, z ograniczoną
liczbą odczytów, bez filtrowania innego zdjęcia o tym samym sequence.
Błąd/lost response nie udaje zapisu ani nie przesuwa wyboru bez dowodu sukcesu.
Stare odpowiedzi i zmiana zakresu nie przywracają dawnej planszy.

Nowy jawny counts=none pomija wszystkie agregaty istniejącego endpointu,
z udokumentowanymi zerami nieobliczonych liczników. reviewAll ich nie pokazuje.
Domyślne all oraz correction pozostają zgodne. Pełny pion enum/backend/OpenAPI/
generowany SDK/wrapper/test żądania, bez równoległego endpointu. Utrzymać
informację loading/error. Dalsze optymalizacje wyłącznie po pomiarze przyczyny.

Testy: save reviewAll normal/deferred→current (inne UUID), ostatnia pozycja,
filtr źródła/importu, ten sam sequence innego źródła, lost response/błąd,
spóźniona odpowiedź; regression correction oraz counts all/correction.
NONE nie wywołuje agregatów; realny PostgreSQL paging zachowuje semantykę.
Po zmianie wykonać ograniczony read-only pomiar ścieżki na tej samej bazie.

## T2 / TASK-1175 — Wersjonowane pełne pole0%

Dodać opcjonalną, zamkniętą wersję polityki cropu do snapshotu symboli.
Brak pola zachowuje dokładnie stary payload/fingerprint/8% (LAB0%); nowa jawna
polityka oznacza0%, jest serializowana i wpływa na fingerprint. Wagi, RGB,
rozmiar i interpolacja nie zmieniają się przy tym porównaniu. Nowy resolver
aktywnego modelu emituje pełne pole dla nowych operacji. Historyczny parser
nie dopisuje nowej polityki do starych snapshotów.

Przejść pełną ścieżkę preview→symbole→manual save dla istniejących pending:
kontrakt nowego renderu jest jawnie przypięty do kontekstu i nowej rewizji,
nie podmienia importowego pinu. Ta sama konfiguracja trafia do klasyfikatora,
virtualRenderSpec i sprawdzania aktualności. Zmiana między preview a save
powoduje czytelny konflikt; restart i idempotencja nie mieszają8%/0%.
Symbole, których piksele się zmieniły, zachowują zasady ponownej weryfikacji;
nie dziedziczą starej kwalifikacji automatu. Pełne pole nie usuwa błędu położenia
siatki. Przed kodem doprecyzować task na podstawie sprawdzonego resolvera i repo
manualnej geometrii, bez ukrytej zmiany domeny.

API rozszerzyć tylko tam, gdzie kontekst/transport wymaga nowego pinu; backend,
OpenAPI, SDK, wrapper i test żądania pozostają zgodne. Porównać rzeczywiste
15wycinków8%/0%, sprawdzić pełne granice oraz sąsiada/perspektywę i utrzymanie
starych geometrii/etykiet. Brak GT pozostaje brakiem dowodu klasyfikacji.

## Odbiór

Testy zmienionego pionu, PostgreSQL, interakcje Reviewera, lint/types/build,
docs:check/code-map:check. Nie powtarzać niezwiązanych długich treningów i
znanych baseline Admina. Każdy task: Outcome, terminalowy Opus PASS, osobny
commit/task-close/hash. Jedna runda poprawek; otwarte P0/P1 blokują commit.
Przy rzeczywistym limicie Opus wolno kontynuować kod, bez fikcyjnego PASS.
Przyjęte ograniczenia i wyniki pomiarów podać jawnie. Końcowe wdrożenie nie
jest częścią zgody na kodowanie.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T1 / TASK-1174 — Kolejka i czas odczytu | gpt-6.1-sol | high | Spójna nawigacja, API i regresje | Claude Code claude-opus-5-5/high |
| T2 / TASK-1175 — Pełne pola0% | gpt-6.1-sol | high | Wersjonowanie snapshotów i istniejący workflow | Claude Code claude-opus-5-5/high |
