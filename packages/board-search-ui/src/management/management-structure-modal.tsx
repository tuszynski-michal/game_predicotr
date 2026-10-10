'use client';

import type {
  ManagementMachineResponse,
  ManagementPointResponse,
  ManagementSnapshotResponse,
} from '@game-predictor/admin-api-client';
import type {
  Dispatch,
  FormEventHandler,
  RefObject,
  SetStateAction,
} from 'react';

export type ManagementStructureEditor =
  | { kind: 'point'; point?: ManagementPointResponse }
  | {
      kind: 'machine';
      point: ManagementPointResponse;
      machine?: ManagementMachineResponse;
    };

interface Props {
  editor: ManagementStructureEditor;
  activeGames: ManagementSnapshotResponse['activeGames'];
  name: string;
  city: string;
  street: string;
  gameIds: readonly string[];
  disabled: boolean;
  saving: boolean;
  error: string;
  retryAvailable: boolean;
  retryDisabled: boolean;
  onRetry: () => void;
  conflict?: boolean;
  nameInput: RefObject<HTMLInputElement | null>;
  setName: (value: string) => void;
  setCity: (value: string) => void;
  setStreet: (value: string) => void;
  setGameIds: Dispatch<SetStateAction<string[]>>;
  onSave: FormEventHandler<HTMLFormElement>;
  onClose: () => void;
}

export function ManagementStructureModal({
  editor,
  activeGames,
  name,
  city,
  street,
  gameIds,
  disabled,
  saving,
  error,
  retryAvailable,
  retryDisabled,
  onRetry,
  conflict = false,
  nameInput,
  setName,
  setCity,
  setStreet,
  setGameIds,
  onSave,
  onClose,
}: Props) {
  const toggleGame = (id: string, checked: boolean) =>
    setGameIds((current) =>
      checked ? [...current, id] : current.filter((item) => item !== id),
    );
  return (
    <form
      onSubmit={onSave}
      onKeyDown={(event) => {
        if (event.key === 'Escape') {
          event.preventDefault();
          onClose();
        }
      }}
      className="management-modal"
      role="dialog"
      aria-modal="true"
      aria-label={editor.kind === 'point' ? 'Edycja punktu' : 'Edycja maszyny'}
    >
      <h3>{editor.kind === 'point' ? 'Punkt' : 'Maszyna'}</h3>
      {error ? <p role="alert">{error}</p> : null}
      {conflict ? (
        <p role="alert">
          Ten punkt lub maszyna zmieniły się w innym oknie. Twój formularz
          pozostał zachowany. Zamknij go i otwórz ponownie, aby użyć nowej
          rewizji.
        </p>
      ) : null}
      <label>
        Nazwa
        <input
          ref={nameInput}
          required
          maxLength={200}
          value={name}
          disabled={saving || retryAvailable}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      {editor.kind === 'point' ? (
        <>
          <label>
            Miasto
            <input
              required
              maxLength={200}
              value={city}
              disabled={saving || retryAvailable}
              onChange={(event) => setCity(event.target.value)}
            />
          </label>
          <label>
            Ulica
            <input
              required
              maxLength={200}
              value={street}
              disabled={saving || retryAvailable}
              onChange={(event) => setStreet(event.target.value)}
            />
          </label>
        </>
      ) : (
        <fieldset>
          <legend>Przypisane gry</legend>
          {activeGames.map((game) => (
            <label className="management-game" key={game.id}>
              <input
                type="checkbox"
                disabled={saving || retryAvailable}
                checked={gameIds.includes(game.id)}
                onChange={(event) => toggleGame(game.id, event.target.checked)}
              />
              {game.name}
              {editor.machine?.assignments.some(
                (row) => row.gameId === game.id && !row.attached,
              )
                ? ' · odłączona'
                : ''}
            </label>
          ))}
          {editor.machine?.assignments
            .filter(
              (row) =>
                row.gameStatus !== 'active' &&
                !activeGames.some((game) => game.id === row.gameId),
            )
            .map((row) => (
              <label className="management-game" key={row.gameId}>
                <input
                  type="checkbox"
                  disabled={saving || retryAvailable}
                  checked={gameIds.includes(row.gameId)}
                  onChange={(event) =>
                    toggleGame(row.gameId, event.target.checked)
                  }
                />
                {row.gameName} · {row.attached ? 'nieaktywna' : 'odłączona'}
              </label>
            ))}
          <p>
            Odpięcie gry usuwa jej zapisy w tej maszynie po osobnym
            potwierdzeniu.
          </p>
          {editor.machine?.assignments.some((row) => !row.attached) ? (
            <p>
              Odłączone gry pozostają zaznaczone, aby chronić ich historię.
              Zapisanie formularza może ponownie przypisać aktywną odłączoną
              grę. Nieaktywną odłączoną grę trzeba jawnie odpiąć po podglądzie;
              odpięcie usuwa historię tej maszyny i gry.
            </p>
          ) : null}
        </fieldset>
      )}
      <div className="management-actions">
        <button
          type="submit"
          disabled={
            disabled ||
            !name.trim() ||
            (editor.kind === 'point' && (!city.trim() || !street.trim()))
          }
        >
          Zapisz
        </button>
        {retryAvailable ? (
          <button type="button" disabled={retryDisabled} onClick={onRetry}>
            Ponów ten sam zapis
          </button>
        ) : null}
        <button type="button" disabled={saving} onClick={onClose}>
          Anuluj
        </button>
      </div>
    </form>
  );
}
