import path from 'node:path';
import { isGameUpdate } from '../contracts.ts';
import {
  ensureDirectory,
  SecureFiles,
  stableStringify,
} from '../filesystem/secure-files.ts';

export interface RecentProject {
  projectId: string;
  projectRoot: string;
  sourceDirectoryName: string;
  sourceRoot?: string;
  gameName?: string;
  gameUpdate?: string;
  openedAt: string;
}
function rootKey(root: string): string {
  return path.resolve(root).toLowerCase();
}
/** Optional native-only cache. Loss or corruption never changes project state. */
export class RecentProjects {
  private directory: string;
  constructor(directory: string) {
    this.directory = directory;
  }
  async list(): Promise<RecentProject[]> {
    try {
      const files = new SecureFiles(this.directory);
      await files.verifyRoot();
      const bytes = await files.read('selector-recent-projects-v1.json');
      if (!bytes) return [];
      const parsed = JSON.parse(bytes.toString()) as {
        schemaVersion: number;
        projects: RecentProject[];
      };
      if (parsed.schemaVersion !== 1 || !Array.isArray(parsed.projects))
        return [];
      const seenRoots = new Set<string>();
      return parsed.projects
        .filter(
          (project) =>
            /^[a-f0-9-]{36}$/.test(project.projectId) &&
            typeof project.projectRoot === 'string' &&
            typeof project.sourceDirectoryName === 'string' &&
            (project.sourceRoot === undefined ||
              typeof project.sourceRoot === 'string') &&
            (project.gameName === undefined ||
              (typeof project.gameName === 'string' &&
                project.gameName === project.gameName.trim() &&
                project.gameName.length > 0 &&
                !/[\u0000-\u001f\u007f]/.test(project.gameName) &&
                project.gameName.length <= 80)) &&
            (project.gameUpdate === undefined ||
              isGameUpdate(project.gameUpdate)) &&
            Number.isFinite(Date.parse(project.openedAt)),
        )
        .sort((a, b) => Date.parse(b.openedAt) - Date.parse(a.openedAt))
        .filter((project) => {
          const key = rootKey(project.projectRoot);
          if (seenRoots.has(key)) return false;
          seenRoots.add(key);
          return true;
        })
        .slice(0, 10);
    } catch {
      return [];
    }
  }
  async remember(project: RecentProject): Promise<void> {
    const existing = await this.list();
    await this.save(
      [
        project,
        ...existing.filter(
          (entry) =>
            entry.projectId !== project.projectId &&
            rootKey(entry.projectRoot) !== rootKey(project.projectRoot),
        ),
      ].slice(0, 10),
    );
  }
  /** Called only after explicit confirmation and a fresh missing-root check. */
  async forgetRoot(projectRoot: string): Promise<void> {
    await this.save(
      (await this.list()).filter(
        (entry) => rootKey(entry.projectRoot) !== rootKey(projectRoot),
      ),
    );
  }
  private async save(projects: RecentProject[]): Promise<void> {
    const files = new SecureFiles(await ensureDirectory(this.directory));
    await files.verifyRoot();
    await files.replace(
      'selector-recent-projects-v1.json',
      stableStringify({
        schemaVersion: 1,
        projects,
      }),
    );
  }
}
