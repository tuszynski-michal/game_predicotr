# TASK-0492 — Nie maskować niepotwierdzonej granicy cięcia

## Status

done

## Relevant docs

- ai_docs/requirements/MANUAL_IMAGE_SELECTION.md
- ai_docs/architecture/MANUAL_IMAGE_SELECTION.md
- ai_docs/process/PLAN_STANDARD.md

## Zakres

Pierwsza naprawa zgłoszenia 200–400 błędnych cięć: wspólna ocena dowodu
dla obowiązkowej korekty, filtrów i etykiet. Nie zmienia współrzędnych ani
fingerprintów historycznych detektorów. Nie aktywuje nieodebranych v11/v12.

## Fakty i decyzje

Zapisane 200 poprawek katalogu 70363–93861 zachowuje oryginalne propozycje:
186 high_confidence, 13 conservative, 1 safe_wide. V10 podnosi klasę po
znalezieniu samego górnego rzędu, nawet gdy fallback dolnej granicy pozostał.
Naprawa przeglądu odczytuje dowód, nie ufa samej klasie. Ręczne decyzje są
chronione. Dalsze usprawnienie lokalizacji obu granic wymaga osobnego odbioru;
ten task nie deklaruje rozwiązania jakości detektora.

## Implementacja i DoD

- crop-session.ts: wspólna funkcja powodu obowiązkowej korekty; fallback
  mimo high_confidence i jawny konflikt rejestracji wymagają korekty.
- storage i workspace: ta sama reguła synchronizacji, filtra i etykiety.
- Restart oraz odznaczenie wszystkich nie ukrywają niepotwierdzonego wyniku;
  ręczne zapisanie/zaakceptowanie nadal rozwiązuje obowiązek.
- Testy core, kontrakt Admina, typecheck, lint, format i build.
- Bez zapisu w katalogach użytkownika i bez zmiany importu/geometrii/OCR.

## Outcome

Wdrożono regułę dowodu wspólną dla storage, etykiet, filtra i restartu.
87 testów core, 17 kontraktów Admina, typecheck core/Admin, lint Admina,
format zmienionego kodu i produkcyjny build Admina OK.
Regresja statyczna wymaga teraz wspólnej funkcji dowodu zamiast poprzedniego
warunku safe_wide; nie osłabiono testu, zmieniono wadliwy kontrakt.

Na 200 ręcznych korektach katalogu 70363–93861: stara reguła obejmowała 1,
nowa 182. Na 105 korektach 93853–117828: stara 40, nowa 103. Razem 285/305,
20 nadal bez ostrzeżenia. Nie badano false positives ani całej populacji.
Manifesty zachowały pierwotne autoCropProposal i ręczny result.crop, więc
nie trzeba prosić operatora o ponowne wskazanie już poprawionych plików.

Odczytowo porównano sześć oryginałów z ręcznymi liniami: v11
zwrócił trzy complete_layout i trzy odmowy. Nie oceniano jeszcze wizualnie
bezpieczeństwa tych nowych propozycji; ciaśniejszy pas niż ręczny nie jest
sam w sobie dowodem odcięcia planszy.

Próbki: seq_89803-89811, seq_78526-78534, seq_80758-80766,
seq_81244-81252, seq_81955-81963, seq_82450-82458 (katalog 70363–93861).
Nie aktywowano eksperymentu ani nie zmieniono JPEG-ów. Dalszy cel użytkownika
— poprawniejsze automatyczne granice — pozostaje nieukończony. Następny etap
wymaga oceny oryginałów i osobnego zbioru odbiorczego, nie obniżenia bramki.
