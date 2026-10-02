// Invalidating on pointer-down also rejects a response arriving during a gesture.
export class LatestPreview {
  private version = 0;
  invalidate() {
    return ++this.version;
  }
  async run<T>(
    request: () => Promise<T>,
    accept: (value: T) => void,
    reject: () => void,
  ) {
    const version = this.invalidate();
    try {
      const result = await request();
      if (version === this.version) accept(result);
    } catch {
      if (version === this.version) reject();
    }
  }
}
