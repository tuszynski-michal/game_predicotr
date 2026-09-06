export type SymbolReviewRequestChannel = 'counts' | 'page' | 'prefetch';

export class SymbolReviewRequestCoordinator {
  private readonly active = new Map<
    SymbolReviewRequestChannel,
    AbortController
  >();

  begin(channel: SymbolReviewRequestChannel): AbortController {
    this.cancel(channel);
    const controller = new AbortController();
    this.active.set(channel, controller);
    return controller;
  }

  cancel(channel: SymbolReviewRequestChannel): void {
    const controller = this.active.get(channel);
    if (controller === undefined) return;
    this.active.delete(channel);
    controller.abort();
  }

  cancelAll(): void {
    for (const channel of [...this.active.keys()]) this.cancel(channel);
  }

  cancelIfCurrent(
    channel: SymbolReviewRequestChannel,
    controller: AbortController,
  ): void {
    if (this.active.get(channel) === controller) this.cancel(channel);
  }

  finish(
    channel: SymbolReviewRequestChannel,
    controller: AbortController,
  ): void {
    if (this.active.get(channel) === controller) this.active.delete(channel);
  }

  isCurrent(
    channel: SymbolReviewRequestChannel,
    controller: AbortController,
  ): boolean {
    return (
      this.active.get(channel) === controller && !controller.signal.aborted
    );
  }

  activeCount(channel?: SymbolReviewRequestChannel): number {
    return channel === undefined
      ? this.active.size
      : Number(this.active.has(channel));
  }
}
