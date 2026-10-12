import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { ProjectStore } from '../project/project-store.ts';
import { RecentProjects } from '../project/recent-projects.ts';
import type { ProjectCommand } from '../project/types.ts';
import { SourceRegistry } from './source-registry.ts';
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
  type CreateProjectRequest,
  type SourceIndex,
  type DesktopWorkspace,
  type ViewPreferences,
  type LegacyPreviewSummary,
} from '../contracts.ts';
export interface NativeDialogs {
  directory(title: string, defaultPath?: string): Promise<string | null>;
  confirm(message: string): Promise<boolean>;
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
  ]);
  if (
    !Number.isSafeInteger(v.firstLayout) ||
    Number(v.firstLayout) < 1 ||
    !['ascending', 'descending'].includes(String(v.direction)) ||
    (v.sequenceUpperBound !== null &&
      (!Number.isSafeInteger(v.sequenceUpperBound) ||
        Number(v.sequenceUpperBound) < Number(v.firstLayout))) ||
    typeof v.customLocations !== 'boolean' ||
    v.localStorageConfirmed !== true
  )
    throw new SelectorError(
      'INVALID_ARGUMENT',
      'Podaj prawidłową numerację i potwierdź lokalne katalogi.',
    );
  return v as unknown as CreateProjectRequest;
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
  private views: ViewPreferencesStore;
  private legacyProof: {
    token: string;
    proof: LegacyProof;
    result: DesktopWorkspace | null;
  } | null = null;
  constructor(
    userData: string,
    registry: SourceRegistry,
    dialogs: NativeDialogs,
  ) {
    this.registry = registry;
    this.dialogs = dialogs;
    this.recentCache = new RecentProjects(userData);
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
  async recent() {
    return (await this.recentCache.list()).map((r) => ({
      projectId: r.projectId,
      name: r.sourceDirectoryName,
      openedAt: r.openedAt,
    }));
  }
  private async refreshSource(): Promise<void> {
    const state = this.active().snapshot();
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
    const s = this.store.snapshot();
    const byPath = new Map(
      this.source?.images.map((i) => [i.relativePath, i.id]),
    );
    return {
      projectId: s.projectId,
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
    this.view = await this.views.load(store.snapshot().projectId);
    await this.refreshSource();
    const s = store.snapshot();
    await this.recentCache.remember({
      projectId: s.projectId,
      projectRoot: store.getProjectRoot(),
      sourceDirectoryName: s.sourceDirectoryName,
      openedAt: new Date().toISOString(),
    });
    return this.snapshot()!;
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
      const proof = await inspectLegacy(source, output);
      const token = randomUUID();
      this.legacyProof = { token, proof, result: null };
      const s = proof.seed;
      return {
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
          s.inventory.findIndex(
            (i) => i.relativePath === s.currentRelativePath,
          ) + 1,
        acceptedCount: s.decisions.filter((d) => d.action === 'accepted')
          .length,
        skippedCount: s.decisions.filter((d) => d.action === 'skipped').length,
        legacyCursor: proof.legacyCursor,
      };
    });
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
        if (this.store?.snapshot().projectId !== preview.result.projectId)
          throw new SelectorError(
            'LEGACY_PREVIEW_EXPIRED',
            'Projekt został zmieniony. Otwórz zapisany projekt.',
          );
        return this.snapshot();
      }
      const projectRoot = await this.dialogs.directory(
        'Wybierz nowy pusty katalog projektu',
      );
      if (!projectRoot) return null;
      const outputRoot = await this.dialogs.directory(
        'Wybierz nowy pusty katalog wynikowy',
      );
      if (!outputRoot) return null;
      if (
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
  create(value: unknown): Promise<DesktopWorkspace | null> {
    return this.serial(async () => {
      const options = validateCreate(value);
      const sourceRoot = await this.dialogs.directory(
        'Wybierz katalog źródłowych zdjęć',
      );
      if (!sourceRoot) return null;
      let projectRoot = `${sourceRoot} selekcja`;
      let outputRoot = `${sourceRoot} wybrane`;
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
        !(await this.dialogs.confirm(
          `Źródło: ${sourceRoot}\nProjekt: ${projectRoot}\nWynik: ${outputRoot}\n\nProjekt i wynik są na lokalnym dysku poza synchronizacją. Utworzyć projekt?`,
        ))
      )
        return null;
      await this.closeInternal();
      return this.replaceStore(
        await ProjectStore.create({
          sourceRoot,
          projectRoot,
          outputRoot,
          ...options,
        }),
      );
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
      return this.replaceStore(await ProjectStore.open(root));
    });
  }
  execute(value: unknown): Promise<DesktopWorkspace> {
    return this.serial(async () => {
      const request = object(value, ['projectId', 'operationId', 'command']);
      validateId(request.projectId);
      validateId(request.operationId);
      const store = this.active();
      if (store.snapshot().projectId !== request.projectId)
        throw new SelectorError('STALE_PROJECT', 'Projekt został zmieniony.');
      const command = object(request.command, [
        'kind',
        'imageId',
        'start',
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
        if (
          !image ||
          !store
            .snapshot()
            .inventory.some((i) => i.relativePath === image.relativePath)
        )
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
          Object.keys(command).sort().join(',') !== 'kind,start' ||
          !Number.isSafeInteger(command.start) ||
          Number(command.start) < 1
        )
          throw new SelectorError(
            'INVALID_ARGUMENT',
            'Podaj dodatni początek zakresu.',
          );
        native = { kind: 'range', start: Number(command.start) };
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
      return this.snapshot()!;
    });
  }
  saveView(projectId: unknown, value: unknown): Promise<void> {
    validateId(projectId);
    const view = validateView(value);
    if (projectId !== this.active().snapshot().projectId)
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
    await this.dialogs.openFolder(store.snapshot().outputRoot);
  }
}
