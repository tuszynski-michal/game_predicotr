import type {
  JobResponse,
  SourceRecordingGroupResponse,
} from '@game-predictor/admin-api-client';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** One explicit page of a complete recording; never truncate operator intent. */
export function recordingSourceIds(value: string): string[] {
  const values = value
    .trim()
    .split(/[\s,;]+/)
    .filter(Boolean);
  if (values.length === 0 || values.length > 200) {
    throw new Error('Podaj od 1 do 200 identyfikatorów zdjęć na stronę.');
  }
  if (values.some((id) => !uuid.test(id))) {
    throw new Error('Każdy identyfikator zdjęcia musi być poprawnym UUID.');
  }
  const normalized = values.map((id) => id.toLowerCase());
  if (new Set(normalized).size !== normalized.length) {
    throw new Error('Strona zawiera powtórzone identyfikatory zdjęć.');
  }
  return normalized;
}
export function recordingImportLabel(job: JobResponse): string {
  const payload = job.inputPayload;
  const name =
    'sourceDisplayName' in payload &&
    typeof payload.sourceDisplayName === 'string' &&
    payload.sourceDisplayName.trim()
      ? payload.sourceDisplayName.trim()
      : 'Import zdjęć bez nazwy';
  const date = new Date(job.createdAt);
  const created = Number.isNaN(date.valueOf())
    ? 'data nieustalona'
    : date.toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'short' });
  const count = job.progress.imageImport?.pipelineTotal;
  return `${name} · ${created} · ${count === undefined ? 'liczba zdjęć nieustalona' : `${count} zdjęć`}`;
}

export function recordingGroupLabel(
  group: SourceRecordingGroupResponse,
  jobs: readonly JobResponse[],
): string {
  const job =
    'importJobId' in group
      ? jobs.find((item) => item.id === group.importJobId)
      : undefined;
  if (job) return recordingImportLabel(job);
  const date =
    'createdAt' in group && typeof group.createdAt === 'string'
      ? new Date(group.createdAt)
      : null;
  return date && !Number.isNaN(date.valueOf())
    ? `Nagranie z ${date.toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'short' })}`
    : 'Nagranie o nieustalonej dacie';
}

export function recordingReasonLabel(reason: string): string {
  return (
    (
      {
        RECORDING_MEMBERSHIP_INCOMPLETE:
          'Nie zarejestrowano jeszcze wszystkich zdjęć nagrania.',
        RECORDING_DECLARATION_REQUIRED:
          'Potwierdź niezależność całego nagrania.',
        RECORDING_ROLE_REQUIRED: 'Nagranie nie ma przypisanej roli.',
        RECORDING_ROLE_CONFLICT: 'Role powiązanych nagrań są sprzeczne.',
        RECORDING_PROTECTED: 'Nagranie podlega ochronie danych kontrolnych.',
        RECORDING_RESOLUTION_REQUIRED: 'Zapisz rozstrzygnięcie pochodzenia.',
        RECORDING_SOURCE_IDENTITY_UNRESOLVED:
          'Nie potwierdzono tożsamości zdjęć.',
        RECORDING_CLOSURE_UNRESOLVED:
          'Nie ustalono wszystkich powiązań nagrania.',
        RECORDING_SOURCE_IDENTITY_DRIFT:
          'Zdjęcia zmieniły się od przygotowania nagrania.',
      } as Record<string, string>
    )[reason] ?? 'Pochodzenie wymaga wyjaśnienia przed dalszą kwalifikacją.'
  );
}
