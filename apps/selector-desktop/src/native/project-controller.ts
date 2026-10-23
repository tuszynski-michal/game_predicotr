import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { lstat } from 'node:fs/promises';
import { assertNoLinks } from './path-security.ts';
import {
  SecureFiles,
  canonicalDirectoryLocation,
  isMissing,
} from '../filesystem/secure-files.ts';
import { ProjectStore } from '../project/project-store.ts';
import { GameCatalog } from './game-catalog.ts';
import { RecentProjects } from '../project/recent-projects.ts';
import type { ProjectCommand } from '../project/types.ts';
import { SourceRegistry } from './source-registry.ts';
import {
  PROJECT_STATE_NAME,
  PROJECT_BACKUP_NAME,
  PROJECT_JOURNAL_NAME,
} from '../project/state-codec.ts';
import { OUTPUT_MANIFEST_NAME } from '../manifest/operator-local.ts';
import {
  inspectLegacy,
  sameLegacyProof,
  type LegacyProof,
} from '../legacy-adoption/legacy-preview.ts';
import {
  DEFAULT_VIEW,
  validateId,
  validateView,
  ViewPreferencesStore,
} from './view-preferences.ts';
import {
  SelectorError,
  MAX_SEQUENCE_NUMBER,
  validateGameName,
  validateGameUpdate,
  outputDirectoryName,
  type CreateProjectRequest,
  type SourceIndex,
  type DesktopWorkspace,
  type ViewPreferences,
  type LegacyPreviewSummary,
  type NewProjectDraft,
  type StartSelectionResult,
} from '../contracts.ts';
export interface NativeDialogs {
  directory(title: string, defaultPath?: string): Promise<string | null>;
  confirm(message: string, confirmLabel?: string): Promise<boolean>;
  openFolder(directory: string): Promise<void>;
}
function object(value: unknown, keys: string[]): Record<string, unknown> {
  if (
    !value ||
    typeof value !== 'object' ||
    Array.isArray(value) ||
    Object.keys(value).some((key) => !keys.includes(key))
  )
    throw new SelectorError(
      'INVALID_ARGUMENT',
      'Nieprawidłowe argumenty polecenia.',
    );
  return value as Record<string, unknown>;
}
export function validateCreate(value: unknown): CreateProjectRequest {
  const v = object(value, [
    'firstLayout',
    'direction',
    'sequenceUpperBound',
    'customLocations',
    'localStorageConfirmed',
    'sourceToken',
    'gameName',
    'gameUpdate',
  ]);
  if (
    !Number.isSafeInteger(v.firstLayout) ||
    Number(v.firstLayout) < 1 ||
    Number(v.firstLayout) > MAX_SEQUENCE_NUMBER ||
    !['ascending', 'descending'].includes(String(v.direction)) ||
    (v.sequenceUpperBound !== null &&
      (!Number.isSafeInteger(v.sequenceUpperBound) ||
        Number(v.sequenceUpperBound) < Number(v.firstLayout) ||
        Number(v.sequenceUpperBound) > MAX_SEQUENCE_NUMBER)) ||
    typeof v.customLocations !== 'boolean' ||
    v.localStorageConfirmed !== true
  )
    throw new SelectorError(
      'INVALID_ARGUMENT',
      'Podaj numerację od 1 do 500000.',
    );
  if (v.sourceToken !== undefined) {
    validateId(v.sourceToken);
    if (v.customLocations)
      throw new SelectorError(
        'INVALID_ARGUMENT',
        'Katalogi powstają obok zdjęć.',
      );
    validateGameName(v.gameName);
    outputDirectoryName(v as unknown as CreateProjectRequest);
  }
  const gameUpdate = validateGameUpdate(v.gameUpdate);
  return {
    ...v,
    gameUpdate,
    sequenceUpperBound: v.sequenceUpperBound ?? MAX_SEQUENCE_NUMBER,
    ...(v.gameName === undefined
      ? {}
      : { gameName: validateGameName(v.gameName) }),
  } as unknown as CreateProjectRequest;
}
export class ProjectController {
  private store: ProjectStore | null = null;
  private source: SourceIndex | null = null;
  private closeIssue: { code: string; message: string } | null = null;
  private view: ViewPreferences = { ...DEFAULT_VIEW };
  private queue: Promise<unknown> = Promise.resolve();
  readonly registry: SourceRegistry;
  private dialogs: NativeDialogs;
  private recentCache: RecentProjects;
  private gameCatalog: GameCatalog;
  private views: ViewPreferencesStore;
  private legacyProof: {
    token: string;
    proof: LegacyProof;
    result: DesktopWorkspace | null;
    automatic?: boolean;
    gameName?: string;
    gameUpdate?: string;
  } | null = null;
  private draft: {
    value: NewProjectDraft;
    request?: string;
    result?: DesktopWorkspace;
  } | null = null;
  constructor(
    userData: string,
    registry: SourceRegistry,
    dialogs: NativeDialogs,
  ) {
    this.registry = registry;
    this.dialogs = dialogs;
    this.recentCache = new RecentProjects(userData);
    this.gameCatalog = new GameCatalog(userData);
    this.views = new ViewPreferencesStore(path.join(userData, 'views'));
  }
  private serial<T>(work: () => Promise<T>): Promise<T> {
    const result = this.queue.then(work);
    this.queue = result.catch(() => {});
    return result;
  }
  private active(): ProjectStore {
    if (!this.store) throw new SelectorError('NO_PROJECT', 'Otwórz projekt.');
    return this.store;
  }
  games(): Promise<string[]> {
    return this.serial(async () =>
      this.gameCatalog.addMany(
        (await this.recentCache.list()).flatMap((r) =>
          r.gameName ? [r.gameName] : [],
        ),
      ),
    );
  }
  addGame(name: unknown): Promise<string[]> {
    return this.serial(() => this.gameCatalog.add(validateGameName(name)));
  }
  async recent() {
    return (await this.recentCache.list()).map((r) => ({
      projectId: r.projectId,
      name: r.gameName
        ? `${r.gameName}${r.gameUpdate ? ` ${r.gameUpdate}` : ''} — ${r.sourceDirectoryName}`
        : r.sourceDirectoryName,
      openedAt: r.openedAt,
    }));
  }
  private async refreshSource(): Promise<void> {
    const state = this.active().sourceSnapshot();
    this.source = null;
    if (this.active().getIssue()?.code === 'SOURCE_MISSING') return;
    try {
      const scan = this.active().getVerifiedSourceScan();
      if (!scan)
        throw new SelectorError(
          'SOURCE_IDENTITY_CONFLICT',
          'Brakuje zweryfikowanego indeksu źródła. Wznów projekt.',
        );
      const source = await this.registry.registerVerifiedScan(scan);
      const actual = source.images.map((i) => [
        i.relativePath,
        i.size,
        Math.trunc(i.lastModified),
      ]);
      const expected = state.inventory.map((i) => [
        i.relativePath,
        i.sizeBytes,
        i.lastModifiedMs,
      ]);
      if (JSON.stringify(actual) !== JSON.stringify(expected))
        throw new SelectorError(
          'SOURCE_CHANGED',
          'Źródło różni się od inwentarza projektu.',
        );
      this.source = source;
    } catch (error) {
      if (!this.active().getIssue()) throw error;
    }
  }
  snapshot(): DesktopWorkspace | null {
    if (!this.store) return null;
    const s = this.store.workspaceSnapshot();
    const byPath = new Map(
      this.source?.images.map((i) => [i.relativePath, i.id]),
    );
    return {
      projectId: s.projectId,
      ...(s.gameName ? { gameName: s.gameName } : {}),
      ...(s.gameUpdate ? { gameUpdate: s.gameUpdate } : {}),
      revision: s.revision,
      source: this.source,
      sourceName: s.sourceDirectoryName,
      projectName: path.basename(this.store.getProjectRoot()),
      outputName: path.basename(s.outputRoot),
      currentImageId: byPath.get(s.currentRelativePath ?? '') ?? null,
      firstLayout: s.firstLayout,
      direction: s.direction,
      sequenceUpperBound: s.sequenceUpperBound,
      nextRangeStart: s.nextRangeStart,
      selectionComplete: s.selectionComplete,
      acceptedCount: s.decisions.filter((d) => d.action === 'accepted').length,
      skippedCount: s.decisions.filter((d) => d.action === 'skipped').length,
      acceptedImageIds: s.decisions
        .filter((d) => d.action === 'accepted')
        .map((d) => byPath.get(d.imagePath ?? ''))
        .filter((id): id is string => Boolean(id)),
      decisionCount: s.decisions.length,
      issue: this.store.getIssue(),
      view: { ...this.view },
    };
  }
  private async replaceStore(store: ProjectStore): Promise<DesktopWorkspace> {
    this.store = store;
    this.view = await this.views.load(store.workspaceSnapshot().projectId);
    await this.refreshSource();
    await this.rememberActive();
    return this.snapshot()!;
  }
  private async rememberActive(): Promise<void> {
    const store = this.active();
    const s = store.workspaceSnapshot();
    await this.recentCache.remember({
      projectId: s.projectId,
      projectRoot: store.getProjectRoot(),
      sourceDirectoryName: s.sourceDirectoryName,
      sourceRoot: s.sourceRoot,
      ...(s.gameName ? { gameName: s.gameName } : {}),
      ...(s.gameUpdate ? { gameUpdate: s.gameUpdate } : {}),
      openedAt: new Date().toISOString(),
    });
  }
  private async closeInternal() {
    await this.views.flush();
    await this.store?.close();
    this.closeIssue = this.store?.getCloseIssue() ?? null;
    this.store = null;
    this.source = null;
  }
  getCloseIssue(): { code: string; message: string } | null {
    return this.closeIssue ? { ...this.closeIssue } : null;
  }
  close(): Promise<void> {
    return this.serial(() => this.closeInternal());
  }
  legacyPreview(): Promise<LegacyPreviewSummary | null> {
    return this.serial(async () => {
      this.legacyProof = null;
      const source = await this.dialogs.directory(
        'Wybierz źródło starej sesji Reviewera',
      );
      if (!source) return null;
      const output = await this.dialogs.directory(
        'Wybierz stary wynik sesji Reviewera',
      );
      if (!output) return null;
      return this.inspectLegacySelection(source, output);
    });
  }
  private async inspectLegacySelection(
    source: string,
    output: string,
    automatic = false,
  ): Promise<LegacyPreviewSummary> {
    const proof = await inspectLegacy(source, output);
    const token = randomUUID();
    this.legacyProof = {
      token,
      proof,
      result: null,
      automatic,
      gameName: automatic
        ? this.store?.workspaceSnapshot().gameName
        : undefined,
      gameUpdate: automatic
        ? this.store?.workspaceSnapshot().gameUpdate
        : undefined,
    };
    const s = proof.seed;
    return {
      ...(automatic
        ? {
            projectName: `${s.sourceDirectoryName} selekcja`,
            outputName: `${s.sourceDirectoryName} wybrane przejete`,
          }
        : {}),
      previewToken: token,
      schemaVersion: proof.schemaVersion,
      sourceName: s.sourceDirectoryName,
      oldOutputName: path.basename(proof.oldOutputRoot),
      fileCount: s.inventory.length,
      firstLayout: s.firstLayout,
      direction: s.direction,
      sequenceUpperBound: s.sequenceUpperBound,
      nextRangeStart: s.nextRangeStart,
      selectionComplete: s.selectionComplete,
      currentPhoto:
        s.inventory.findIndex((i) => i.relativePath === s.currentRelativePath) +
        1,
      acceptedCount: s.decisions.filter((d) => d.action === 'accepted').length,
      skippedCount: s.decisions.filter((d) => d.action === 'skipped').length,
      legacyCursor: proof.legacyCursor,
    };
  }
  legacyAdopt(token: unknown): Promise<DesktopWorkspace | null> {
    return this.serial(async () => {
      validateId(token);
      const preview = this.legacyProof;
      if (!preview || preview.token !== token)
        throw new SelectorError(
          'LEGACY_PREVIEW_EXPIRED',
          'Wykonaj ponownie podgląd starej sesji.',
        );
      if (preview.result) {
        if (
          this.store?.workspaceSnapshot().projectId !== preview.result.projectId
        )
          throw new SelectorError(
            'LEGACY_PREVIEW_EXPIRED',
            'Projekt został zmieniony. Otwórz zapisany projekt.',
          );
        return this.snapshot();
      }
      const projectRoot = preview.automatic
        ? `${preview.proof.sourceRoot} selekcja`
        : await this.dialogs.directory('Wybierz nowy pusty katalog projektu');
      if (!projectRoot) return null;
      const outputRoot = preview.automatic
        ? `${preview.proof.sourceRoot} wybrane przejete`
        : await this.dialogs.directory('Wybierz nowy pusty katalog wynikowy');
      if (!outputRoot) return null;
      if (
        !preview.automatic &&
        !(await this.dialogs.confirm(
          `Przejęcie sesji: ${preview.proof.seed.sourceDirectoryName}\nNowy projekt: ${projectRoot}\nNowy wynik: ${outputRoot}\n\nProjekt i nowy wynik są na lokalnym dysku poza synchronizacją. Stary wynik i źródło pozostaną bez zmian. Utworzyć nowy projekt?`,
        ))
      )
        return null;
      const proof = await inspectLegacy(
        preview.proof.sourceRoot,
        preview.proof.oldOutputRoot,
      );
      if (!sameLegacyProof(preview.proof, proof))
        throw new SelectorError(
          'LEGACY_CHANGED',
          'Sesja zmieniła się od podglądu. Wykonaj podgląd ponownie.',
        );
      const store = await ProjectStore.createFromSelection(
        {
          sourceRoot: proof.sourceRoot,
          projectRoot,
          outputRoot,
          ...(preview.gameName ? { gameName: preview.gameName } : {}),
          ...(preview.gameUpdate ? { gameUpdate: preview.gameUpdate } : {}),
          firstLayout: proof.seed.firstLayout,
          direction: proof.seed.direction,
          sequenceUpperBound: proof.seed.sequenceUpperBound,
          localStorageConfirmed: true,
        },
        {},
        proof.seed,
        proof.oldOutputRoot,
      );
      try {
        await this.closeInternal();
        const result = await this.replaceStore(store);
        preview.result = result;
        return result;
      } catch (error) {
        await store.close();
        throw error;
      }
    });
  }
  begin(): Promise<StartSelectionResult | null> {
    return this.serial(async () => {
      const chosen = await this.dialogs.directory('Wybierz folder zdjęć');
      if (!chosen) return null;
      // No image is read here. Check the selected path and ancestors; create/open
      // perform the full source content scan once before any selection access.
      await assertNoLinks(chosen);
      if (!(await lstat(chosen)).isDirectory())
        throw new SelectorError('NOT_DIRECTORY', 'Wybierz folder zdjęć.');
      const sourceRoot = await canonicalDirectoryLocation(chosen);
      const selectedFiles = new SecureFiles(sourceRoot);
      const selectedNames = await selectedFiles.names();
      if (
        [PROJECT_STATE_NAME, PROJECT_BACKUP_NAME, PROJECT_JOURNAL_NAME].some(
          (name) => selectedNames.includes(name),
        )
      ) {
        await this.closeInternal();
        const workspace = await this.replaceStore(
          await ProjectStore.open(sourceRoot),
        );
        this.draft = null;
        return { kind: 'existing', workspace };
      }
      if (selectedNames.includes(OUTPUT_MANIFEST_NAME)) {
        // Metadata is only a hint. inspectLegacy proves the source identity and
        // every selected JPEG before presenting an adoption preview.
        let raw: Record<string, unknown>;
        try {
          raw = JSON.parse(
            (await selectedFiles.read(OUTPUT_MANIFEST_NAME))!.toString(),
          ) as Record<string, unknown>;
          if (!raw || typeof raw !== 'object' || Array.isArray(raw))
            throw new Error('manifest');
        } catch {
          throw new SelectorError(
            'LEGACY_INVALID',
            'Manifest sesji jest uszkodzony.',
          );
        }
        const name = raw.sourceDirectoryName;
        let oldSource: string | null = null;
        if (
          typeof name === 'string' &&
          name !== '.' &&
          name !== '..' &&
          !/[\\/:]/.test(name)
        ) {
          const sibling = path.join(path.dirname(sourceRoot), name);
          try {
            if ((await lstat(sibling)).isDirectory()) oldSource = sibling;
          } catch (error) {
            if (!isMissing(error)) throw error;
          }
        }
        oldSource ??= await this.dialogs.directory(
          'Wybierz folder źródłowych zdjęć tej sesji',
        );
        if (!oldSource) return null;
        return this.beginSource(oldSource, sourceRoot);
      }
      return this.beginSource(sourceRoot);
    });
  }
  private async beginSource(
    sourceRoot: string,
    legacyOutput?: string,
  ): Promise<StartSelectionResult | null> {
    const projectRoot = `${sourceRoot} selekcja`;
    const candidates = new Map<string, { root: string; projectId?: string }>();
    const key = (root: string) => path.resolve(root).toLowerCase();
    try {
      const files = new SecureFiles(projectRoot);
      await files.verifyRoot();
      if ((await files.names()).length)
        candidates.set(key(projectRoot), { root: projectRoot });
    } catch (error) {
      if (!isMissing(error)) throw error;
    }
    const cachedRoots = new Set<string>();
    for (const entry of await this.recentCache.list()) {
      const rootKey = key(entry.projectRoot);
      if (cachedRoots.has(rootKey)) continue;
      cachedRoots.add(rootKey);
      if (entry.sourceRoot && key(entry.sourceRoot) === key(sourceRoot))
        candidates.set(key(entry.projectRoot), {
          root: entry.projectRoot,
          projectId: entry.projectId,
        });
    }
    if (candidates.size > 1)
      throw new SelectorError(
        'SOURCE_PROJECT_AMBIGUOUS',
        'Ten folder ma kilka projektów. Wybierz właściwy z historii.',
      );
    const existing = candidates.values().next().value;
    if (existing) {
      let missing = false;
      try {
        await lstat(existing.root);
      } catch (error) {
        if (!isMissing(error)) throw error;
        missing = true;
      }
      if (missing) {
        if (
          !(await this.dialogs.confirm(
            `Nie znaleziono folderu projektu:\n${existing.root}\n\nJeżeli projekt został przeniesiony, anuluj i wskaż go przez „Wybierz folder zdjęć”. „Nowa partia” zapomina tylko martwy wpis historii i otwiera nową konfigurację. Nie usuwa plików. Rozpocząć nową partię?`,
            'Nowa partia',
          ))
        )
          return null;
        // A moved/restored project may reappear while the dialog is open.
        // Never discard its identity or progress based on the old check.
        try {
          await lstat(existing.root);
          missing = false;
        } catch (error) {
          if (!isMissing(error)) throw error;
        }
        if (missing) await this.recentCache.forgetRoot(existing.root);
      }
      if (!missing) {
        await this.closeInternal();
        const store = await ProjectStore.open(existing.root, {
          expectedSourceRoot: sourceRoot,
          expectedProjectId: existing.projectId,
        });
        const workspace = await this.replaceStore(store);
        this.draft = null;
        return { kind: 'existing', workspace };
      }
    }
    const oldOutput = legacyOutput ?? `${sourceRoot} wybrane`;
    try {
      const files = new SecureFiles(oldOutput);
      if ((await files.names()).includes(OUTPUT_MANIFEST_NAME))
        return {
          kind: 'legacy',
          preview: await this.inspectLegacySelection(
            sourceRoot,
            oldOutput,
            true,
          ),
        };
    } catch (error) {
      if (!isMissing(error)) throw error;
    }
    const draft: NewProjectDraft = {
      sourceToken: randomUUID(),
      sourceName: path.basename(sourceRoot),
      sourcePath: sourceRoot,
      projectPath: projectRoot,
      outputParentPath: path.dirname(sourceRoot),
    };
    this.draft = { value: draft };
    return { kind: 'new', draft: { ...draft } };
  }
  create(value: unknown): Promise<DesktopWorkspace | null> {
    return this.serial(async () => {
      const options = validateCreate(value);
      const draft = options.sourceToken ? this.draft : null;
      if (
        options.sourceToken &&
        (!draft || options.sourceToken !== draft.value.sourceToken)
      )
        throw new SelectorError(
          'STALE_SOURCE_TOKEN',
          'Wybierz folder zdjęć ponownie.',
        );
      if (draft?.result) {
        if (
          draft.request !== JSON.stringify(options) ||
          this.store?.workspaceSnapshot().projectId !== draft.result.projectId
        )
          throw new SelectorError(
            'STALE_SOURCE_TOKEN',
            'Projekt został zmieniony.',
          );
        return this.snapshot();
      }
      const sourceRoot = draft
        ? draft.value.sourcePath
        : await this.dialogs.directory('Wybierz katalog źródłowych zdjęć');
      if (!sourceRoot) return null;
      let projectRoot = `${sourceRoot} selekcja`;
      let outputRoot = draft
        ? path.join(path.dirname(sourceRoot), outputDirectoryName(options))
        : `${sourceRoot} wybrane`;
      if (options.customLocations) {
        const selectedProject = await this.dialogs.directory(
          'Wybierz pusty katalog projektu',
          projectRoot,
        );
        if (!selectedProject) return null;
        const selectedOutput = await this.dialogs.directory(
          'Wybierz pusty katalog wynikowy',
          outputRoot,
        );
        if (!selectedOutput) return null;
        projectRoot = selectedProject;
        outputRoot = selectedOutput;
      }
      if (
        !draft &&
        !(await this.dialogs.confirm(
          `Źródło: ${sourceRoot}\nProjekt: ${projectRoot}\nWynik: ${outputRoot}\n\nProjekt i wynik są na lokalnym dysku poza synchronizacją. Utworzyć projekt?`,
        ))
      )
        return null;
      if (options.gameName) await this.gameCatalog.add(options.gameName);
      const store = await ProjectStore.create({
        sourceRoot,
        projectRoot,
        outputRoot,
        ...options,
      });
      let result: DesktopWorkspace;
      try {
        await this.closeInternal();
        result = await this.replaceStore(store);
      } catch (error) {
        await store.close();
        throw error;
      }
      if (draft) {
        draft.request = JSON.stringify(options);
        draft.result = result;
      }
      return result;
    });
  }
  open(projectId?: unknown): Promise<DesktopWorkspace | null> {
    return this.serial(async () => {
      let root: string | null;
      if (projectId !== undefined) {
        validateId(projectId);
        root =
          (await this.recentCache.list()).find((r) => r.projectId === projectId)
            ?.projectRoot ?? null;
        if (!root)
          throw new SelectorError(
            'UNKNOWN_PROJECT',
            'Projekt nie jest na liście ostatnich projektów.',
          );
      } else
        root = await this.dialogs.directory('Otwórz katalog projektu selekcji');
      if (!root) return null;
      await this.closeInternal();
      return this.replaceStore(
        await ProjectStore.open(root, {
          expectedProjectId: projectId as string | undefined,
        }),
      );
    });
  }
  execute(value: unknown): Promise<DesktopWorkspace> {
    return this.serial(async () => {
      const request = object(value, ['projectId', 'operationId', 'command']);
      validateId(request.projectId);
      validateId(request.operationId);
      const store = this.active();
      if (store.workspaceSnapshot().projectId !== request.projectId)
        throw new SelectorError('STALE_PROJECT', 'Projekt został zmieniony.');
      const command = object(request.command, [
        'kind',
        'imageId',
        'start',
        'direction',
        'expectedRevision',
        'previewChecksum',
      ]);
      let native: ProjectCommand;
      if (command.kind === 'accept' || command.kind === 'navigate') {
        if (Object.keys(command).sort().join(',') !== 'imageId,kind')
          throw new SelectorError(
            'INVALID_ARGUMENT',
            'Niedozwolone argumenty zdjęcia.',
          );
        validateId(command.imageId);
        const image = this.source?.images.find((i) => i.id === command.imageId);
        if (!image || !store.hasImage(image.relativePath))
          throw new SelectorError(
            'UNKNOWN_IMAGE',
            'Zdjęcie nie należy do projektu.',
          );
        native = { kind: command.kind, imagePath: image.relativePath };
      } else if (command.kind === 'skip' || command.kind === 'undo') {
        if (Object.keys(command).length !== 1)
          throw new SelectorError(
            'INVALID_ARGUMENT',
            'Niedozwolone argumenty.',
          );
        native = { kind: command.kind };
      } else if (command.kind === 'range') {
        if (
          !['kind,start', 'direction,kind,start'].includes(
            Object.keys(command).sort().join(','),
          ) ||
          !Number.isSafeInteger(command.start) ||
          Number(command.start) < 1 ||
          Number(command.start) > MAX_SEQUENCE_NUMBER ||
          (command.direction !== undefined &&
            !['ascending', 'descending'].includes(String(command.direction)))
        )
          throw new SelectorError(
            'INVALID_ARGUMENT',
            'Podaj zakres od 1 do 500000 i prawidłowy kierunek.',
          );
        native = {
          kind: 'range',
          start: Number(command.start),
          ...(command.direction === undefined
            ? {}
            : { direction: command.direction as 'ascending' | 'descending' }),
        };
      } else if (command.kind === 'restart') {
        if (
          Object.keys(command).sort().join(',') !==
            'expectedRevision,kind,previewChecksum' ||
          !Number.isSafeInteger(command.expectedRevision) ||
          typeof command.previewChecksum !== 'string' ||
          !/^[a-f0-9]{64}$/.test(command.previewChecksum)
        )
          throw new SelectorError(
            'INVALID_ARGUMENT',
            'Nieprawidłowy podgląd restartu.',
          );
        native = {
          kind: 'restart',
          expectedRevision: Number(command.expectedRevision),
          previewChecksum: command.previewChecksum,
        };
      } else throw new SelectorError('INVALID_ARGUMENT', 'Nieznane polecenie.');
      await store.execute(request.operationId as string, native);
      return this.snapshot()!;
    });
  }
  resume(): Promise<DesktopWorkspace> {
    return this.serial(async () => {
      await this.active().resume();
      await this.refreshSource();
      await this.rememberActive();
      return this.snapshot()!;
    });
  }
  previewRestart() {
    return this.serial(() => this.active().previewRestart());
  }
  relink(kind: unknown): Promise<DesktopWorkspace | null> {
    return this.serial(async () => {
      if (kind !== 'source' && kind !== 'output')
        throw new SelectorError('INVALID_ARGUMENT', 'Nieprawidłowy katalog.');
      const store = this.active();
      const directory = await this.dialogs.directory(
        kind === 'source' ? 'Wskaż ponownie źródło' : 'Wskaż ponownie wynik',
      );
      if (!directory) return null;
      if (
        !(await this.dialogs.confirm(
          'Potwierdź lokalny katalog poza synchronizacją. Zawartość zostanie zweryfikowana; postęp nie zostanie wyzerowany.',
        ))
      )
        return null;
      await store.execute(randomUUID(), {
        kind: 'relink',
        ...(kind === 'source'
          ? { sourceRoot: directory }
          : { outputRoot: directory }),
      });
      await this.refreshSource();
      await this.rememberActive();
      return this.snapshot()!;
    });
  }
  saveView(projectId: unknown, value: unknown): Promise<void> {
    validateId(projectId);
    const view = validateView(value);
    if (projectId !== this.active().workspaceSnapshot().projectId)
      throw new SelectorError('STALE_PROJECT', 'Projekt został zmieniony.');
    this.view = view;
    return this.views.save(projectId as string, view);
  }
  async openOutput(): Promise<void> {
    const store = this.active();
    if (store.getIssue())
      throw new SelectorError(
        'PROJECT_BLOCKED',
        'Najpierw rozwiąż problem projektu.',
      );
    await this.dialogs.openFolder(store.workspaceSnapshot().outputRoot);
  }
}
