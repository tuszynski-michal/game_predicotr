export class RemoteSelectionInteractionQueue {
  private tail: Promise<void> = Promise.resolve();

  enqueue<T>(work: () => Promise<T>): Promise<T> {
    const result = this.tail.catch(() => undefined).then(work);
    this.tail = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }

  idle(): Promise<void> {
    return this.tail;
  }
}
