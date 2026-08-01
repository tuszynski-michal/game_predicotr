'use client';

import type { GameResponse } from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useRef, useState } from 'react';

import {
  DEFAULT_ADMIN_NAVIGATION,
  type AdminNavigationState,
  type AdminWorkspace,
  type GameSection,
  parseAdminNavigation,
  serializeAdminNavigation,
} from '@/features/catalog/admin-navigation-state';
import { CleanupControl } from '@/features/cleanup/cleanup-control';
import { GameCatalog } from '@/features/games/game-catalog';
import { ImageFolderImportPanel } from '@/features/imports/image-folder-import-panel';
import { JobMonitor } from '@/features/jobs/job-monitor';
import { ReleasePanel } from '@/features/releases/release-panel';
import { ReviewerAccessLauncher } from '@/features/reviewer-access/reviewer-access-launcher';
import { RulesVersionCatalog } from '@/features/rules/rules-version-catalog';
import { SymbolCatalog } from '@/features/symbols/symbol-catalog';

interface CatalogWorkspaceProps {
  readonly apiBaseUrl: string;
}

const WORKSPACE_OPTIONS: readonly {
  readonly id: AdminWorkspace;
  readonly label: string;
  readonly description: string;
  readonly index: string;
}[] = [
  {
    id: 'games',
    label: 'Zarządzanie grami',
    description: 'Gry, import, symbole, reguły i zatwierdzanie.',
    index: '01',
  },
  {
    id: 'releases',
    label: 'Wersje Android',
    description: 'Snapshoty i paczki instalacyjne APK.',
    index: '02',
  },
  {
    id: 'jobs',
    label: 'Joby',
    description: 'Postęp oraz błędy procesów w tle.',
    index: '03',
  },
];

const GAME_SECTION_OPTIONS: readonly {
  readonly id: GameSection;
  readonly title: string;
  readonly description: string;
}[] = [
  {
    id: 'imports',
    title: 'Import layoutów',
    description: 'Wybór folderu, postęp importu i kompletność layoutów.',
  },
  {
    id: 'symbols',
    title: 'Symbole',
    description: 'Katalog symboli używany przez reguły i mobile.',
  },
  {
    id: 'rules',
    title: 'Reguły',
    description: 'Wymiary planszy, paylines, payouty i publikacja.',
  },
  {
    id: 'reviews',
    title: 'Zatwierdzanie plansz',
    description: 'Dostęp do osobnej aplikacji Reviewer.',
  },
];

