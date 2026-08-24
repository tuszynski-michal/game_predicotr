'use client';

export interface RemoteSelectionTabState {
  readonly mode: 'writer' | 'read_only';
  readonly ownerClientInstanceId: string | null;
  readonly supported: boolean;
}

type TabMessage = {
  readonly schemaVersion: 1;
  readonly sessionId: string;
  readonly senderClientInstanceId: string;
  readonly senderTabInstanceId?: string;
  readonly claimedAtMs: number;
  readonly kind: 'hello' | 'owner' | 'heartbeat' | 'release';
};

export interface RemoteSelectionBroadcastChannel {
  onmessage: ((event: MessageEvent<TabMessage>) => void) | null;
  close(): void;
  postMessage(message: TabMessage): void;
}

type ChannelFactory = (name: string) => RemoteSelectionBroadcastChannel;

const HEARTBEAT_MS = 2_000;
const OWNER_STALE_MS = 6_000;
const DISCOVERY_MS = 80;

export class RemoteSelectionTabCoordinator {
  private readonly sessionId: string;
  private readonly clientInstanceId: string;
  private readonly tabInstanceId: string;
  private readonly channelFactory: ChannelFactory | null;
  private readonly now: () => number;
  private readonly discoveryMs: number;
  private readonly heartbeatMs: number;
  private readonly staleMs: number;
  private channel: RemoteSelectionBroadcastChannel | null = null;
  private interval: ReturnType<typeof setInterval> | null = null;
  private owner: {
    readonly clientInstanceId: string;
    readonly tabInstanceId: string;
    readonly claimedAtMs: number;
    readonly seenAtMs: number;
  } | null = null;
  private claimedAtMs: number;
  private listeners = new Set<(state: RemoteSelectionTabState) => void>();

  constructor(
    sessionId: string,
    clientInstanceId: string,
    options: {
      readonly channelFactory?: ChannelFactory | null;
      readonly discoveryMs?: number;
      readonly heartbeatMs?: number;
      readonly staleMs?: number;
      readonly now?: () => number;
      readonly tabInstanceId?: string;
    } = {},
  ) {
    this.sessionId = sessionId;
    this.clientInstanceId = clientInstanceId;
    this.channelFactory =
      options.channelFactory === undefined
        ? defaultChannelFactory()
        : options.channelFactory;
    this.now = options.now ?? Date.now;
    this.discoveryMs = options.discoveryMs ?? DISCOVERY_MS;
    this.heartbeatMs = options.heartbeatMs ?? HEARTBEAT_MS;
    this.staleMs = options.staleMs ?? OWNER_STALE_MS;
    this.tabInstanceId = options.tabInstanceId ?? createTabInstanceId();
    this.claimedAtMs = this.now();
  }

  async start(): Promise<RemoteSelectionTabState> {
    if (this.channelFactory === null) return this.state();
    if (this.channel !== null) return this.state();
    this.channel = this.channelFactory(
      `game-predictor-remote-selection:${this.sessionId}`,
    );
    this.channel.onmessage = (event) => this.receive(event.data);
    this.post('hello');
    await delay(this.discoveryMs);
    this.claimIfAvailable();
    this.interval = setInterval(() => this.tick(), this.heartbeatMs);
    return this.state();
  }

  state(): RemoteSelectionTabState {
    const liveOwner = this.liveOwner();
    return {
      mode:
        liveOwner === null || liveOwner.tabInstanceId === this.tabInstanceId
          ? 'writer'
          : 'read_only',
      ownerClientInstanceId:
        liveOwner?.clientInstanceId ??
        (this.channelFactory === null ? this.clientInstanceId : null),
      supported: this.channelFactory !== null,
    };
  }

  subscribe(listener: (state: RemoteSelectionTabState) => void): () => void {
    this.listeners.add(listener);
    listener(this.state());
    return () => this.listeners.delete(listener);
  }

