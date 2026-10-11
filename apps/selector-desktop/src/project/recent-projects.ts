import {
  ensureDirectory,
  SecureFiles,
  stableStringify,
} from '../filesystem/secure-files.ts';

export interface RecentProject {
  projectId: string;
  projectRoot: string;
  sourceDirectoryName: string;
  openedAt: string;
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
      return parsed.projects
        .filter(
          (project) =>
            /^[a-f0-9-]{36}$/.test(project.projectId) &&
            typeof project.projectRoot === 'string' &&
            typeof project.sourceDirectoryName === 'string' &&
            Number.isFinite(Date.parse(project.openedAt)),
        )
        .slice(0, 10);
    } catch {
      return [];
    }
  }
  async remember(project: RecentProject): Promise<void> {
    const existing = await this.list();
    const files = new SecureFiles(await ensureDirectory(this.directory));
    await files.verifyRoot();
    await files.replace(
      'selector-recent-projects-v1.json',
      stableStringify({
        schemaVersion: 1,
        projects: [
          project,
          ...existing.filter((entry) => entry.projectId !== project.projectId),
        ].slice(0, 10),
      }),
    );
  }
}
