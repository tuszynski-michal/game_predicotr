import readline from 'node:readline';
const mode = process.argv[2];
readline.createInterface({ input: process.stdin }).on('line', (line) => {
  const request = JSON.parse(line);
  if (mode === 'crash') process.exit(17);
  if (mode === 'hang') return;
  if (mode === 'invalid-json') return process.stdout.write('{bad}\n');
  if (mode === 'oversize') return process.stdout.write('x'.repeat(20000));
  if (mode === 'stderr') return process.stderr.write('x'.repeat(20000));
  const result =
    request.op === 'driveInfo'
      ? { type: 3, ready: true }
      : request.op === 'reparseScan'
        ? { clean: true }
        : { identity: mode === 'split' ? 'zażółć🙂' : String(request.pid) };
  if (mode === 'wrong-type') result.identity = false;
  const response =
    JSON.stringify({
      version: 1,
      id: mode === 'wrong-id' ? 'foreign' : request.id,
      ok: true,
      result,
    }) + '\n';
  if (mode === 'split') {
    const bytes = Buffer.from(response);
    const offset = bytes.indexOf(Buffer.from('🙂')) + 1;
    process.stdout.write(bytes.subarray(0, offset));
    setTimeout(() => process.stdout.write(bytes.subarray(offset)), 5);
  } else process.stdout.write(response);
});
