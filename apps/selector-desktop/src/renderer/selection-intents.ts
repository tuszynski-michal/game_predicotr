import { sourceLookup } from '../source-index.ts';
import { applyWorkspaceUpdate } from './workspace-updates.ts';
import type {
  DesktopCommand,
  DesktopWorkspace,
  DesktopWorkspaceUpdate,
  ExecuteRequest,
  NativeResult,
} from '../contracts.ts';

export type SelectionPhase =
  | 'idle'
  | 'navigating'
  | 'waiting_to_accept'
  | 'accepting'
  | 'recovering'
  | 'error';
export interface AcceptIntent {
  projectId: string;
  sourceId: string;
  imageId: string;
  rangeStart: number;
  direction: DesktopWorkspace['direction'];
  sequenceUpperBound: number | null;
  request: ExecuteRequest;
  deadline: number;
  dispatched: boolean;
}
export function matchesAcceptContext(
  intent: AcceptIntent,
  workspace: DesktopWorkspace,
): boolean {
  return (
    intent.projectId === workspace.projectId &&
    intent.sourceId === workspace.source?.id &&
    intent.rangeStart === workspace.nextRangeStart &&
    intent.direction === workspace.direction &&
    intent.sequenceUpperBound === workspace.sequenceUpperBound &&
    !workspace.issue &&
    !workspace.selectionComplete
  );
}
function value<T>(result: NativeResult<T>): T {
  if (!result.ok)
    throw new Error(`${result.error.message} (${result.error.code})`);
  return result.value;
}

