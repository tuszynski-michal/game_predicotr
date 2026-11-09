---
title: Wdrożenie pełnych symboli i przygotowanie danych operatora
status: active
last_updated: 2026-11-09
---

# Wdrożenie i dane — 2026-11-09

Operator zatwierdził integrację, push, migracje0182/0183 oraz restart API,
Admina, Reviewera i workerów. Następnie wybrał przygotowanie danych do pełnego
eksperymentu, bez zastępowania go legacy grid-only, i pozostawił Reviewer
wyłącznie lokalny. Publiczny tunel nie został ponownie uruchomiony.

## Wynik wdrożenia

- T0–T5 i TASK-1169 są w main/origin. Poprawka startu: v1.7.579/a5e78251,
  zapis hasha v1.7.580/ec1ee483. TASK-1169 Opus5.5/high R1 PASS,0P0/0P1;
  właściwy raport i receipt są w `ai_docs/quality/`.
- Baza: `0183_production_cell_evaluation`, manifestv22, pięć gier. Zachowane
  166971 źródeł, cztery przypisania i default3ed60010/revision2.
- API8000, Admin3000 i Reviewer3001 odpowiadają200; general(7wątków) i
  grid_training(1wątek) działają. image_selection pozostaje zatrzymany.
- Powtórny odczyt usług i sesji wykonano z nowego procesu. Testy kodu i granice
  dowodu pozostają w raportach TASK-1168/1169; smoke nie jest testem jakości modelu.
- Pierwsze uruchomienie API zablokował stary head guard. TASK-1169 usunął
  przyczynę; odczyt prawdziwej bazy i start obu workerów potwierdziły poprawkę.

Dowody lokalne: root `artifacts/full-symbol-deployment-20261109/`
(migration, push, preflight, db-before/after, logi usług i live-smoke).

## Przygotowane dane

Zamrożona kohorta `dae22c06-33cf-5f6a-accc-ce3166d13cf3`, manifest
`1b97e3a11ee37906367d930a5955ce4299eb2a9e8c9135792c5a0626b54b0c93`.
Role i punkty geometrii pozostają zachowane.

| Materiał | Stan |
|---|---|
| TRAIN geometrii | 10 pełnych zdjęć,90plansz |
| A geometrii | 5 pełnych zdjęć,45plansz |
| Szkice zawartości TRAIN | 5 innych zdjęć,45plansz,675pól; origin=ai_proposal, humanApproval=false |
| Szkice rozstrzygnięte przez automat pomocniczy | 378visible,297unknown; wszystkie wymagają sprawdzenia człowieka |
| Ślepy pomiar | sesja f5f2cc6c-9e53-525b-b76f-58fd33975855,50plansz/10zdjęć,pass1,0/50 |
| Pula B | 0zdjęć |
| Historyczny REG | 13częściowych zdjęć,21plansz; nie jest świeżym testem |
| Zatwierdzone etykiety zawartości | 0; żaden szkic AI nie jest ludzkim GT |
| Pochodzenie bazy | dwa ancestor versions,0zainstalowanych dostawców dowodów; nierozstrzygnięte |

Szkice powstały wyłącznie dla pięciu TRAIN poza sesją ślepą. Pomocnicze,
lokalne wykrywanie obrysu z pikseli nie jest nowym silnikiem produkcyjnym,
wynikiem R0–R3 ani dowodem kompletności. Część szkiców wymaga narysowania od
nowa. Zapisano je przez istniejące API z idempotencją i pinami źródła;
nowy proces odczytał wszystkie45 z humanApproved=false. Brakujące/zasłonięte
treści nie zostały dopisane jako pełne, widoczne symbole.

Sesja ślepa obejmuje wszystkie45plansz A oraz pięć plansz z pięciu innych
zdjęć TRAIN. Nie zapisano w niej punktów, etykiet, propozycji ani zatwierdzeń.
Dwa przebiegi muszą wykonać rzeczywisty operator. u/δ nie są jeszcze ustalone.

HTML root `artifacts/full-symbol-training-20261109/przygotowanie-danych.html`
pokazuje wyłącznie szkice TRAIN.675plików podglądu, nawigację45plansz,
filtr297unknown i przełącznik obrysu zweryfikowano; sprawdzono też render
lokalnego HTML. Podgląd adnotacji jest jawnie odróżniony od wejścia sieci.

## Dalsze warunki

Najpierw operator sprawdza szkice w **Etykiety zawartości zdjęć** i wykonuje
**Pomiar powtarzalności etykiet**. Do pełnego eksperymentu nadal brakuje
zatwierdzeń, świeżych pełnych kontroli i dowodu wykluczeń rodowodu. Sama
gotowość starszego screen+grid nie dowodzi gotowości R0–R3.

Trusted provider index nie jest skonfigurowany; dla wersji3ed60010 i158a740f
`RECORDING_ANCESTOR_EXCLUSIONS_UNRESOLVED` pozostaje rzeczywistym brakiem.
Nie utworzono fikcyjnych nagrań ani deklaracji niezależności.691zdjęć stagingu
pozostaje potencjalnym materiałem do sprawdzenia dopuszczalności, nie gotowym
REG. Film nie jest wymagany.

Nie uruchomiono nowego treningu, nie zmieniono defaultu ani progów i nie
zaimportowano691zdjęć.309istniejących zdjęć i ręczne korekty zachowano.
Pełne operational receipts są lokalnie w root `artifacts/full-symbol-training-20261109/`.
