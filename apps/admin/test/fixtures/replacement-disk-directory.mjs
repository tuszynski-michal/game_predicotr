import { readFile, writeFile, readdir, stat } from 'node:fs/promises';
import { join, resolve, relative, basename } from 'node:path';

// Real disk bytes with FSA's close boundary and injected lost-response/crash points.
export class DiskDirectory {
  kind = 'directory';
  constructor(path, hook = () => undefined, readonly = false) {
    this.path = resolve(path);
    this.name = basename(path);
    this.hook = hook;
    this.readonly = readonly;
    this.writes = 0;
  }
  async isSameEntry(other) {
    return this.path === other.path;
  }
  async resolve(other) {
    const value = relative(this.path, other.path);
    return value.startsWith('..') ? null : value.split(/[\\/]/).filter(Boolean);
  }
  async *entries() {
    for (const row of await readdir(this.path, { withFileTypes: true }))
      yield [
        row.name,
        row.isDirectory()
          ? new DiskDirectory(join(this.path, row.name))
          : await this.getFileHandle(row.name),
      ];
  }
  async getFileHandle(name, options) {
    const target = join(this.path, name);
    try {
      await stat(target);
    } catch (cause) {
      if (cause.code !== 'ENOENT') throw cause;
      if (!options?.create) throw new DOMException('missing', 'NotFoundError');
      if (this.readonly) throw new Error('SOURCE_WRITE');
      await writeFile(target, '');
    }
    return {
      kind: 'file',
      name,
      getFile: async () =>
        new File([await readFile(target)], name, {
          type: name.endsWith('.json') ? 'application/json' : 'image/jpeg',
        }),
      createWritable: async () => {
        this.writes++;
        if (this.readonly) throw new Error('SOURCE_WRITE');
        let bytes;
        return {
          write: async (data) => {
            bytes =
              typeof data === 'string'
                ? Buffer.from(data)
                : Buffer.from(await data.arrayBuffer());
          },
          abort: async () => undefined,
          close: async () => {
            this.hook(name, 'before', bytes);
            await writeFile(target, bytes);
            this.hook(name, 'after', bytes);
          },
        };
      },
    };
  }
}