export function CatalogWorkspace({ apiBaseUrl }: CatalogWorkspaceProps) {
  const [navigation, setNavigation] = useState<AdminNavigationState>(
    DEFAULT_ADMIN_NAVIGATION,
  );
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [gamesRevision, setGamesRevision] = useState(0);
  const navigationRef = useRef(navigation);
  const sectionHeaderRefs = useRef<
    Partial<Record<GameSection, HTMLButtonElement | null>>
  >({});

  useEffect(() => {
    navigationRef.current = navigation;
  }, [navigation]);

  useEffect(() => {
    const restoreFromUrl = () => {
      setNavigation(parseAdminNavigation(window.location.search));
    };
    restoreFromUrl();
    window.addEventListener('popstate', restoreFromUrl);
    return () => window.removeEventListener('popstate', restoreFromUrl);
  }, []);

  const commitNavigation = useCallback(
    (next: AdminNavigationState, mode: 'push' | 'replace' = 'push') => {
      setNavigation(next);
      const search = serializeAdminNavigation(window.location.search, next);
      const url = `${window.location.pathname}${search}${window.location.hash}`;
      if (mode === 'replace') {
        window.history.replaceState(null, '', url);
      } else {
        window.history.pushState(null, '', url);
      }
    },
    [],
  );

  const handleGamesLoaded = useCallback(
    (loadedGames: readonly GameResponse[]) => {
      setGames(loadedGames);
      const currentNavigation = navigationRef.current;
      if (
        currentNavigation.gameId !== null &&
        !loadedGames.some((game) => game.id === currentNavigation.gameId)
      ) {
        commitNavigation(
          { ...currentNavigation, gameId: null, section: null },
          'replace',
        );
      }
    },
    [commitNavigation],
  );

  const activeGame =
    games.find(
      (game) => game.id === navigation.gameId && game.status !== 'archived',
    ) ?? null;

  function selectWorkspace(workspace: AdminWorkspace) {
    if (workspace !== navigation.workspace) {
      commitNavigation({ ...navigation, workspace });
    }
  }

  function selectGame(gameId: string | null) {
    if (gameId !== navigation.gameId) {
      commitNavigation({
        ...navigation,
        gameId,
        section: gameId === null ? null : navigation.section,
      });
    }
  }

  function toggleSection(section: GameSection) {
    const nextSection = navigation.section === section ? null : section;
    commitNavigation({ ...navigation, section: nextSection });
    if (nextSection !== null) {
      window.requestAnimationFrame(() => {
        sectionHeaderRefs.current[nextSection]?.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest',
        });
      });
    }
  }

  function openSection(section: GameSection) {
    commitNavigation({ ...navigation, section });
    window.requestAnimationFrame(() => {
      sectionHeaderRefs.current[section]?.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
      });
    });
  }

  return (
    <div className="adminWorkspace">
      <header className="workspaceHeader">
        <div>
          <p className="eyebrow">Game Predictor · Admin 0.2</p>
          <h1>Wybierz obszar pracy</h1>
          <p className="lead">
            Każdy obszar ma własny, krótki przepływ. Wybrany kontekst wróci po
            odświeżeniu strony.
          </p>
        </div>
      </header>

      <nav className="workspaceNavigation" aria-label="Obszary panelu Admin">
        {WORKSPACE_OPTIONS.map((option) => (
          <button
            aria-current={
              navigation.workspace === option.id ? 'page' : undefined
            }
            className={
              navigation.workspace === option.id
                ? 'workspaceTile workspaceTileActive'
                : 'workspaceTile'
            }
            key={option.id}
            onClick={() => selectWorkspace(option.id)}
            type="button"
          >
            <span className="workspaceTileIndex">{option.index}</span>
            <strong>{option.label}</strong>
            <span>{option.description}</span>
          </button>
        ))}
      </nav>

      <div className="workspaceBody">
        {navigation.workspace === 'games' ? (
          <div className="gameManagementWorkspace">
            <GameCatalog
              apiBaseUrl={apiBaseUrl}
              onGamesChanged={() =>
                setGamesRevision((revision) => revision + 1)
              }
              onGamesLoaded={handleGamesLoaded}
              onSelectedGameIdChange={selectGame}
              selectedGameId={navigation.gameId}
            />

            {activeGame !== null ? (
              <section
                aria-label={`Konfiguracja gry ${activeGame.name}`}
                className="gameAccordion"
              >
                <header className="activeGameContext">
                  <div>
                    <p className="eyebrow">Aktywny kontekst</p>
                    <h2>{activeGame.name}</h2>
                  </div>
                  <code>{activeGame.code}</code>
                </header>

                {GAME_SECTION_OPTIONS.map((section) => {
                  const expanded = navigation.section === section.id;
                  return (
                    <article
                      className="gameAccordionItem"
                      key={`${section.id}-${gamesRevision}`}
                    >
                      <h2 className="gameAccordionHeading">
                        <button
                          aria-controls={`game-section-${section.id}`}
                          aria-expanded={expanded}
                          className="gameAccordionTrigger"
                          onClick={() => toggleSection(section.id)}
                          ref={(node) => {
                            sectionHeaderRefs.current[section.id] = node;
                          }}
                          type="button"
                        >
                          <span>
                            <strong>{section.title}</strong>
                            <span>{section.description}</span>
                          </span>
                          <span className="sectionReadiness">Dostępna</span>
                          <span className="accordionChevron" aria-hidden="true">
                            {expanded ? '−' : '+'}
                          </span>
                        </button>
                      </h2>
                      <div
                        className="gameAccordionBody"
                        hidden={!expanded}
                        id={`game-section-${section.id}`}
                      >
                        {section.id === 'imports' ? (
                          <ImageFolderImportPanel
                            apiBaseUrl={apiBaseUrl}
                            gameId={activeGame.id}
                            key={activeGame.id}
                          />
                        ) : null}
                        {section.id === 'symbols' ? (
                          <SymbolCatalog
                            apiBaseUrl={apiBaseUrl}
                            gameId={activeGame.id}
                            gamesRevision={gamesRevision}
                          />
                        ) : null}
                        {section.id === 'rules' ? (
                          <RulesVersionCatalog
                            apiBaseUrl={apiBaseUrl}
                            gameId={activeGame.id}
                            gamesRevision={gamesRevision}
                          />
                        ) : null}
                        {section.id === 'reviews' ? (
                          <ReviewerAccessLauncher
                            apiBaseUrl={apiBaseUrl}
                            gameId={activeGame.id}
                            onOpenImports={() => openSection('imports')}
                          />
                        ) : null}
                      </div>
                    </article>
                  );
                })}

                <CleanupControl
                  apiBaseUrl={apiBaseUrl}
                  onCompleted={() => {
                    setGamesRevision((revision) => revision + 1);
                    commitNavigation({ ...navigation, section: null });
                  }}
                  target={{ id: activeGame.id, kind: 'game-layout-data' }}
                  targetLabel={`${activeGame.name} · ${activeGame.code}`}
                />
              </section>
            ) : null}
          </div>
        ) : null}

        {navigation.workspace === 'releases' ? (
          <ReleasePanel
            apiBaseUrl={apiBaseUrl}
            onOpenJobs={() => selectWorkspace('jobs')}
          />
        ) : null}
        {navigation.workspace === 'jobs' ? (
          <JobMonitor apiBaseUrl={apiBaseUrl} />
        ) : null}
      </div>
    </div>
  );
}
