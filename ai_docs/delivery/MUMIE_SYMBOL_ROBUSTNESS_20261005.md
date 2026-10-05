---
title: Mumie — odporność na podświetlenie i linie wygranej
status: complete
last_updated: 2026-10-05
---

# Poprawa odporności modeli symboli

Operator polecił autonomicznie sprawdzać i poprawiać problemy. TASK-0856
wykazał na rzeczywistych zdjęciach błędne propozycje jasnych J/K z zieloną
linią wygranej. To nie problem samego podziału tych przykładowych pól.
Nie zmieniamy etykiet człowieka i nie trenujemy na propozycjach modeli.

## Stan, cel i decyzja

W pierwszych112 zdjęciach3194 z15120 rozpoznań wymagało review,772 razy
modele się nie zgadzały. Kontaktowe kadry ujawniły wyraźne J/K przewidywane
jako Q/Mumia. Mała walidacja84 pól nie reprezentuje tych wszystkich wariantów.
Rozszerzamy wyłącznie lokalny eksperyment symboli o wersję2, z tym samym
kwalifikowanym development255/validation84. Obrazy partii600 nigdy nie
wchodzą do uczenia ani wyboru epoki/temperatury/wagi. Ta przejrzana partia
jest teraz materiałem eksploracyjnym, nie niezależnym końcowym testem.

## TASK-0857 — ograniczony trening odporności i ponowne rozpoznanie

Proponowany `vision_lab/symbol_augmentation.py` definiuje zamrożone
`symbol-light-payline-v1`. Transformacje używają deterministycznego SHA
sample_id/seed/epoch. W przestrzeni pikseli0–1, po łagodnej istniejącej
affine: gamma0.65–1.6, brightness0.65–1.5, contrast0.7–1.3,
saturation0.1–1.5 i hue±0.12. W jednej trzeciej próbek jedna lub dwie
cienkie zielone linie1–3px o alpha0.25–0.7, z ograniczonym położeniem
i skosem, symulują obserwowaną nakładkę. Nie tworzy to nowych zdjęć,
etikiet ani dodatkowych rekordów. Grayscale następuje po augmentacji.
Walidacja i inferencja zachowują dokładny wcześniejszy preprocess.

Dodajemy opcjonalne `mumie-symbol-rgb-v2`/`mumie-symbol-gray-v2` i `--generation 2`
do istniejącego SymbolRunManager/CLI. Domyślne v1, jego20epok i checkpointy
pozostają bez zmian. V2: od zera,20epok, seed20261005, batch32, AdamWlr0.001,
max1800s/10000 kroków per wariant, ten sam neutralny trwały protokół.
Osobny skonfigurowany root v2; najwyżej jeden train na wariant/kohortę/root.
Nowy wersjonowany model wiąże nową augmentację bez zmiany rendererów i bramek.

Odczyt rzeczywistego `TrainingConfiguration` ujawnił wspólny limit20 epok.
Pierwotna propozycja40 została odrzucona przed admission, bez uruchomienia
workerów i bez zużycia budżetu treningu. Zachowujemy limit20 i istniejący
kontrakt API zamiast rozszerzać globalną konfigurację dla tej lokalnej próby.

Epoka i kalibracja używają tylko oryginalnej walidacji, bez osłabiania testów.
Przed ponownym większym przebiegiem wymagamy co najmniej83/84 każdego
wariantu oraz ONNX parity całych84 przypadków. Gorszy run jest zachowany
jako niezakwalifikowany; nie zastępuje wersji1. Brak poprawy po tej jednej
ograniczonej parze nie powoduje kolejnych losowych eksperymentów. Wymaga
świeżych świadomych etykiet trudnych wariantów.

Batch CLI dostaje opcjonalną generację2; default1 zachowuje stare manifesty.
Nie zmieniamy manifestu600 ani wcześniejszych wyników. Nowy root inferencji
wiąże własne modele, kalibrację i dokładnie te same wybrane źródła/SHA.
Geometrię i cropy przejmujemy z niezmiennych wyników TASK-0856, po kontroli
wszystkich SHA i zgodności pikseli ponownie wyrenderowanego pola. Nie liczymy
na nowo RANSAC ani nie mieszamy zmiany siatki ze zmianą klasyfikatora.
Porównanie podaje liczbę review, disagreements i przykładowe wizualne błędy,
bez accuracy na zdjęciach bez referencji. Wysoka pewność sama nie dowodzi
poprawy. Wizualny odbiór przez agenta nie staje się zatwierdzeniem człowieka.

## Odbiór, testy i granica

Najpierw commit i odbiór TASK-0856. Następnie testy deterministycznej augmentacji,
zakresu pikseli, epoch0 bez transformacji, wersji1 bez regresji, admission/budżetu
v2, wznowienia oraz starego i nowego batchu. Format/lint/typecheck, oba realne
runy i eksporty, zachowane oryginalne SHA, raport i osobny commit.
Po zakwalifikowanych modelach ponowna rzeczywista inferencja600 zdjęć
z tymi samymi kontrolami trwałości. Bez DB, nowych zgód, aktywacji i wdrożenia.

Rzeczywistą granicą jest potrzeba nowych etykiet jasnych/podświetlonych
wariantów lub ślepej niezależnej referencji do pomiaru jakości. Nie zatrzymujemy
się po samym zapisie planu ani przy kolejnych rutynowych testach.

## Wynik i rzeczywista granica

TASK-0857 ukończony. Oba warianty V2: 20 epok, walidacja 83/84, ONNX parity
wszystkich 84 cropów. Na tych samych 600 zdjęciach i 80940 identycznych
wycięciach niepewność wzrosła z 15626 do 16024, a disagreement z 3494 do
4047. Wizualnie występują poprawy i regresje; nie wykazano przewagi V2.
Nie aktywowano modeli. Wymagana teraz interakcja to prawdziwe etykiety
trudnych wariantów i potwierdzenie siatek, nie zgoda na rutynowe testy.

36 testów, format/lint, scoped mypy, eksporty, zachowanie SHA oryginałów,
dokładne wznowienie i pełny replay w nowym procesie PASS. Wszystkie kryteria
planu oraz taska porównano z artefaktami. Raport:
`ai_docs/quality/MUMIE_SYMBOL_ROBUSTNESS_20261005.md`.
18 wskazanych pól: `http://127.0.0.1:8108/symbol-review-priority/review.html`.
Strona wyłącznie do odczytu, bez zatwierdzeń i nowych etykiet.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0857 — odporność v2 i ponowna partia | gpt-6.1-sol | high | Deterministyczne augmentacje, zgodność historycznych runów, brak uczenia na przewidywaniach i rzetelna kwalifikacja. | Odrębny samodzielny przegląd, regresje i wizualny odbiór; bez delegowania |