/** Bounded input state. Only this coordinator dispatches renderer decisions. */
export class SelectionIntents {
  workspace: DesktopWorkspace | null = null;
  displayedImageId: string | null = null;
  pendingNavigation: string | null = null;
  acceptIntent: AcceptIntent | null = null;
  readyImageId: string | null = null;
  private failedImageId: string | null = null;
  phase: SelectionPhase = 'idle';
  message = '';
  closing = false;
  private inFlight: Promise<void> | null = null;
  private failedRequest: ExecuteRequest | null = null;
  private knownFailure = false;
  private scheduled = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private effects: {
    execute: (
      request: ExecuteRequest,
    ) => Promise<NativeResult<DesktopWorkspaceUpdate>>;
    snapshot: () => Promise<NativeResult<DesktopWorkspace | null>>;
    changed: () => void;
    frame: (callback: () => void) => void;
    operationId: () => string;
    now?: () => number;
  };
  constructor(effects: SelectionIntents['effects']) {
    this.effects = effects;
  }
  get mutating() {
    return Boolean(
      this.inFlight ||
      this.acceptIntent ||
      this.failedRequest ||
      this.pendingNavigation,
    );
  }
  get blocked() {
    return Boolean(
      this.acceptIntent ||
      this.failedRequest ||
      this.closing ||
      this.workspace?.issue,
    );
  }
  get recoverableError() {
    return this.phase === 'error' && this.knownFailure && !this.inFlight;
  }
  install(workspace: DesktopWorkspace | null) {
    if (this.inFlight) throw new Error('Operacja nadal trwa.');
    this.clearAccept();
    this.workspace = workspace;
    this.displayedImageId = workspace?.currentImageId ?? null;
    this.pendingNavigation = this.readyImageId = null;
    this.failedImageId = null;
    this.failedRequest = null;
    this.knownFailure = false;
    this.phase = 'idle';
    this.message = '';
    this.effects.changed();
  }
  updateView(workspace: DesktopWorkspace) {
    if (this.workspace?.projectId === workspace.projectId)
      this.workspace = workspace;
  }
  move(delta: number) {
    const source = this.workspace?.source;
    if (
      !source ||
      this.blocked ||
      ['error', 'accepting', 'recovering'].includes(this.phase)
    )
      return;
    const ordinal =
      sourceLookup(source).ordinal.get(this.displayedImageId ?? '') ?? -1;
    const target =
      source.images[
        Math.max(0, Math.min(source.images.length - 1, ordinal + delta))
      ];
    if (!target || target.id === this.displayedImageId) return;
    this.displayedImageId = this.pendingNavigation = target.id;
    this.readyImageId = null;
    this.failedImageId = null;
    this.message = '';
    this.schedule();
  }
  accept() {
    if (this.acceptIntent) {
      this.effects.changed();
      return;
    }
    const workspace = this.workspace;
    const imageId = this.displayedImageId;
    if (imageId && imageId === this.failedImageId) {
      this.message = 'Nie zapisano — nie można odczytać JPEG-a.';
      this.effects.changed();
      return;
    }
    if (
      !workspace?.source ||
      !imageId ||
      this.blocked ||
      ['error', 'accepting', 'recovering'].includes(this.phase) ||
      workspace.selectionComplete ||
      workspace.acceptedImageIds.includes(imageId)
    ) {
      this.message =
        'Nie zapisano — zdjęcie lub projekt nie jest gotowy do wyboru.';
      this.effects.changed();
      return;
    }
    this.acceptIntent = {
      projectId: workspace.projectId,
      sourceId: workspace.source.id,
      imageId,
      rangeStart: workspace.nextRangeStart,
      direction: workspace.direction,
      sequenceUpperBound: workspace.sequenceUpperBound,
      request: {
        projectId: workspace.projectId,
        operationId: this.effects.operationId(),
        command: { kind: 'accept', imageId },
      },
      deadline: (this.effects.now?.() ?? Date.now()) + 10000,
      dispatched: false,
    };
    this.pendingNavigation =
      workspace.currentImageId === imageId ? null : imageId;
    this.phase = 'waiting_to_accept';
    this.message = 'Oczekuje na zapis';
    this.timer = setTimeout(() => this.expire(), 10000);
    this.effects.changed();
    this.pump();
  }
  cancelAccept() {
    if (!this.acceptIntent || this.acceptIntent.dispatched) return;
    this.clearAccept();
    this.phase = this.inFlight ? 'navigating' : 'idle';
    this.message = 'Nie zapisano — anulowano oczekiwanie.';
    this.effects.changed();
    this.pump();
  }
  expire() {
    if (
      !this.acceptIntent ||
      this.acceptIntent.dispatched ||
      (this.effects.now?.() ?? Date.now()) < this.acceptIntent.deadline
    )
      return;
    this.clearAccept();
    this.message = 'Nie zapisano — podgląd nie jest gotowy. Spróbuj ponownie';
    this.phase = this.inFlight ? 'navigating' : 'idle';
    this.effects.changed();
  }
  decoded(imageId: string | null, failedImageId?: string) {
    if (failedImageId === this.displayedImageId)
      this.failedImageId = failedImageId;
    if (imageId === this.displayedImageId) this.failedImageId = null;
    if (
      failedImageId &&
      failedImageId === this.acceptIntent?.imageId &&
      !this.acceptIntent.dispatched
    ) {
      this.clearAccept();
      this.message = 'Nie zapisano — nie można odczytać JPEG-a.';
      this.phase = this.inFlight ? 'navigating' : 'idle';
    }
    this.readyImageId = imageId === this.displayedImageId ? imageId : null;
    this.effects.changed();
    this.pump();
  }
  command(command: DesktopCommand) {
    if (
      !this.workspace ||
      this.blocked ||
      this.mutating ||
      this.phase === 'error'
    )
      return;
    this.send({
      projectId: this.workspace.projectId,
      operationId: this.effects.operationId(),
      command,
    });
  }
  private schedule() {
    if (this.scheduled) return;
    this.scheduled = true;
    this.effects.frame(() => {
      this.scheduled = false;
      this.effects.changed();
      this.pump();
    });
  }
  private clearAccept() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.acceptIntent = null;
  }
  private pump() {
    if (
      this.inFlight ||
      this.failedRequest ||
      !this.workspace ||
      this.workspace.issue ||
      this.phase === 'error'
    )
      return;
    this.expire();
    const intent = this.acceptIntent;
    if (intent && !matchesAcceptContext(intent, this.workspace)) {
      this.clearAccept();
      this.pendingNavigation = null;
      this.phase = 'error';
      this.message = 'Nie zapisano — zmienił się projekt, źródło lub zakres.';
      this.effects.changed();
      return;
    }
    const target = intent?.imageId ?? this.pendingNavigation;
    if (target && target !== this.workspace.currentImageId) {
      this.pendingNavigation = null;
      this.send({
        projectId: this.workspace.projectId,
        operationId: this.effects.operationId(),
        command: { kind: 'navigate', imageId: target },
      });
    } else {
      this.pendingNavigation = null;
      if (intent && this.readyImageId === intent.imageId) {
        intent.dispatched = true;
        if (this.timer) clearTimeout(this.timer);
        this.timer = null;
        this.send(intent.request);
      } else {
        this.phase = intent ? 'waiting_to_accept' : 'idle';
        this.effects.changed();
      }
    }
  }
  private apply(update: DesktopWorkspaceUpdate, request: ExecuteRequest) {
    const result = applyWorkspaceUpdate(this.workspace, update);
    const keepReady =
      this.workspace?.projectId === result.projectId &&
      this.workspace?.source?.id === result.source?.id &&
      this.displayedImageId === result.currentImageId &&
      this.readyImageId === result.currentImageId &&
      this.failedImageId !== result.currentImageId;
    this.workspace = result;
    if (request.command.kind !== 'navigate') {
      this.displayedImageId = result.currentImageId;
      // Range/undo can retain the same DOM image: no new decode callback follows.
      // A different project/source/target or decode error must still wait.
      if (!keepReady) this.readyImageId = null;
      this.pendingNavigation = null;
    }
    if (request.command.kind === 'accept') {
      this.clearAccept();
      this.message = '';
    }
    if (result.issue) {
      this.clearAccept();
      this.pendingNavigation = null;
    }
  }
  private send(request: ExecuteRequest) {
    this.phase =
      request.command.kind === 'accept'
        ? 'accepting'
        : request.command.kind === 'navigate'
          ? this.acceptIntent
            ? 'waiting_to_accept'
            : 'navigating'
          : 'accepting';
    this.inFlight = Promise.resolve().then(async () => {
      let knownFailure = false;
      try {
        const response = await this.effects.execute(request);
        if (!response.ok) {
          // A known native failure is surfaced; retry is an explicit operator action.
          this.failedRequest = request;
          knownFailure = true;
          throw new Error(`${response.error.message} (${response.error.code})`);
        }
        this.apply(response.value, request);
      } catch (cause) {
        this.phase = 'recovering';
        this.effects.changed();
        try {
          const snapshot = value(await this.effects.snapshot());
          if (
            !snapshot ||
            snapshot.projectId !== request.projectId ||
            snapshot.source?.id !== this.workspace?.source?.id
          )
            throw new Error('Nie można potwierdzić aktywnego projektu.');
          this.workspace = { ...snapshot, view: this.workspace!.view };
          if (
            request.command.kind === 'accept' &&
            !this.failedRequest &&
            !snapshot.issue
          ) {
            // Lost response: receipt lookup uses the identical request and operationId.
            this.apply(value(await this.effects.execute(request)), request);
            this.message = '';
            return;
          }
          if (request.command.kind !== 'accept' || knownFailure)
            this.clearAccept();
          if (knownFailure) this.pendingNavigation = null;
          this.failedRequest = request;
          this.knownFailure = knownFailure;
          this.message =
            cause instanceof Error
              ? cause.message
              : 'Wynik operacji jest nieznany.';
        } catch (recoveryError) {
          this.failedRequest = request;
          this.knownFailure = false;
          this.message = `Nie potwierdzono zapisu. Wznów połączenie. ${recoveryError instanceof Error ? recoveryError.message : ''}`;
        }
        this.phase = 'error';
      } finally {
        this.inFlight = null;
        this.effects.changed();
        this.pump();
      }
    });
    this.effects.changed();
  }
  retry() {
    if (this.inFlight) return;
    if (!this.failedRequest) {
      this.phase = 'recovering';
      this.inFlight = Promise.resolve().then(async () => {
        try {
          const snapshot = value(await this.effects.snapshot());
          this.inFlight = null;
          this.install(snapshot);
        } catch (cause) {
          this.inFlight = null;
          this.phase = 'error';
          this.message =
            cause instanceof Error
              ? cause.message
              : 'Nie można odczytać projektu.';
          this.effects.changed();
        }
      });
      this.effects.changed();
      return;
    }
    const request = this.failedRequest;
    this.failedRequest = null;
    this.knownFailure = false;
    this.message = '';
    this.send(request);
  }
  async flushForClose(): Promise<void> {
    this.closing = true;
    this.effects.changed();
    try {
      if (this.acceptIntent && !this.acceptIntent.dispatched)
        throw new Error(
          'Oczekuje wybór. Anuluj oczekiwanie albo dokończ zapis przed zamknięciem.',
        );
      if (this.failedRequest && !this.knownFailure)
        throw new Error(
          'Nie potwierdzono operacji. Wznów zapis przed zamknięciem.',
        );
      if (this.knownFailure) {
        // Native returned an explicit failure and snapshot confirmed the project.
        // Existing close/recovery can now release only our own lock.
        this.failedRequest = null;
        this.clearAccept();
        this.pendingNavigation = null;
        return;
      }
      this.pump();
      while (this.inFlight) await this.inFlight;
      if (this.failedRequest || this.pendingNavigation)
        throw new Error('Nie udało się utrwalić ostatniego celu nawigacji.');
    } catch (error) {
      this.closing = false;
      this.effects.changed();
      throw error;
    }
  }
  cancelClose(message = '') {
    this.closing = false;
    if (message) this.message = message;
    this.effects.changed();
  }
}
