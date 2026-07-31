---
title: Open product and architecture questions
status: active
last_updated: 2026-07-29
---

# Otwarte pytania

Ten dokument zawiera wyłącznie pytania, które nadal wymagają odpowiedzi.

Q-001–Q-015 oraz Q-018 zostały rozstrzygnięte. Obowiązujące decyzje znajdują
się w [Decision Log](../process/DECISION_LOG.md), a dokładny zapis odpowiedzi
właściciela w
[ukończonym Task 0001](../tasks/completed/0001-architecture-clarification.md).

## Obraz i import

### Q-016 — Stabilność układu strony

**Status: closed 2026-07-28.** Strona ma maksymalnie dziewięć mini-layoutów
w siatce 3 × 3. Ostatnia strona ciągu może zawierać mniej pozycji, ponieważ
liczba layoutów gry nie musi być podzielna przez dziewięć. Pozycje występują
bez luk od indeksu 0 w kolejności row-major. Pełna strona nadal wymaga
dziewięciu pozycji.

### Q-017 — Zestaw treningowy

**Status: closed 2026-07-28.** Właściciel potwierdził możliwość zebrania około
100 przykładów na symbol. Obecne 43 zdjęcia obejmują 387 layoutów i 5805
automatycznie utworzonych cell crops. Właściciel nie wycina ich ręcznie;
manualna praca dotyczy zatwierdzenia lub korekty etykiety. Podział
train/validation/test nadal odbywa się według zdjęcia źródłowego.

## Administracja i wdrożenie

### Q-019 — Wielu administratorów

**Status: closed 2026-07-29.** Lokalny panel początkowo obsługuje właściciela,
ale docelowo zdalny moduł review ma umożliwić pracę co najmniej jednej innej
osobie. Każda decyzja musi mieć aktora, sesję, append-only audyt i optimistic
revision. Zdalny recenzent ma dostęp wyłącznie do wskazanej gry i review, nie do
pełnej administracji.

### Q-021 — Transport zdalnego review

**Status: closed 2026-07-30.** Dla czasowego zdalnego review v0.1 wybrano
Cloudflare Quick Tunnel do publicznego originu samej aplikacji Reviewer.
Połączenie jest wychodzące, używa losowego adresu HTTPS i nie otwiera portu
routera. API, Admin i PostgreSQL pozostają na loopback. Tryb nie ma SLA i służy
testom/pilotowi; stały adres wymaga później named tunnel.

### Q-020 — Aplikacja referencyjna

Czy istnieje zgoda właściciela aplikacji Windows na analizę jej zachowania, plików i ruchu sieciowego? Bez zgody prace należy ograniczyć do obserwacji funkcji, dostarczonych zdjęć i ręcznego tworzenia specyfikacji.

## Panel Admin 0.2

Poniższe pytania są omawiane przed zadaniem `0.2`, którego semantykę zmieniają.
Nie blokują TASK-0119, kontrolowanego resetu TASK-0120 ani wydania `0.1`.

### Q-022 — Fizyczne usuwanie gry

Czy `Usuń` ma działać wyłącznie dla gry bez zależnych importów, reguł, wydań i
audytu, czy właściciel oczekuje kaskadowego usunięcia całej historii? Zalecenie:
pozwolić fizycznie usunąć tylko pusty szkic, a pozostałe gry archiwizować.

### Q-023 — Usuwanie wydania Android

Czy przycisk usuwa tylko ciężki APK/snapshot, zachowując rekord, manifest i
checksumy, czy ma usuwać również wpis wydania? Zalecenie: usuwać wyłącznie
artefakty możliwe do odtworzenia i zachować audytowalny rekord release.

### Q-024 — Retencja jobów

Jak długo i dla których statusów zachowywać pełne szczegóły jobów oraz ich
diagnostyczne artefakty? Zalecenie: zawsze zachować minimalny rekord audytowy,
a ręczny cleanup ograniczyć do ciężkich logów/eksportów zakończonych jobów.

### Q-025 — Wybór folderu zdjęć

Czy akceptowalny jest kontrolowany natywny dialog Windows uruchamiany przez
lokalny backend, czy preferowane jest ręczne wklejenie ścieżki? Zwykła strona
webowa nie może bez zgody przeglądarki odczytać dowolnego katalogu dysku.

### Q-026 — Jeden widoczny zestaw reguł

Czy „tylko jedna wersja” oznacza wyłącznie ukrycie historii w interfejsie, czy
oczekiwane jest nadpisywanie opublikowanych reguł? Zalecenie: pokazywać jeden
bieżący workspace, ale każdą publikację utrwalać jako nową niezmienną wersję.

### Q-027 — Docelowa liczba layoutów

Czy docelowe 500 000 obowiązuje każdą grę w `0.3`, czy ma być konfiguracją
gry? W `0.2` liczba layoutów jest jawnie ustawioną wielkością małego datasetu
testowego i nie rozstrzyga tej decyzji.

### Q-028 — Źródło numeru brakującej sekwencji

Czy kompletność ma opierać się wyłącznie na numerze rozpoznanym spod planszy,
czy administrator może ręcznie przypisać numer, gdy OCR jest niepewny lub
nieczytelny?

### Q-029 — Wybór lepszego zdjęcia duplikatu

Czy automatyczny ranking ostrości, kompletności symboli i geometrii wystarczy,
czy w `0.2` wymagany jest również ręczny wybór źródła dla tej samej sekwencji?

### Q-030 — Niezgodna liczba wykrytych symboli

Co ma zrobić pipeline, gdy podana liczba symboli wynosi np. 10, ale klastry
jednoznacznie wskazują 9 albo 11? Zalecenie: nie tworzyć symboli po cichu,
pokazać konflikt i poprosić o zatwierdzenie/scalenie propozycji.

### Q-031 — Własność plików wybranego folderu

Czy po wskazaniu folderu system ma skopiować obrazy do kontrolowanego storage,
czy przetwarzać je wyłącznie z lokalizacji użytkownika? Zalecenie: kopiować
oryginały content-addressed do storage, aby przeniesienie folderu nie psuło
pochodzenia, wznowienia, review ani późniejszego backupu.

### Q-032 — Zakres operacji „Usuń layouty”

Czy operacja ma odłączyć bieżący nieopublikowany import, usunąć tylko jego
pliki robocze, czy również kanoniczne layouty bez historii wydań? Zalecenie:
nie pozwalać kasować danych użytych przez release ani decyzji człowieka;
fizyczny cleanup ograniczyć do nieopublikowanego importu po jawnym
potwierdzeniu i zachowaniu minimalnego audytu.

## Warunek rozpoczęcia etapów

- M1 nie ma otwartych pytań blokujących.
- Techniczne decyzje toolchain/build podejmowane w M1.1 nie wymagają odpowiedzi
  produktowej, ale muszą zostać zapisane w Decision Log.
- Q-016/Q-017 są zamknięte. D-057 dopuszcza M6 na przejrzanych goldenach i
  automatycznych cropach, przy OCR pozostającym w trybie manual-review-only.
- M2 i lokalny M6.5 mogą używać panelu właściciela na loopback. Q-019 jest
  zamknięte; zdalna autoryzacja wielu recenzentów należy do M8.7 i wymaga
  rozstrzygnięcia Q-021.
- Analiza aplikacji referencyjnej poza obserwacją wymaga odpowiedzi na Q-020.
- Q-022–Q-032 blokują tylko zadania Admina `0.2`, których zachowanie zależy od
  odpowiedzi. Nie blokują TASK-0120 ani reprezentatywnego wydania `0.1`.
