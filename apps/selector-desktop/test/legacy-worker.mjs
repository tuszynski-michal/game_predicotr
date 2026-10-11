import { ProjectStore } from '../src/project/project-store.ts';
import { inspectLegacy } from '../src/legacy-adoption/legacy-preview.ts';
const [mode, inputJson, oldOutput, phase] = process.argv.slice(2);
const input = JSON.parse(inputJson);
if (mode === 'crash') {
  const proof = await inspectLegacy(input.sourceRoot, oldOutput);
  await ProjectStore.createFromSelection(
    input,
    {
      checkpoint(point) {
        if (point === phase) process.exit(73);
      },
    },
    proof.seed,
    oldOutput,
  );
  process.exit(74);
} else if (mode === 'recover') {
  const store = await ProjectStore.open(input.projectRoot);
  if (store.getIssue()) throw new Error(JSON.stringify(store.getIssue()));
  process.stdout.write(JSON.stringify(store.snapshot()));
  await store.close();
} else throw new Error('unknown fixture mode');
