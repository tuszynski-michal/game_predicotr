---
title: Skuteczne uczenie siatek i test rzeczywistej poprawy
status: accepted
last_updated: 2026-11-11
---

# Skuteczne uczenie siatek i test rzeczywistej poprawy

Operator zaakceptował pełne T1–T4, koszt6–10h, testy i osobne audyty Opus
przez terminal. Na końcu wymagane pytanie o scalenie. Bez zgody na nowy
trening operatora, wdrożenie, migracje operatora ani zmianę defaultu.

T1: kod i audyt Opus R2 PASS, v1.7.602; T2–T4 w realizacji. Historyczny model nadal REVISE.

## Cel

Mocno poprawione plansze uczą model; inne zdjęcia z podobnym błędem sprawdzają
generalizację. Dobre przykłady chronią przed pogorszeniem. Kopie, sesje i
sąsiednie niemal identyczne klatki nie udają niezależnego testu. Wykorzystujemy
istniejący trener, ledger, edytor zawartości i produkcyjną ocenę wycinków.

## T1 / TASK-1182 — Zgodność oceny

Odtworzyć checkpoint600 run39ddc3a3 i jego ONNX na tych samych13zdjęciach A.
Porównać wejścia, preprocessing, detekcje, surowe punkty, fit, matching i metryki.
Wyjaśnić historyczne .8376068376 vs .9145299145 correct-rate; nie zakładać
przyczyny. Współdzielić przygotowanie/ocenę, zachowując osobne PyTorch/ONNX.
Kontrola eksportu obejmuje całe zamrożone A; różnica wpływająca na matching,
wybór checkpointu lub werdykt blokuje odbiór do wyjaśnienia. Test przyczyny,
bez nowego treningu. Raport odróżnia odtworzenie historyczne i nowe zabezpieczenia.

## T2 / TASK-1183 — Materiał i niezależny podział

TRAIN obejmuje aktualne human-approved korekty i dobre przykłady, wagi4:1.
Stara predykcja plus human geometry wskazuje trudność, nie samodzielne GT.
Kategorie: missing-row, shifted-board, clipped-edge, neighbor-takeover,
perspective, incomplete-image. Brak wiarygodnego odniesienia jest unknown.
Pełne zdjęcia uczą detektor, partial punkty; nieopisane plansze nie są tłem.
Zachować TRAIN/A/B/REG, sesje, kopie, historię i10-photo bufory.
Rozliczyć konflikt importu1121: tylko dowiedzione atesty/kolejność; konfliktującą
grupę jawnie wykluczyć z NOWEGO użycia bez kasowania historycznych pinów.
Jeśli minima niemożliwe, dokładne braki zamiast pustego disabled.

REG zawiera oddzielnie próbkę zwykłą i trudną; wybór na zamrożonej bazie i
human GT przed treningiem, seed20261108 po całych grupach. Nie dobierać po
wyniku kandydata; raportować brak reprezentacji kategorii. Wykorzystać istniejące
obrysy, wskazać brakujące tylko w wybranym zestawie; AI draft != human GT.
Zachować30plansz/10zdjęć ślepej powtarzalności TRAIN/A per gra,5pełnych REG,
u/delta przed REG i dotychczasowe caps. Historyczne approvals zachowane.
Manifest pokazuje przydziały/wykluczenia/braki, bez równoległego ledger.

## T3 / TASK-1184 — Pełne uczenie i odbiór

Przypiąć bazę3ed60010-7c3e-5c3b-91aa-4e03eb9bfa5e, rewizje i full-cell0%.
Istniejący full-symbol-content-experiment-v1/R0–R3, bez zastępczego grid-only
pod nazwą pełnego ulepszenia. R3 tylko przy zatwierdzonych danych i failR2/A.
1200steps/arm, ocena200, łącznie<=4800steps/7200s, devicepreflight i trwały
budżet. Ranking istniejący: no-regression, usablephotos/boards, NME, prostszy
wariant, wcześniejszy krok, tylkoA. B=kalibracja, REG=końcowy test.
Ocena oryginał->produkcyjne15cropów: naprawione/zepsute symbole i plansze,
missing/wrongcell/neighbor, pełne zdjęcia, NME+zmierzone delta. Bramka istniejąca
content-v6: brak nowych uszkodzeń/mismatch, brak regresji recall/correct/FP/dup,
NME<=base+delta per gra/A/REG i>=1 dodatkowa usableboard bieżącej gry/REG.
Brak labels=not_evaluable, brak kalibracji automatu nie blokuje uczenia/propozycji.

## T4 / TASK-1185 — Panel, HTML i odbiór

Pion backend/OpenAPI/SDK/wrapper/requesttest: nowe korekty TRAIN vs kontrole,
gotowość detector/geometry/content, konkretne braki i konflikty, jawny mode,
wynik improvement/no-improvement/regression/not-evaluable. HTML oryginał,
humanreference, baza/kandydat,15realcropów; naprawione/bez zmian/pogorszone/
nierozstrzygnięte, bez ukrywania porażek. Nowe korekty rozszerzają legalny TRAIN;
ujawniony REG pozostaje historyczną kontrolą, kolejna świeża ocena wymaga nowej
zamrożonej partii. Stare ręczne dane pozostają zachowane.

## Odbiór i granice

Każdy task: testy własnego pionu, lint/typecheck, właściwy PG/worker/UI,
ONNX, restart/lostresponse, docs:check/code-map:check, Opus terminal,
Outcome/commit/task-close. T1dowodzi zgodności; T2braku leakage i liczników;
T3full detector i ranking/budżet; T4pełnego kontraktu i raportu. Testy są
planowane, nie deklarowane PASS. Schemat zmieniać wyłącznie Alembic jeśli
niezbędne; preferowane istniejące wersjonowane manifesty. Układ3×5; dowód
per gra, brak obietnicy dowolnych przyszłych gier. REVISE historii nie przepisywać.

## Przypisanie modeli do zadań

Operator2026-11-11: z powodu4% pozostałego limitu Codex przekazuje dokończenie otwartychT2–T4 do Claude Code Opus5.5/high. Codex audytuje zmiany Claude; odziedziczone fragmenty Codex wymagają niezależnego przeglądu Claude przed ich zmianą. Dotychczasowe audyty i autorstwo pozostają w historii.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| T1 / TASK-1182 | gpt-6-astra | high | Trening/ONNX/ocena | Claude Code claude-opus-5-5/high |
| T2 / TASK-1183 | claude-opus-5-5 | high | Źródła, role i niezależne odniesienie | gpt-6.1-sol/high — audyt zmian Claude |
| T3 / TASK-1184 | claude-opus-5-5 | high | Pełne uczenie i bramka zawartości | gpt-6.1-sol/high — audyt zmian Claude |
| T4 / TASK-1185 | claude-opus-5-5 | high | Panel/HTML/integracja | gpt-6.1-sol/high — audyt zmian Claude |
