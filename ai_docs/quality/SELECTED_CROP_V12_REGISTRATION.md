# Odbiór czteropunktowej rejestracji cropa v12

## Zakres

Odbiór jest ograniczonym testem tylko do odczytu na 30 ujawnionych wcześniej,
source-disjoint referencjach z fixture'ów v11 `fourth`, `fifth` i `sixth`.
Oryginalne JPEG-i odczytano z lokalnego katalogu źródłowego po kontroli SHA-256.
Nie zapisano ani nie przeliczono katalogów `cut` użytkownika.

Polityka:
`selected-image-board-band-v12-four-point-anchor-registration`.

## Wynik

- 30 zdjęć;
- 29 wyników automatycznych, w tym 20 przez rejestrację kotwicy;
- 1 obowiązkowa korekta ręczna;
- 29/29 automatów zachowuje wszystkie oznaczone plansze i numery;
- 0 automatycznych odcięć;
- 16/29 automatów mieści się w ścisłym przedziale położenia obu linii.

Bezpieczna automatyzacja wynosi 96,7% całej próby i spełnia minimalny cel 95%
dla ochrony zawartości. Nie potwierdza celu 99% ani jednakowo ciasnego cropa.
Trzynaście bezpiecznych wyników zachowuje więcej tła albo rozmieszcza jedną z
linii poza wąskim przedziałem referencyjnym.

## Decyzja

Mechanizm czteropunktowy jest dostępny do jawnego testu, ale flaga wydania
pozostaje wyłączona. Nie jest to niezależny odbiór nowej szaty graficznej ani
zgoda na masowe przeliczenie istniejących danych. Kolejna bramka powinna objąć
nowe, zamrożone przed uruchomieniem przykłady i ocenić osobno bezpieczeństwo
oraz nadmiar tła.
