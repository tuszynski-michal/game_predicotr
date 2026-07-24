import { SQLiteProvider, type SQLiteDatabase } from 'expo-sqlite';
import { useCallback, useState } from 'react';

import {
  asLocalDataError,
  buildLocalDatabaseName,
  readSnapshotDiagnostics,
  snapshotAssetId,
  snapshotManifest,
  type LocalDataError,
  type SnapshotDiagnostics,
} from '@/data/bundled-snapshot';
import {
  LocalLayoutRepository,
  type LocalGameConfig,
} from '@/data/local-layout-repository';
import { GameWorkspaceScreen } from '@/features/board/game-workspace-screen';

import { SnapshotDiagnosticScreen } from './snapshot-diagnostic-screen';

export function LocalSnapshotGate() {
  const [diagnostics, setDiagnostics] = useState<SnapshotDiagnostics | null>(
    null,
  );
  const [games, setGames] = useState<readonly LocalGameConfig[] | null>(null);
  const [error, setError] = useState<LocalDataError | null>(null);

  const initialize = useCallback(async (database: SQLiteDatabase) => {
    const repository = new LocalLayoutRepository(database);
    const [verifiedDiagnostics, gameCatalog] = await Promise.all([
      readSnapshotDiagnostics(database),
      repository.listGames(),
    ]);
    setDiagnostics(verifiedDiagnostics);
    setGames(gameCatalog);
  }, []);

  const handleError = useCallback((providerError: Error) => {
    setError(asLocalDataError(providerError));
  }, []);

  if (error !== null) {
    return <SnapshotDiagnosticScreen error={error} diagnostics={null} />;
  }

  return (
    <SQLiteProvider
      assetSource={{ assetId: snapshotAssetId }}
      databaseName={buildLocalDatabaseName(snapshotManifest)}
      onError={handleError}
      onInit={initialize}
    >
      {diagnostics === null || games === null ? (
        <SnapshotDiagnosticScreen diagnostics={null} error={null} />
      ) : (
        <GameWorkspaceScreen diagnostics={diagnostics} games={games} />
      )}
    </SQLiteProvider>
  );
}
