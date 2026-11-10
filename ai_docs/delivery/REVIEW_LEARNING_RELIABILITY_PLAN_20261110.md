---
title: Wydajna weryfikacja i niezawodne uczenie z korekt
status: accepted
last_updated: 2026-11-10
---

# Wydajna weryfikacja i niezawodne uczenie z korekt

Operator zatwierdził cały zakres czterech problemów, 6–10h, testy i audyt
Claude Code Opus5.5 przez terminal. Koniec pracy: raport i pytanie o merge.
Bez restartów, operacji zapisu na danych operatora, treningu lub aktywacji.
Gałąź codex/review-learning-performance, baza main f4d16729/v1.7.593.

## Fakty i cel

Na rzeczywistych danych partia2487 komórek trwa360s; partie około500
trwają65–77s wobec31–51s w starszych zapisach. Zarejestrowano56s zapytania
_exclusion_counts oraz czekające advisory lock i kolejkę7 partii. Nowa
partia dodała93285 komórek. To pomiary odczytowe, nie pełny profil kosztów.
Operator zgłasza także PREVIEW_STALE po długim freeze oraz disabled start
uczenia pomimo nowych korekt. Ich dokładne przyczyny wymagają odtworzenia.

Docelowo zatwierdzanie aktualizuje tylko potrzebne dane, wolne przygotowanie
treningu nie utrzymuje długo blokady zapisów, a nieaktualny manifest nie
powoduje utraty polecenia ani nie jest ignorowany. Panel pokazuje prawdziwe
braki i rekomenduje cel uczenia na podstawie dostępnych danych.

## T1 / TASK-1177 — Zapis symboli i zamrażanie manifestu

Prześledzić SqlAlchemySymbolCellReviewBulkOperationWorker.process_next_batch,
SqlAlchemySymbolCellReviewMutationRepository.apply_board_mutations,
SqlAlchemySymbolCellTrainingSourceRepository.inventory/_exclusion_counts
i VerifiedTrainingCohortService.preview/freeze. Ustalić koszt na istniejących
zapytaniach i ograniczonych testach PostgreSQL; nie budować sztucznego
wielomilionowego korpusu.

Usunąć powtarzane odczyty i agregacje w trwałym zapisie, zachowując atomowość
planszy, kolejność blokad, własność sekwencji, aktualność cropów, audyt,
liczniki, projekcje wyszukiwania/supergry i retry. Nie zwiększać równoległości
przez usunięcie ochrony własności. Wprowadzać migrację Alembic wyłącznie,
jeżeli pomiar planów potwierdzi potrzebę zmiany indeksów/funkcji.

Przygotowanie danych i attestation plików oddzielić od krótkiej walidacji
i zapisu pod blokadą. Zachować realną kontrolę rewizji, ochronę holdoutów,
idempotencję i aktualną zgodę na manifest. Zmiana zatwierdzonych danych
może wymagać nowego podglądu, ale nie może prowadzić do długiego freeze
trzymającego blokadę i kończącego się nieczytelnym błędem. Nowych danych nie
zamrażać automatycznie pod zgodą dotyczącą starego podglądu. W UI wyjaśnić
konflikt, odświeżyć podgląd i wymagać ponownego potwierdzenia; trwające zapisy
zbiorcze pokazać jako jawny warunek oczekiwania. Zmianę API przeprowadzić
przez backend/OpenAPI/SDK/wrapper/test żądania.

Odbiór: zgodność wyników przed/po, krótsza liczba zapytań i utrzymywania
blokad, porównanie czasu na tych samych ograniczonych danych; stale nadal
odrzuca zmienione etykiety, niezmienione preview daje ten sam manifest.
Przerwanie i utrata odpowiedzi nie dublują zdarzeń lub kohort.

## T2 / TASK-1178 — Gotowość korekt i zrozumiały cel uczenia

Odtworzyć bieżący preview MumieA2 i powody disabled bez zmieniania danych.
Naprawić błędną kwalifikację/liczniki/aktualizację panelu, jeżeli występują.
Prawdziwy brak przykładów pozostaje blokadą z konkretną liczbą i instrukcją;
nie zmniejszać minimów, nie przenosić holdoutów i nie tworzyć human approval.

Zalecany wybór celu ma wynikać z danych: detektor+punkty tylko przy gotowych
pełnych zdjęciach, w przeciwnym razie punkty przy spełnieniu ich warunków.
Wyświetlić wybrany cel i uzasadnienie; ręczne sterowanie pozostawić jako
zaawansowane. Nie uruchamiać samoczynnie GPU po korekcie ani nie stosować
modelu bez potwierdzenia. Wyjaśnić, że korekty są materiałem, a trening i test
są oddzielnym, jawnym procesem. Backend pozostaje właścicielem gotowości
i wybranego kontraktu; stare polecenia zachowują przypięty tryb.

Odbiór: aktualne korekty widoczne po refresh, zrozumiały każdy disabled,
domyślny wybór zgodny z gotowością, brak cichego zmniejszenia zakresu;
niezmienione bezpieczeństwo A/B/REG, budżetów, freeze i zastosowania wersji.

## Weryfikacja i granice

| Problem | Zadanie | Dowód |
|---|---|---|
| Wolny bulk i blokady | T1 | PG zapisów, konkurencja, liczba SQL, ograniczone porównanie czasu |
| Długi freeze / PREVIEW_STALE | T1 | stabilny preview, realny konflikt, krótka sekcja blokady, UI/replay |
| Disabled uczenia siatek | T2 | aktualne ręczne korekty, liczniki i powody blokad API/UI |
| Niezrozumiały cel | T2 | rekomendacja pełne/częściowe, wyjaśnienie i ręczny override |

Testy najpierw zmienionych pionów, następnie regresje API/workera, PostgreSQL,
interakcje Admina, SDK, lint/typecheck/build, docs:check i code-map:check.
Każdy task: Outcome, jeden audyt Opus i runda poprawek, task-close i osobny
commit. Otwarte P0/P1 blokują commit; brak audytora nie oznacza PASS.
Wyniki testów i przyspieszenie raportować dopiero po pomiarze. Nie obiecywać
kilkunastu sekund dla dowolnej wielkości partii. Nie naprawiać obcych regresji.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T1 / TASK-1177 — Zapis i manifest symboli | gpt-6.1-sol | high | Wspólny pion transakcji i snapshotów z ochroną danych | Claude Code claude-opus-5-5/high |
| T2 / TASK-1178 — Gotowość i dobór celu | gpt-6.1-sol | high | Spójna kwalifikacja danych i prowadzony interfejs | Claude Code claude-opus-5-5/high |
