import { randomUUID } from 'node:crypto';
import {
  SelectorError,
  type ShutdownReply,
  type ShutdownRequest,
} from '../contracts.ts';

export class ShutdownHandshake {
  private pending: {
    request: ShutdownRequest;
    resolve: () => void;
    reject: (error: Error) => void;
    timer: ReturnType<typeof setTimeout>;
  } | null = null;
  request(
    projectId: string | null,
    send: (request: ShutdownRequest) => void,
    timeoutMs = 10000,
  ): Promise<void> {
    if (this.pending) throw new SelectorError('CLOSING', 'Zamykanie już trwa.');
    return new Promise((resolve, reject) => {
      const request = { token: randomUUID(), projectId };
      const timer = setTimeout(() => {
        this.pending = null;
        reject(
          new SelectorError(
            'SHUTDOWN_TIMEOUT',
            'Nie zamknięto — przekroczono czas oczekiwania. Spróbuj ponownie.',
          ),
        );
      }, timeoutMs);
      this.pending = { request, resolve, reject, timer };
      send(request);
    });
  }
  reply(value: unknown, activeProjectId: string | null) {
    const reply = value as ShutdownReply;
    const pending = this.pending;
    if (
      !reply ||
      typeof reply !== 'object' ||
      Object.keys(reply).some(
        (key) => !['token', 'projectId', 'ready', 'message'].includes(key),
      ) ||
      typeof reply.ready !== 'boolean' ||
      (reply.message !== undefined &&
        (typeof reply.message !== 'string' || reply.message.length > 500)) ||
      !pending ||
      reply.token !== pending.request.token ||
      reply.projectId !== pending.request.projectId ||
      activeProjectId !== reply.projectId
    )
      throw new SelectorError(
        'INVALID_SHUTDOWN',
        'Nieaktualne potwierdzenie zamknięcia.',
      );
    clearTimeout(pending.timer);
    this.pending = null;
    if (reply.ready) pending.resolve();
    else
      pending.reject(
        new SelectorError(
          'SHUTDOWN_PENDING',
          reply.message || 'Dokończ zapis albo anuluj oczekiwanie.',
        ),
      );
  }
}

export class DesktopLifecycle {
  private closing = false;
  private relaunchScheduled = false;

  beginClosing() {
    this.closing = true;
  }
  cancelClosing() {
    this.closing = false;
    this.relaunchScheduled = false;
  }

  secondInstance(): 'focus' | 'relaunch' | 'pending' {
    if (!this.closing) return 'focus';
    if (this.relaunchScheduled) return 'pending';
    this.relaunchScheduled = true;
    return 'relaunch';
  }
}
