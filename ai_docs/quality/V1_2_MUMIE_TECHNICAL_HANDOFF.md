---
title: V1.2 Mumie technical handoff
status: active
last_updated: 2026-09-22
---

# V1.2 — odbiór techniczny na Mumii

## Rzeczywiste dane

Cztery źródła w `C:\Users\tuszy\Documents\mumie` są niezmienione względem diagnozy TASK-0612:

| Plik | SHA-256 | Stan V1.2 |
| --- | --- | --- |
| `seq_1-9.jpg` | `68f8ba589e9bbca55eedc2431f4fbefd6fe95bb3e192729199e25ee08283e9f9` | `review_required` |
| `seq_10-18.jpg` | `80759c0f43456ace9a52555d4a64b2b70ce9589f32d7a0425e9ab73f87d18467` | `review_required` |
| `seq_19-27.jpg` | `f2f37f6e9836e0021b6592b66dc96006fd562949ea1251657f88b523887bb4fe` | `review_required` |
| `seq_28-36.jpg` | `e15eca4b489d39da5967408f19d0116acdf09866cdc384eac05f6a638008fde1` | `review_required` |

Źródłem stanu jest checksummowany manifest V1.2
`artifacts/data/page-geometry-manifests/0646d4bb6b6a2f4bc5ff5c14884d0dab0557e6d047ef7ced2c81c731073bffd2.json`.
Jego SHA-256 odpowiada nazwie. Manifest należy do gry
`2a46d3a6-bc56-4a13-8f98-dd51c88df0b2` i stagingu
`c7822d39-e311-409c-a7e1-090894f5d0cb`; obejmuje 24 źródła, z których
**0 jest zarejestrowanych, a 24 wymagają korekty**. Każde z czterech
wskazanych zdjęć ma powód `IMAGE_CONTRAST_FRAME_GRID_PROFILE_REQUIRED`.
Przypięty profil ma `sampleSourceCount=0` i `sampleCount=0`.

Z tego manifestu nie powstaje nakładka ramka/siatka ani import. Nie wolno
traktować pojedynczych quadów V1.1 jako potwierdzonych par V1.2. Wynik
dokładności na tych czterech zdjęciach jest **nieoceniony**; brak automatu nie
jest zaliczonym testem skuteczności.

## Co jest sprawdzone technicznie

- T03: API blokuje brak preflightu i nierozstrzygnięty manifest; zgodny
  preflight dopuszcza V1.2, a ponowienie startu zwraca ten sam job.
- Worker przetworzył testowo pełną stronę 9 plansz oraz końcową stronę
  5 plansz; każda dała 15 pól z `symbolGridQuads`, nie z `boardFrameQuads`.
- Skoncentrowane testy API (4), workera (9), Ruff, format, typecheck Admina
  i klienta, OpenAPI oraz test starego przepływu przeszły przed commitem
  `v0.10.359`. Testy są techniczne i nie zastępują oceny pikseli Mumii.
- Nie uruchomiono importu użytkownika i nie zapisano wycinków z Mumii.

## Następny krok operatora

W Adminie dla Mumii wybierz jawnie V1.2 i otwórz korektę jednego pełnego,
czytelnego zdjęcia, najlepiej `seq_1-9.jpg`. Wyznacz 36 narożników siatek
symboli i cztery odstępy ramki dla każdej planszy, sprawdź nakładkę obu
warstw i zapisz. Uruchom **nowy** preflight; stary manifest nie zmieni się.
Sprawdź wynik wszystkich 24 źródeł, nie tylko czterech zdjęć użytych w tym
raporcie. Każde nadal nierozstrzygnięte źródło przeznaczone do importu popraw
ręcznie i ponów preflight. Dopiero przy zerowej liczbie nierozstrzygniętych
importowanych źródeł kliknij **Import**. Wtedy porównaj rzeczywiste wycinki
plansz i symboli w aplikacji; to jest właściwy odbiór dokładności.
