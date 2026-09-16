# Odbiór `range-only OCR v2`

Data: 2026-08-31

## Zakres

Odbiór był read-only i używał pierwszych 10, a następnie pierwszych 100
numerycznie uporządkowanych JPEG-ów `seq_*` z katalogu operatora
`C:\Users\user\Documents\777\1-19809`. Nazwa była wyłącznie oracle'em
raportu; recognizer nie otrzymywał oczekiwanego zakresu. Pliki źródłowe nie
zostały zmienione.

Adapter: `semi-automatic-range-only-ocr-v2`
Runtime fingerprint:
`2075f0da6494ce1e55b2b2a8e0cebcef7b285f42e59e9629b1d4859fa69335f6`

## Wyniki bramek

| Próba | Exact | Luki | Fałszywe automatyczne | Overlap | Czas | Średnia |
|---|---:|---:|---:|---:|---:|---:|
| 10 | 7 | 3 | 0 | 0 | 13,462 s | 1,346 s/JPEG |
| 100 | 68 | 32 | 0 | 0 | 131,883 s | 1,319 s/JPEG |

Dla próby 100 mediana wyniosła `1,421 s/JPEG`, peak RSS `541 708 288 B`,
a stosunek czasu 100/10 wyniósł około `9,80`. Potwierdza to liniowy koszt
O(N) w granicach tej kontrolowanej próby.

Manifest źródeł próby 10:
`299f79e584d301c0d0923281433e5fbb36e0cf6c935fa8dc2806a06dce3e8e27`.

Manifest źródeł próby 100:
`763fd15f89dab01802005ce92da6e9eedbbb6dbb1f90e93bd49692fd66b682a2`.

## Wynik próby 100

Dokładnie rozpoznano 68 zakresów:

`10–18`, `19–27`, `28–36`, `37–45`, `46–54`, `55–63`, `82–90`,
`91–99`, `100–108`, `109–117`, `118–126`, `127–135`, `136–144`,
`145–153`, `154–162`, `163–171`, `172–180`, `190–198`, `217–225`,
`235–243`, `244–252`, `253–261`, `262–270`, `280–288`, `289–297`,
`298–306`, `307–315`, `316–324`, `325–333`, `352–360`, `361–369`,
`370–378`, `397–405`, `415–423`, `424–432`, `442–450`, `460–468`,
`469–477`, `478–486`, `496–504`, `514–522`, `523–531`, `532–540`,
`541–549`, `559–567`, `595–603`, `604–612`, `613–621`, `622–630`,
`640–648`, `649–657`, `658–666`, `676–684`, `685–693`, `694–702`,
`703–711`, `712–720`, `730–738`, `748–756`, `757–765`, `766–774`,
`775–783`, `793–801`, `820–828`, `847–855`, `865–873`, `874–882`,
`883–891`.

Jako luki pozostało:

- 20 przypadków `range_unreadable`;
- 6 przypadków `range_ambiguous`;
- 6 przypadków `not_expected_range`.

Dwanaście surowych hipotez odrzucono przed automatycznym wyborem:
`73–81→76–84`, `181–189→182–190`, `199–207→200–208`,
`334–342→337–345`, `343–351→346–354`, `379–387→382–390`,
`505–513→508–516`, `577–585→580–588`, `631–639→634–642`,
`811–819→811–819`, `838–846→841–849`, `892–900→895–903`.
Przypadek `811–819` miał zgodny surowy zakres, lecz za słaby dowód pozycyjny,
więc zgodnie z polityką również pozostał luką.

## Koszt OCR i izolacja pipeline'u

- źródła: `100`;
- cropy etykiet przekazane do OCR: `3228`;
- batche OCR, każdy maksymalnie po 9 cropów: `538`;
- zakończenie po poziomie 24: `31` zdjęć;
- zakończenie po poziomie 36: `30` zdjęć;
- brak mocnego dowodu po poziomie 36: `39` zdjęć;
- wywołania geometrii: `0`;
- wywołania croppera komórek: `0`;
- wywołania klasyfikatora symboli: `0`.

## Decyzja rolloutowa

Obie bramki odbioru przeszły: recall próby 100 wyniósł `68%`, bez żadnego
błędnego automatycznego przypisania. Implementacja v2 jest gotowa do osobnej
decyzji o rolloutcie, ale ten odbiór nie włącza funkcji. Domyślna flaga
`GAME_PREDICTOR_ENABLE_SEMI_AUTOMATIC_IMAGE_SELECTION` pozostaje `false`.
