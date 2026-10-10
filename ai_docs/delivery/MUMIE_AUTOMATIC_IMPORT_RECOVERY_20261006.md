# Automatyczny import Mumii i gotowa weryfikacja symboli

Status: wykonywany na polecenie użytkownika z 2026-10-06.

## Stan i cel

TASK-0884 uruchomił import, który odkłada wszystkie siatki neural do ręcznej
korekty. Pierwszy zapis cropów tworzy stan rebuilding bez zadania backfill;
panel nie oferuje wznowienia takiego stanu. To dwie potwierdzone blokady
przepływu. Użytkownik zlecił ich naprawę i uruchomienie w MAIN.

## TASK-0886 — cały przepływ

Nowe importy z zamrożonym neural proposal otrzymują wersjonowaną politykę
neural-auto-crop-v1 w istniejącym payloadzie i fingerprintach. Stare joby
pozostają odtwarzalne według starej polityki. Istniejący endpoint managed
reprocess przypina aktualny neural descriptor i nową politykę.

Każdy jednoznacznie przypisany, pełny lattice 24 węzłów daje 15 wirtualnych
cropów RGB w istniejącym rendererze. Zachowujemy wnętrze lattice, checksumy,
pozycję i sequence_number. Brakujący albo niepełny slot pozostaje w korekcie,
bez blokowania pełnych sąsiadów. Automatyczna geometria nie jest zatwierdzeniem
człowieka; symbole pozostają przewidywaniami do zbiorczej weryfikacji.
NEURAL_GRID_GATE_UNCALIBRATED pozostaje diagnostyką jakości.

Wspólna bramka projekcji dopuszcza tylko aktualne pełne neural cropy powiązane
z polityką, źródłem i zapisanym lattice. Nie znosi innych bramek. Reprocess
blokuje sekwencje i zachowuje ręcznie zatwierdzoną geometrię oraz oznaczenia.
Stare nierozstrzygnięte pending można zastąpić audytowalnym aktualnym wynikiem,
bez usuwania historii.

Zapis pierwszych cropów inicjalizuje gotową pustą projekcję wyłącznie przy
udowodnionym braku starszej historii. Historyczne rebuilding bez aktywnego joba
uruchamia istniejący trwały backfill; panel umożliwia wznowienie i odróżnia
oczekiwanie od pracy. Aktywny job jest ponownie używany. Błąd jest widoczny,
bez nieskończonych automatycznych prób.

Odbiór panelu wykazał historyczny stan gotowych cropów z niedostępnymi
licznikami. Istniejący backfill kończy także odbudowę bieżącej semantyki
liczników w ograniczonych partiach z trwałym kursorem. Gotowe liczniki
pozostają bez przebudowy; przerwany krok jest wznawiany z zapisanego stanu.

Istniejący przycisk zbiorczego zatwierdzania był wyłączony na stałe.
Profil Mumii włącza go dla zaznaczeń z obrazem, przez istniejący podgląd
i trwałą operację. Domyślne zachowanie wspólnego paska dla innych gier
pozostaje bez zmian; pola poza zdjęciem nadal nie mogą zatwierdzać obrazu.

## Odbiór i wdrożenie

Testy: pełny lattice → 15 cropów, brak środkowej pozycji bez przesunięcia,
wewnętrzne węzły zachowane, legacy replay, ochrona ludzkich poprawek, zimny
restart/retry oraz rebuilding bez joba → trwałe wznowienie. API/OpenAPI/SDK,
typy i test żądania obejmują opcjonalną politykę. Nie zmieniamy schematu bazy.

Po testach kontrolowany restart wyłącznie zmienionych usług MAIN. Odzyskanie
istniejącego importu Mumii i projekcji przez ich obecne endpointy; kontrole
liczności, kolejności i ochrony ręcznych danych. Praca partiami po źródle,
bez pełnej kopii bazy, benchmarku 500000 plansz albo generowania masy fixture.
Zakres nie obejmuje 777, usuwania danych, nowego treningu, aktywacji modelu ani
mechaniki symbolu specjalnego. Wynik i ograniczenia zapisujemy w TASK-0886.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0886 | gpt-6.1-sol | high | Spójny pion importu, renderera, projekcji i UI z ochroną danych. Ponowna analiza przy konflikcie źródeł prawdy. | Odrębny przegląd własny i testy regresyjne; bez delegowania. |
