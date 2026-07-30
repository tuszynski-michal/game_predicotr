'use client';

import { useState } from 'react';

import { GameCatalog } from '@/features/games/game-catalog';
import { DatasetCatalog } from '@/features/datasets/dataset-catalog';
import { JobMonitor } from '@/features/jobs/job-monitor';
import { ManualImportPanel } from '@/features/imports/manual-import-panel';
import { ReviewerAccessLauncher } from '@/features/reviewer-access/reviewer-access-launcher';
import { ReleasePanel } from '@/features/releases/release-panel';
import { ReviewWorkspace } from '@/features/reviews/review-workspace';
import { RulesVersionCatalog } from '@/features/rules/rules-version-catalog';
import { SymbolCatalog } from '@/features/symbols/symbol-catalog';

interface CatalogWorkspaceProps {
  readonly apiBaseUrl: string;
}

export function CatalogWorkspace({ apiBaseUrl }: CatalogWorkspaceProps) {
  const [gamesRevision, setGamesRevision] = useState(0);

  return (
    <>
      <GameCatalog
        apiBaseUrl={apiBaseUrl}
        onGamesChanged={() => setGamesRevision((revision) => revision + 1)}
      />
      <SymbolCatalog apiBaseUrl={apiBaseUrl} gamesRevision={gamesRevision} />
      <RulesVersionCatalog
        apiBaseUrl={apiBaseUrl}
        gamesRevision={gamesRevision}
      />
      <DatasetCatalog apiBaseUrl={apiBaseUrl} gamesRevision={gamesRevision} />
      <ManualImportPanel apiBaseUrl={apiBaseUrl} />
      <JobMonitor apiBaseUrl={apiBaseUrl} />
      <ReviewWorkspace apiBaseUrl={apiBaseUrl} />
      <ReviewerAccessLauncher apiBaseUrl={apiBaseUrl} />
      <ReleasePanel apiBaseUrl={apiBaseUrl} />
    </>
  );
}
