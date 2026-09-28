'use client';
import { useRef, useState } from 'react';
import { useAnnotations } from './annotation-context';
import { useToast } from '../../../../packages/ui/src/toasts';
import { gameDisplayName } from '../lib/game-display-name';
import {
  backupAnnotations,
  annotationTimings,
  writeFamily,
  type Source,
  type FamilyRequest,
} from '../../../../packages/vision-lab-api-client/src/index';

export function FamilyEditor({
  sources,
  selected,
  onSelected,
}: {
  sources: Source[];
  selected: Source[];
  onSelected: (sources: Source[]) => void;
}) {
  const { accept, refresh } = useAnnotations();
  const notify = useToast();
  const writing = useRef(false);
  const preparing = useRef(false);
  const [actor, setActor] = useState('');
  const [family, setFamily] = useState('');
  const [evidence, setEvidence] = useState('');
  const [verified, setVerified] = useState(false);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState('');
  const [pending, setPending] = useState<FamilyRequest | null>(null);
  async function submit(body: FamilyRequest) {
    if (writing.current) return;
    writing.current = true;
    setBusy(true);
    setPending(body);
    try {
      accept(await writeFamily(body));
      setPending(null);
      notify({
        kind: 'success',
        message:
          'Zapisano jawne powiązanie źródeł. Wspólny SHA i relacje są łączone przechodnio.',
      });
    } catch {
      notify({
        kind: 'error',
        message:
          'Zapis niepotwierdzony. Ponów identyczne żądanie lub odśwież stan po konflikcie.',
      });
    } finally {
      setBusy(false);
      writing.current = false;
    }
  }
  return (
    <section>
      <h2>Powiązane zdjęcia i rodziny</h2>
      <p>
        Zaznacz powiązane ujęcia, pochodne i powtórzenia układu. Wybór zachowuje
        się między stronami i grami. Nazwa pliku nie dowodzi rodziny, a SHA
        wykrywa wyłącznie identyczne pliki. Nie potwierdzaj niezależności bez
        wiedzy o pochodzeniu.
      </p>
      <fieldset disabled={busy || pending !== null}>
        <div className="family-options">
          {sources.map((source) => (
            <label key={source.id}>
              <input
                type="checkbox"
                disabled={busy}
                checked={selected.some((s) => s.id === source.id)}
                onChange={(e) =>
                  onSelected(
                    e.target.checked
                      ? [...selected, source]
                      : selected.filter((s) => s.id !== source.id),
                  )
                }
              />
              {gameDisplayName(source.game_id, source.game_name)}: {source.filename}
            </label>
          ))}
        </div>
        <p>
          Wybrano {selected.length}:{' '}
          {selected.map((s) => s.filename).join(', ')}
        </p>
        <button disabled={busy} onClick={() => onSelected([])}>
          Wyczyść wybór
        </button>
        <label>
          Osoba weryfikująca{' '}
          <input
            value={actor}
            onChange={(e) => setActor(e.target.value)}
            disabled={busy}
          />
        </label>
        <label>
          Wspólna rodzina / grupa powiązań{' '}
          <input
            value={family}
            onChange={(e) => setFamily(e.target.value)}
            disabled={busy}
          />
        </label>
        <label>
          Dowód i opis powiązań{' '}
          <textarea
            value={evidence}
            onChange={(e) => setEvidence(e.target.value)}
            disabled={busy}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={verified}
            onChange={(e) => setVerified(e.target.checked)}
            disabled={busy}
          />{' '}
          Znam pochodzenie wszystkich wybranych źródeł i zweryfikowałem ich
          powiązania z pozostałymi rodzinami.
        </label>
        <p>
          Bez potwierdzenia grupa pozostanie nierozstrzygnięta. Sam zapis grupy
          nie kwalifikuje geometrii do treningu. Wybrane geometrie historycznego
          777 dopuszcza osobna decyzja D-453; pilot D-456 dzieli całe gry bez
          potwierdzania niezależności rodzin. Zmiana unieważni bieżący podział.
        </p>
        <button
          disabled={
            busy ||
            !selected.length ||
            !actor.trim() ||
            !family.trim() ||
            evidence.trim().length < 5
          }
          onClick={async () => {
            if (preparing.current) return;
            preparing.current = true;
            setBusy(true);
            try {
              const state = await refresh();
              await submit({
                request_id: crypto.randomUUID(),
                expected_revision: state.revision,
                actor,
                decision: {
                  source_ids: selected.map((s) => s.id),
                  related_source_ids: [],
                  family_id: family,
                  evidence,
                  provenance: verified ? 'verified' : 'unresolved',
                  declaration: '',
                  checksum_reviewed: false,
                  similarity_reviewed: false,
                },
              });
            } catch {
              notify({
                kind: 'error',
                message:
                  'Zapis niepotwierdzony lub konflikt rewizji. Sprawdź stan przed ponowieniem.',
              });
            } finally {
              setBusy(false);
              preparing.current = false;
            }
          }}
        >
          Zapisz decyzję o grupie
        </button>
      </fieldset>
      {pending && (
        <>
          <button disabled={busy} onClick={() => submit(pending)}>
            Ponów identyczną decyzję o grupie
          </button>
          <button
            disabled={busy}
            onClick={async () => {
              try {
                const state = await refresh();
                setPending(null);
                notify({
                  kind: 'info',
                  message: `Odczytano rewizję ${state.revision}. Sprawdź zapisaną decyzję przed zmianą.`,
                });
              } catch {
                notify({ kind: 'error', message: 'Odczyt nie powiódł się.' });
              }
            }}
          >
            Odśwież po konflikcie
          </button>
        </>
      )}
      <button
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            const result = await backupAnnotations();
            notify({
              kind: 'success',
              message: `Backup rewizji ${result.revision}: ${result.backup_id}. Odtworzenie jest dostępne wyłącznie do nowego katalogu przez narzędzie operatorskie.`,
            });
          } catch {
            notify({ kind: 'error', message: 'Backup nie powiódł się.' });
          } finally {
            setBusy(false);
          }
        }}
      >
        Utwórz backup anotacji
      </button>
      <button
        disabled={busy}
        onClick={async () => {
          try {
            const rows = await annotationTimings();
            setReport(
              rows
                .map(
                  (row) =>
                    `${row.game_id}: ${row.measured_sources}/10 zmierzonych, ${(row.active_ms / 60000).toFixed(1)} min; pozostały pilot: ${row.estimated_remaining_ms === null ? 'brak pomiaru' : (row.estimated_remaining_ms / 60000).toFixed(1) + ' min'}`,
                )
                .join(' | '),
            );
          } catch {
            notify({ kind: 'error', message: 'Nie można odczytać pomiaru.' });
          }
        }}
      >
        Pokaż pomiar pierwszych 10 zdjęć na grę
      </button>
      {report && <p aria-label="Raport pomiaru anotacji">{report}</p>}
    </section>
  );
}
