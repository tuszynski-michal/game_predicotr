import { createOwnedSmoke } from '../../scripts/release-support.mjs';
const [fixture, tempRoot, userData, diagnosticsRoot] = process.argv.slice(2);
const smoke = createOwnedSmoke({
  name: 'child-fault',
  fixture,
  tempRoot,
  userData: [userData],
  diagnosticsRoot,
});
try {
  await smoke.run(() => new Promise(() => {}));
  smoke.result.succeeded = true;
} catch (error) {
  smoke.result.error = error;
} finally {
  await smoke.finish();
}
