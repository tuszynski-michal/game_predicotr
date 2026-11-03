import type { SourceIndex, SourceImage } from '../contracts.ts';
import { sourceLookup } from '../source-index.ts';

export const PREVIEW_BITMAP_BUDGET = 128 * 1024 * 1024;
interface Entry {
  image: HTMLImageElement;
  decoded: boolean;
  bytes: number;
  promise: Promise<HTMLImageElement>;
}
/** Owns the actual DOM images. The byte estimate is not a Chromium RSS limit. */
export class PreviewCache {
  private entries = new Map<string, Entry>();
  private source: SourceIndex | null = null;
  private target: SourceImage | null = null;
  private allowed: SourceImage[] = [];
  private window: SourceImage[] = [];
  private prefetch: Entry | null = null;
  private generation = 0;
  private displayed: SourceImage | null = null;
  private transitioning = false;
  private direction = 1;
  private createImage: () => HTMLImageElement;
  constructor(createImage: () => HTMLImageElement = () => new Image()) {
    this.createImage = createImage;
  }
  get size() {
    return this.entries.size;
  }
  get estimatedBytes() {
    return [...this.entries.values()].reduce(
      (sum, entry) => sum + entry.bytes,
      0,
    );
  }
  private key(image: SourceImage) {
    return `${this.source!.id}/${image.id}`;
  }
  private remove(key: string, entry: Entry) {
    this.entries.delete(key);
    entry.image.remove();
    entry.image.removeAttribute('src');
  }
  clear() {
    this.generation++;
    for (const [key, entry] of this.entries) this.remove(key, entry);
    this.displayed = null;
    this.source = null;
    this.target = null;
    this.allowed = [];
    this.window = [];
  }
  private trim() {
    const active = this.target && this.key(this.target);
    const visible = this.displayed && this.key(this.displayed);
    const allowed = new Set(this.allowed.map((image) => this.key(image)));
    for (const [key, entry] of this.entries)
      if (!allowed.has(key) && key !== visible) this.remove(key, entry);
    // allowed is nearest first, so release farthest inactive images first.
    for (const image of [...this.allowed].reverse()) {
      if (this.estimatedBytes <= PREVIEW_BITMAP_BUDGET) break;
      const key = this.key(image);
      const entry = this.entries.get(key);
      if (key !== active && key !== visible && entry) this.remove(key, entry);
    }
  }
  private load(image: SourceImage): Entry {
    const key = this.key(image);
    const existing = this.entries.get(key);
    if (existing) return existing;
    const element = this.createImage();
    const entry: Entry = {
      image: element,
      decoded: false,
      bytes: 0,
      promise: null!,
    };
    this.entries.set(key, entry);
    element.src = image.url;
    entry.promise = element
      .decode()
      .then(() => {
        if (this.entries.get(key) !== entry)
          throw new Error('Preview invalidated');
        entry.decoded = true;
        entry.bytes = element.naturalWidth * element.naturalHeight * 4;
        this.trim();
        return element;
      })
      .catch((error) => {
        if (this.entries.get(key) === entry) this.remove(key, entry);
        throw error;
      });
    return entry;
  }
  async activate(
    source: SourceIndex,
    image: SourceImage,
    step = 1,
    retainDisplayed = false,
  ): Promise<HTMLImageElement> {
    if (this.source !== source) this.clear();
    this.source = source;
    const previous =
      this.target && sourceLookup(source).ordinal.get(this.target.id);
    this.target = image;
    this.transitioning = retainDisplayed;
    const generation = ++this.generation;
    const ordinal = sourceLookup(source).ordinal.get(image.id);
    if (ordinal === undefined) throw new Error('Unknown preview image');
    if (previous !== null && previous !== undefined && ordinal !== previous)
      this.direction = ordinal > previous ? 1 : -1;
    const stride = Math.max(1, Math.trunc(step));
    this.allowed = [image];
    for (let distance = 1; distance <= 3; distance++)
      for (const position of [
        ordinal + distance * stride * this.direction,
        ordinal - distance * stride * this.direction,
      ])
        if (source.images[position]) this.allowed.push(source.images[position]);
    this.window = [...this.allowed];
    // Retaining the visible image consumes one of the seven slots.
    if (
      this.displayed &&
      !this.allowed.some((i) => i.id === this.displayed!.id)
    )
      this.allowed.splice(6, 1, this.displayed);
    this.trim();
    const element = await this.load(image).promise;
    if (generation !== this.generation) throw new Error('Preview superseded');
    if (!retainDisplayed) this.present(image.id);
    return element;
  }
  /** Called only after the decoded target has replaced the visible DOM image. */
  present(imageId: string) {
    if (this.target?.id !== imageId) return;
    this.displayed = this.target;
    this.allowed = this.window;
    this.transitioning = false;
    this.trim();
    this.schedulePrefetch();
  }
  private schedulePrefetch() {
    if (this.transitioning || this.prefetch || !this.source || !this.target)
      return;
    const active = this.entries.get(this.key(this.target));
    if (!active?.decoded || active.bytes >= PREVIEW_BITMAP_BUDGET) return;
    this.trim();
    if (this.estimatedBytes >= PREVIEW_BITMAP_BUDGET) return;
    const next = this.allowed.find(
      (image) => !this.entries.has(this.key(image)),
    );
    if (!next) return;
    const entry = this.load(next);
    this.prefetch = entry;
    // A failed/evicted neighbour is not retried in this prefetch pass.
    void entry.promise
      .catch(() => {})
      .finally(() => {
        if (this.prefetch === entry) this.prefetch = null;
        // Continue only if this image survived the budget. Otherwise repeated
        // decode/evict would consume CPU indefinitely with oversized neighbours.
        if ([...this.entries.values()].includes(entry)) this.schedulePrefetch();
      });
  }
}
