---
title: T03 — addytywny zbiór i zachowanie zapisów po restarcie
status: active
last_updated: 2026-09-27
---

# Wynik operacji danych laboratorium

## Zakres i odbiór

Wykonawca `gpt-6-sol` / `medium`, niezależny audyt `gpt-6-astra` / `medium`.
Plan i helper sprawdzono przed zapisem. Import zakończył się przed restartem
komputera; po restarcie sprawdzono wynik bez ponownego importowania zdjęć.
Następnie wykonano addytywny rebase do nowego katalogu, bez nadpisania starego.
Końcowy audyt operacji: **PASS, bez P0–P2**.

Nowy zestaw zachowuje 993 wcześniejsze wystąpienia i dodaje 473 nowe:
1466 identyfikatorów, 1440 unikalnych SHA, te same 6 gier. Zachowano wszystkie
stare wpisy manifestu, role i źródła. Sześć nowych zdjęć Mumii ma SHA identyczne
ze starymi nieanotowanymi źródłami; nie usunięto żadnego wystąpienia.

Zachowano rewizję 259, 180 pełnych anotacji, 63 aktualnie zaakceptowane zdjęcia,
259 zdarzeń historii, 259 receipts i 196 timingów. Cały payload różni się
wyłącznie `state.snapshot_id`. Wszystkie 63 źródła występujące w pełnej historii
mają identyczne obiekty Source. Żadne z 473 nowych źródeł nie dostało akceptacji.

Przy odbiorze: zero rodzin i kwalifikacji, brak splitu. Późniejsza kwalifikacja
geometrii 777 jest osobną operacją, nie częścią opisanego rebase.

## Lokalizacje i integralność

Wspólny katalog: `C:/Users/tuszy/Documents/game_predictor_vision_data`.

Stary identyfikator snapshotu:
`82c3c29dd35e17a1df74da249fd8687f86db6be0b781e0bb1a64f1dbbc1962c9`.
Nowy identyfikator snapshotu:
`0cdc0770b3535596fdbfa0a8f403cbf32d6a8b134fb52047f5a1f7bda33772c2`.
Snapshoty znajdują się w `snapshots/<ID>`, odpowiadające zapisy
w `annotations/<ID>/state.json`.

| Obiekt | SHA-256 |
| --- | --- |
| Stary state.json i backup | `22f452d0e976a9997909ece2cf9bede0073f1241574f5880fa7b3ebdbb0e0586` |
| Nowy state.json po rebase, przed dalszymi decyzjami | `ef5903646401fc95225542126e84a85e8d0991bebcbb177efbdb916606de0f01` |
| Nowy Catalog / state.snapshot_id | `e8c0cfc703923b1937221d4a86c096d871034707c51bb9873e75fb0051c2d544` |
| Payload wyjściowy rebase | `8377e75c24281af07136724f5db9ec70d312bd87a7d90f6893a29484431ef62f` |
| rebase-report.json | `fade4cab1358e618e6dd3ee8ae7f5015f7a94b9da2487af135edb737e59e77ca` |
| provenance.json partii | `7c028155b4bd0a47e5e03b02ebec117af7a27b4148460a14094b9099b6bc32be` |

Snapshot ID, digest katalogu i suma pliku stanu to różne identyfikatory.
Backup: `recovery-backups/t03-before-addition-revision259/state.json`.
Staging zachowany: `staging/t03-addition-20260927-0cdc0770`.
Raport wszystkich wejść i ich mapowania:
`import-reports/t03-addition-20260927-0cdc0770/provenance.json`.
Obok są kopie `_selection_report.txt` i JSON selekcji Treasure. Raport jawnie
nie deklaruje weryfikacji rodzin ani zgodności starych cropów z nowymi pikselami.
Istniejący mechanizm opublikował `rebase-report.json` razem z nowym stanem.

## Weryfikacja trwałości

- Przed apply: świeży preview `ready`, brak listenera API 8102 i brak starego
  procesu helpera. Niezmieniony SHA wejścia i zgodny backup.
- `apply-rebase`: exit 0, `applied`; kolejny nowy proces preview: exit 0,
  `already_applied`. Nie wykonywano drugiego apply.
- Niezależny audyt w kolejnym procesie potwierdził oba Catalog, checksummed
  payloady, pełną równość, aktualność 63 akceptacji, brak nowych zgód oraz retry.
  SHA starego i nowego stanu przed i po odczycie pozostały identyczne.
- Każdy helper miał limit 60 s i ukryte okno; nie wystąpił timeout ani osierocony
  proces. Pierwszy start w sandboxie dał exit 101 przed uruchomieniem docelowego
  Pythona; dozwolone ponowienie poza sandboxem nie wymagało zmiany ACL.
- Restart OS potwierdził trwałość wcześniejszego importu. Rebase sprawdzono
  w nowych procesach, bez kolejnego restartu systemu, bez uruchamiania UI/API.

Dokładne logi i raport wykonawcy: `artifacts/vision-lab/` w repozytorium,
`t03-additive-operation-outcome.md`, `additive-prepare-import-run1.*`,
`additive-apply-rebase-resume1.*`, `additive-preview-postapply1.*`.
Nie zmieniano kodu produkcyjnego, geometrii, rodzin ani zgód; testów aplikacji
nie uruchamiano specjalnie dla tej operacji. Bez cleanupu, treningu i aktywacji.

## Pozostałe bramki danych

Nadal trzeba przypisać konkretne zdjęcia do oryginalnych nagrań i ich wycinków.
Odległe numery ani różne foldery nie wystarczają do niezależnego testu.
Powiązanie Treasure 23590–23913 z dawnym `tresure23600` pozostaje konserwatywnie
wspólne zgodnie z odpowiedzią operatora; nie ponawiać tego pytania.
Raport selekcji sugeruje też wspólne zakresy Mumii 76555–103221, 1–23175
oraz 379549–391419. Nie nadano im automatycznie `verified`.

Tabela konkretnych braków dla sześciu gier jest w raporcie wykonawcy. Najbardziej
użyteczne wejście operatora to ścieżka do oryginalnych katalogów nagrań lub
eksportów selekcji; nie jest potrzebne ponowne rysowanie dotychczasowych siatek.
T03 pozostaje blocked; brak freeze i treningu T04/T05. Nowe zdjęcia nie zwiększają
automatycznie liczby zatwierdzonych przykładów ani niezależnych rodzin.