  claimIfAvailable(): RemoteSelectionTabState {
    if (this.liveOwner() !== null) return this.state();
    this.claimedAtMs = this.now();
    this.owner = {
      claimedAtMs: this.claimedAtMs,
      clientInstanceId: this.clientInstanceId,
      tabInstanceId: this.tabInstanceId,
      seenAtMs: this.now(),
    };
    this.post('owner');
    this.emit();
    return this.state();
  }

  close(): void {
    if (this.owner?.tabInstanceId === this.tabInstanceId) {
      this.post('release');
    }
    if (this.interval !== null) clearInterval(this.interval);
    this.interval = null;
    if (this.channel !== null) {
      this.channel.onmessage = null;
      this.channel.close();
    }
    this.channel = null;
    this.owner = null;
    this.emit();
  }

  private receive(message: TabMessage): void {
    const senderTabInstanceId =
      typeof message.senderTabInstanceId === 'string' &&
      message.senderTabInstanceId !== ''
        ? message.senderTabInstanceId
        : `legacy:${message.senderClientInstanceId}`;
    if (
      message.schemaVersion !== 1 ||
      message.sessionId !== this.sessionId ||
      senderTabInstanceId === this.tabInstanceId
    ) {
      return;
    }
    if (message.kind === 'hello') {
      if (this.owner?.tabInstanceId === this.tabInstanceId) {
        this.post('owner');
      }
      return;
    }
    if (message.kind === 'release') {
      if (this.owner?.tabInstanceId === senderTabInstanceId) {
        this.owner = null;
        this.emit();
      }
      return;
    }
    const candidate = {
      claimedAtMs: message.claimedAtMs,
      clientInstanceId: message.senderClientInstanceId,
      tabInstanceId: senderTabInstanceId,
      seenAtMs: this.now(),
    };
    const current = this.liveOwner();
    if (current === null || compareClaims(candidate, current) < 0) {
      this.owner = candidate;
      this.emit();
    } else if (current.tabInstanceId === candidate.tabInstanceId) {
      this.owner = candidate;
    }
  }

  private tick(): void {
    const owner = this.liveOwner();
    if (owner?.tabInstanceId === this.tabInstanceId) {
      this.owner = { ...owner, seenAtMs: this.now() };
      this.post('heartbeat');
      return;
    }
    if (owner === null) this.claimIfAvailable();
  }

  private liveOwner() {
    if (this.owner === null) return null;
    if (
      this.owner.tabInstanceId !== this.tabInstanceId &&
      this.now() - this.owner.seenAtMs > this.staleMs
    ) {
      this.owner = null;
      return null;
    }
    return this.owner;
  }

  private post(kind: TabMessage['kind']): void {
    this.channel?.postMessage({
      schemaVersion: 1,
      claimedAtMs: this.claimedAtMs,
      kind,
      senderClientInstanceId: this.clientInstanceId,
      senderTabInstanceId: this.tabInstanceId,
      sessionId: this.sessionId,
    });
  }

  private emit(): void {
    const state = this.state();
    for (const listener of this.listeners) listener(state);
  }
}

function compareClaims(
  left: {
    readonly claimedAtMs: number;
    readonly clientInstanceId: string;
    readonly tabInstanceId: string;
  },
  right: {
    readonly claimedAtMs: number;
    readonly clientInstanceId: string;
    readonly tabInstanceId: string;
  },
): number {
  return (
    left.claimedAtMs - right.claimedAtMs ||
    left.clientInstanceId.localeCompare(right.clientInstanceId) ||
    left.tabInstanceId.localeCompare(right.tabInstanceId)
  );
}

function defaultChannelFactory(): ChannelFactory | null {
  if (typeof BroadcastChannel === 'undefined') return null;
  return (name) => new BroadcastChannel(name);
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function createTabInstanceId(): string {
  const webCrypto = globalThis.crypto;
  if (typeof webCrypto?.randomUUID === 'function')
    return webCrypto.randomUUID();
  if (typeof webCrypto?.getRandomValues === 'function') {
    const values = new Uint32Array(4);
    webCrypto.getRandomValues(values);
    return [...values]
      .map((value) => value.toString(16).padStart(8, '0'))
      .join('');
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
