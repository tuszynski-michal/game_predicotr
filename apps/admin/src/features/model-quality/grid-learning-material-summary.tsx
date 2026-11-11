import type { GridCorrectionLearningPreview } from '@game-predictor/admin-api-client';

const roleNames: Record<string, string> = {
  TRAIN: 'Do nauki',
  VALIDATION: 'Kontrole wyboru modelu (A/B)',
  'VALIDATION-A': 'Dobór modelu (A)',
  'VALIDATION-B': 'Kalibracja automatu (B)',
  REGRESSION: 'Końcowy test',
  EXCLUDED: 'Wyłączone z nowego uczenia',
  UNASSIGNED: 'Bez przydziału',
  BUFFER: 'Chroniony odstęp',
  'VALIDATION-BUFFER': 'Chroniony odstęp A/B',
};

const categoryNames: Record<string, string> = {
  'missing-row': 'pominięty rząd',
  'shifted-board': 'przesunięta plansza',
  'clipped-edge': 'ucięte skrajne symbole',
  'neighbor-takeover': 'przejęcie sąsiada',
  perspective: 'perspektywa',
  'incomplete-image': 'niepełny obraz',
};

export function GridLearningTestSampleSummary({
  sample,
}: {
  sample: GridCorrectionLearningPreview['testSample'];
}) {
  if (!sample) return null;
  return (
    <section aria-label="Zwykłe i trudne przykłady do końcowego testu">
      <h4>Osobne zdjęcia sprawdzające poprawę</h4>
      <p>
        Zwykłe przypadki: {sample.ordinaryGeometryPhotos} pełnych zdjęć,{' '}
        {sample.ordinaryContentPhotos} z oznaczoną zawartością. Trudne
        przypadki: {sample.hardGeometryPhotos} pełnych zdjęć,{' '}
        {sample.hardContentPhotos} z oznaczoną zawartością.
      </p>
      <p>
        Zwykła próbka jest losowana niezależnie od trudności. Trudna próbka
        sprawdza znane problemy i nie określa ich częstości we wszystkich
        importach. Obie wybieramy przed treningiem na podstawie starego modelu i
        zatwierdzonego odniesienia.
      </p>
      {sample.state !== 'ready' ? <p>Brak danych do końcowej oceny.</p> : null}
      <p>
        Źródła w tej próbce wymagające oznaczenia zawartości:{' '}
        {sample.missingContentSources}. Zdjęcia bez rozstrzygniętej trudności:{' '}
        {sample.unknownReferencePhotos}.
      </p>
      {sample.unrepresentedCategories.length > 0 ? (
        <p>
          Nie sprawdzono jeszcze:{' '}
          {sample.unrepresentedCategories
            .map((name) => categoryNames[name] ?? name)
            .join(', ')}
          .
        </p>
      ) : null}
    </section>
  );
}

export function GridLearningMaterialSummary({
  material,
}: {
  material: GridCorrectionLearningPreview['learningMaterial'];
}) {
  if (!material) return null;
  return (
    <section aria-label="Materiał do uczenia i osobne kontrole">
      <h4>Twoje korekty i osobne testy</h4>
      <p>
        Oznaczone dane po wyłączeniach: {material.availableBoards} plansz z{' '}
        {material.availablePhotos} zdjęć. Korekta ma wagę 4, sprawdzony dobry
        przykład — 1. Do nauki trafia wyłącznie pula „Do nauki”. Kontrole służą
        do oceny, a chronione odstępy pozostają wyłączone z użycia.
      </p>
      <ul>
        {Object.entries(material.roles).map(([role, counts]) => (
          <li key={role}>
            {roleNames[role] ?? role}: {counts.correctedBoards} poprawionych,{' '}
            {counts.goodBoards} sprawdzonych dobrych, {counts.unknownBoards} z
            nierozstrzygniętym pochodzeniem; łącznie {counts.boards} plansz z{' '}
            {counts.photos} zdjęć.
          </li>
        ))}
      </ul>
      {material.photoDeficit > 0 || material.boardDeficit > 0 ? (
        <p>
          Do podstawowego podziału geometrii brakuje co najmniej{' '}
          {material.photoDeficit} zdjęć i {material.boardDeficit} plansz. Pełne
          uczenie i ocena zawartości mają dodatkowe wymagania oznaczeń i
          podziału A/B; spełnienie tych liczb nie oznacza gotowości całego
          procesu.
        </p>
      ) : null}
      {material.roleShortfalls ? (
        <div>
          <p>
            Bezpieczny podział nie jest możliwy: chronione role nie spełniają
            minimów. Podział nie zostanie poluzowany. Brakuje:
          </p>
          <ul>
            {Object.entries(material.roleShortfalls.roles)
              .filter(
                ([, counts]) =>
                  counts.photoDeficit > 0 || counts.boardDeficit > 0,
              )
              .map(([role, counts]) => (
                <li key={role}>
                  {roleNames[role] ?? role}: {counts.photoDeficit} zdjęć i{' '}
                  {counts.boardDeficit} plansz (jest {counts.photos} zdjęć i{' '}
                  {counts.boards} plansz, minimum {counts.minimumPhotos} i{' '}
                  {counts.minimumBoards}).
                </li>
              ))}
          </ul>
        </div>
      ) : null}
      {material.excludedPhotos > 0 ? (
        <details>
          <summary>
            Wyłączono {material.excludedPhotos} zdjęć i{' '}
            {material.excludedBoards} plansz z nowego użycia
          </summary>
          <p>
            Powiązane zdjęcia mają sprzeczne chronione role lub ograniczenia
            podziału. Ich historyczne użycie i Twoje zatwierdzenia są zachowane.
          </p>
          <ul>
            {material.exclusions.map((group) => (
              <li key={group.componentKey}>
                {group.photos} zdjęć, {group.boards} plansz; wcześniejsze role:{' '}
                {group.priorRoles
                  .map((role) => roleNames[role] ?? role)
                  .join(', ') || 'brak przydziału'}
                .
                <details>
                  <summary>Identyfikatory i powody</summary>
                  <p>Importy: {group.importIds.join(', ')}</p>
                  <p>Powody: {group.reasonCodes.join(', ')}</p>
                </details>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
