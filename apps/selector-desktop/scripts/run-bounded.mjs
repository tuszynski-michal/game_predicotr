import { spawn, spawnSync } from 'node:child_process';
import path from 'node:path';
import { existsSync } from 'node:fs';
const [seconds, executable, ...args] = process.argv.slice(2);
if (!Number.isFinite(Number(seconds)) || Number(seconds) <= 0 || !executable)
  throw new Error('Usage: run-bounded.mjs <seconds> <executable> [...args]');
let command = executable;
let commandArgs = args;
if (/^npm(?:\.cmd)?$/i.test(executable)) {
  const cli =
    process.env.npm_execpath ??
    path.join(
      path.dirname(process.execPath),
      'node_modules/npm/bin/npm-cli.js',
    );
  if (!existsSync(cli))
    throw new Error(
      'Cannot locate npm CLI beside Node.js. Pass node.exe and the npm-cli.js path explicitly.',
    );
  command = process.execPath;
  commandArgs = [cli, ...args];
}
const child = spawn(command, commandArgs, {
  stdio: 'inherit',
  windowsHide: true,
});
const timer = setTimeout(
  () => {
    console.error(`Command exceeded ${seconds} seconds.`);
    if (process.platform === 'win32')
      spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], {
        timeout: 5000,
        stdio: 'ignore',
        windowsHide: true,
      });
    else child.kill('SIGKILL');
    process.exitCode = 124;
  },
  Number(seconds) * 1000,
);
child.on('error', (error) => {
  clearTimeout(timer);
  console.error(error.message);
  process.exitCode = 1;
});
child.on('close', (code) => {
  clearTimeout(timer);
  process.exitCode ??= code ?? 1;
});
