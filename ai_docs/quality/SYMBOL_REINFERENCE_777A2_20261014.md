---
title: Wynik ponownego rozpoznawania symboli 777 a2 poniżej 80%
status: active
last_updated: 2026-10-14
---

# TASK-0991 — Wynik rozpoznawania symboli 777 a2

Przebieg zakończono, a wynik potwierdzono z nowego procesu przez odczyt bazy
2026-10-14 około 08:51 UTC (09:51 Africa/Lagos). Obsłużono cały zamrożony
zakres: **35 122 komórki na 24 309 planszach** gry
`6e20a58f-88f3-4a9c-87b5-ae3297ed4fbf` (`777a2`, „777 a2”).

## Zakres i model

Operator zlecił wszystkie osiem klas, wyłącznie komórki `pending` z pewnością
ściśle mniejszą niż `0.80`. Ręcznie zatwierdzone komórki nie kwalifikowały się
do zakresu. Nie dodano filtra do API ani UI i nie uruchomiono treningu ani
aktywacji. Użyto aktywowanej wcześniej iteracji
`747c21d5-8cbb-4ba5-a53c-6a763f79a2b4`, ONNX SHA-256
`588a2f4cb0771dd4972d28c59bfb1726f8dfc60956d86c0647a6bd70d1f683c3`.

| Klasa w chwili zamrożenia | Komórki poniżej 80% |
|---|---:|
| ARBUZ | 7135 |
| CYTRYNA | 654 |
| GWIAZDA | 1360 |
| POMARANCZ | 7500 |
| SIEDEM | 2549 |
| SLIWKA | 6992 |
| WINOGRON | 6014 |
| WISNIA | 2918 |
| **Razem** | **35 122** |

## Wynik i niezależny odczyt po zakończeniu procesu

| Wynik | Liczba |
|---|---:|
| Plansze z kompletnymi, unikalnymi receiptami | 24 309 / 24 309 |
| Plansze z nową inferencją | 24 054 |
| Plansze już przeliczone tym samym modelem dla tych samych cropów | 255 |
| Komórki przeliczone w tym przebiegu | 34 726 |
| Komórki z wcześniej istniejącym wynikiem tego samego modelu | 396 |
| Komórki zamrożonego zakresu obecne po zakończeniu | 35 122 |
| Pewność co najmniej 80% po przeliczeniu | 31 290 |
| Pewność nadal poniżej 80% | 3832 |
| Brakujące receipty lub pominięte plansze | 0 |

Wszystkie 35 122 komórki nadal miały stan `pending`: inferencja nie zatwierdza
etykiet w imieniu człowieka. Weryfikator sprawdził istnienie każdej rewizji
wskazanej przez receipt, jej właściciela, checksumę modelu i pochodzenie
nowych rewizji z manifestu tej operacji. Suma 34 726 + 396 pokrywa cały zakres.

Przed zapisem każdej nowej rewizji ponownie sprawdzano stan, próg pewności,
identyfikator komórki oraz tożsamość cropa i geometrii. Transakcja sprawdzała
zachowanie pól predykcji, cropa i decyzji człowieka poza zakresem. Odwołania
systemowe do rewizji planszy mogły się zmienić podczas publikowania mieszanej
rewizji; zachowane predykcje mają odnotowane pochodzenie wcześniejszej rewizji.
Żadna asercja ochronna nie przerwała przebiegu.

## Trwałość, naprawa i kontrole

Pierwotny job `2f807266-ae5f-410d-afae-f33c01580773` miał
`JOB_PROGRESS_REGRESSION` przy 6824/341461 po czterech próbach. Handler
ignorował checkpoint i zaczynał liczniki od zera. Naprawa
**v1.7.351 / `6e84a1b1d4a9546e1ff9545b039512f6691ec15d`** zapisuje stabilny
klucz wznowienia i zachowuje liczniki; starsze checkpointy odtwarza
idempotentnie. Ochrona monotoniczności w domenie pozostaje włączona.

Testy workera i domeny jobów: **43 PASS**, ruff format/lint i targeted mypy
PASS. Wyniki wykorzystano bez powtarzania kontroli niezmienionego kodu.
Regresje obejmują wznowienie, utraconą odpowiedź, zmianę zbioru oczekujących,
stare checkpointy i niepoprawny kursor. Nie wykonano niezależnego audytu
Claude: CLI było niedostępne; brief zachowano, bez deklarowania PASS audytu.

Operacyjny runner zachował zsynchronizowane receipty po chwilowej blokadzie
pliku statusu Windows, a później po zaplanowanym godzinnym limicie. Kolejne
procesy kontynuowały ten sam manifest bez równoległych kopii. Końcowe procesy
42980/36160 były już nieobecne przy weryfikacji. Monitor został wyłączony po
potwierdzeniu wyniku. API, Admin, Reviewer i istniejący worker nie były
restartowane. Nie wykonywano migracji, cleanupu, push ani nowego merge.

## Dowody

Pełne lokalne dowody: `artifacts/symbol-reinference-20261014/`.
Checksumą kanonicznej treści manifestu bez własnego pola checksumy jest
`dbec7abccf16f9be88854622c5dae804a47170ec069583f9b3a2118951f1f0d6`.

| Plik | SHA-256 bajtów pliku |
|---|---|
| `scope.json` | `08725779fbc112fba871c50416d3546168779867202b98bda98c7278fc0305ab` |
| `receipts.jsonl` | `feb6f8aa94958abdbb307cfabcebafe9d4ff564fde005141f1c545fa8a4ede2e` |
| `verification.json` | `b266bfc0e67b58d0b9c12f4df41a781b9ec3fe5704588b5541768d431998d1fa` |

## Kryteria i pozostawione czynności

Siedem kryteriów taska spełniono: cztery regresje wznowienia mają testy,
kontrole zmienionego kodu przeszły, manifest i ochrona decyzji zostały
zweryfikowane, a wynik potwierdzono z nowego procesu i zapisano w tym raporcie.
Nie było osobnego zaakceptowanego planu wykonawczego; zakres wynikał ze zleceń
operatora i taska. Zmiany schematu, API i UI nie wystąpiły.

3832 komórki pozostają poniżej 80%. Nie uruchomiono kolejnego treningu ani
dodatkowej oceny accuracy. Istniejący poll worker wymaga przeładowania przez
operatora przed przyszłymi zwykłymi jobami; instrukcja pozostaje w tasku.
Naprawa kodu jest już na gałęzi integracyjnej po wcześniejszej zgodzie.
Nowa dokumentacja zamknięcia oczekuje końcowej akceptacji i zgody na scalenie.
