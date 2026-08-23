---
title: V19 symbol model candidate
status: rejected
last_updated: 2026-08-23
---

# Kandydat modelu symboli na cropach v19

## Wynik

TASK-0270 wytrenował od początku `spatial-symbol-cnn-v1` na niezmiennej
kohorcie TASK-0269. Kandydat został **kontrolowanie odrzucony** i nie został
aktywowany.

- kohorta: 321 plansz, 4815 cropów, 41 rodzin źródeł i 6 stagingów,
- split: 38 rodzin train oraz po jednej validation, test i regression,
- najlepsza epoka: 24 z 40,
- checkpoint:
  `da69f8c28ca3781279379f235dddef9fde9ff54400583eda9b2c4a965241f9e7`,
- manifest bazowej bramki:
  `ced0140fe8641ed3cb8059b46ee3bdb1200b875a986de0b5affd02f78190c804`,
- decyzja v19:
  `4e6ace22cc4d90ee230cc66ae4a3a306afa54c6b19f9e8d96544dbebee421578`.

## Porównanie z aktywnym modelem

Porównanie wykonano na identycznym połączonym zbiorze test i regression.

| Miara | Aktywny model | Kandydat | Różnica |
| --- | ---: | ---: | ---: |
| Accuracy symboli | 98,4314% | 99,2157% | +0,7843 pp |
| Accuracy całych plansz | 88,2353% | 94,1176% | +5,8824 pp |

Kandydat spełnił alternatywną bramkę poprawy accuracy całych plansz o co
najmniej 2 pp. Recall żadnej klasy nie spadł o więcej niż 1 pp. PyTorch i ONNX
zachowały identyczne top-1 dla próbki parity; maksymalny błąd bezwzględny
logitów wyniósł `0,000002861`. Temperatura `0,60057958` mieści się w bezpiecznym
zakresie `0,5–20`.

## Powód odrzucenia

Deterministyczny audyt 100 plansz znalazł jeden błąd o confidence co najmniej
0,99:

- sekwencja 35, komórka 13, staging `test`,
- oczekiwane `lemon`, przewidziane `orange`,
- confidence `0,99999698`.

Zgodnie z zaakceptowaną bramką nawet jeden taki błąd blokuje promocję.
Odrzucenie nie jest błędem technicznym treningu. Aktywny fingerprint pozostał
równy
`19e15e92591a3e1692a329e7c2fc9f4f3fe0f102bf623bebc20184615e48db64`.

## Odtworzenie i kontrola

```powershell
.venv\Scripts\python.exe scripts\evaluate_symbol_model_candidate.py --check
```

Ponowny trening nie jest wymagany do sprawdzenia decyzji. Polecenie kontrolne
weryfikuje checksumę raportu, kontrakt bramki oraz brak zmiany aktywnego modelu.
