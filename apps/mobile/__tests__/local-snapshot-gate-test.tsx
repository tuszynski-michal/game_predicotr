import type { ReactNode } from 'react';
import { act, create, type ReactTestRenderer } from 'react-test-renderer';

import { LocalSnapshotGate } from '@/features/local-snapshot/local-snapshot-gate';

type MockSQLiteProviderProps = {
  assetSource?: { assetId: number };
  children: ReactNode;
  databaseName: string;
  onError?: (error: Error) => void;
  onInit?: (database: object) => Promise<void>;
};

jest.mock('expo-sqlite', () => {
  const React = jest.requireActual<typeof import('react')>('react');
  const database = {};
  const DatabaseContext = React.createContext(database);

  function Provider({
    children,
    onError,
    onInit,
  }: MockSQLiteProviderProps): ReactNode {
    const [ready, setReady] = React.useState(false);

    React.useEffect(() => {
      Promise.resolve(onInit?.(database))
        .then(() => setReady(true))
        .catch((error: Error) => onError?.(error));
    }, [onError, onInit]);

    return ready
      ? React.createElement(
          DatabaseContext.Provider,
          { value: database },
          children,
        )
      : null;
  }

  return {
    SQLiteProvider: React.memo(
      Provider,
      (previous: MockSQLiteProviderProps, next: MockSQLiteProviderProps) =>
        previous.databaseName === next.databaseName &&
        previous.onError === next.onError &&
        previous.onInit === next.onInit,
    ),
    useSQLiteContext: () => React.useContext(DatabaseContext),
  };
});

jest.mock('@/data/bundled-snapshot', () => {
  class LocalDataError extends Error {
    readonly code = 'local_data_error';
  }

  return {
    asLocalDataError: (error: Error) => error,
    buildLocalDatabaseName: () => 'snapshot-test.db',
    LOCAL_DATA_ERROR_CODE: 'local_data_error',
    LocalDataError,
    readSnapshotDiagnostics: jest.fn().mockResolvedValue({
      algorithmVersion: 'payout-v2',
      databaseName: 'snapshot-test.db',
      datasetVersion: 2,
      fixtureVersion: 'm1-fixture-v2',
      gameCount: 1,
      layoutCount: 1,
      logicalContentSha256: 'b'.repeat(64),
      releaseVersion: 'm1-fixture.2',
      rulesVersion: 2,
      schemaVersion: 2,
      snapshotFileSha256: 'a'.repeat(64),
    }),
    snapshotAssetId: 1,
    snapshotManifest: {},
  };
});

jest.mock('@/data/local-layout-repository', () => ({
  LocalLayoutRepository: class {
    listGames() {
      return Promise.resolve([
        {
          code: 'game-1',
          columns: 1,
          databaseId: 1,
          datasetVersion: 2,
          id: 'game-1',
          layoutCount: 1,
          name: 'Game 1',
          rows: 1,
          rulesVersion: 2,
          signatureCellWidth: 2,
          spinCost: 10,
          symbols: [
            {
              code: 'S1',
              displayOrder: 0,
              isWildcard: false,
              mobileCode: 1,
              name: 'Symbol 1',
            },
          ],
        },
      ]);
    }
  },
}));

jest.mock('@/features/board/game-workspace-screen', () => {
  const React = jest.requireActual<typeof import('react')>('react');
  const { Text } =
    jest.requireActual<typeof import('react-native')>('react-native');

  return {
    GameWorkspaceScreen: () =>
      React.createElement(
        Text,
        { testID: 'workspace-ready' },
        'workspace-ready',
      ),
  };
});

describe('LocalSnapshotGate', () => {
  test('leaves the diagnostic loader after the bundled database is verified', async () => {
    let renderer!: ReactTestRenderer;

    await act(async () => {
      renderer = create(<LocalSnapshotGate />);
      await new Promise((resolve) => setTimeout(resolve, 0));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(
      renderer.root.findByProps({ testID: 'workspace-ready' }),
    ).toBeTruthy();
    expect(JSON.stringify(renderer.toJSON())).not.toContain(
      'Weryfikacja danych offline',
    );
  });
});
