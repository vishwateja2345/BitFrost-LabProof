// Container-only fixed operation mapping. No shell, paths, or flags from requests.
import {spawn} from 'node:child_process';
import {pathToFileURL} from 'node:url';

export function parseArgs(args) {
  if (!Array.isArray(args) || args.length !== 2 || args.some(a => typeof a !== 'string') ||
      args[0] !== 'typescript-node-test' || !['alpha', 'beta', 'gamma', 'delta'].includes(args[1])) {
    throw new Error('Expected declared operation and opaque variant');
  }
  return {operation: args[0], variant: args[1]};
}

export async function main(args) {
  let request;
  try { request = parseArgs(args); }
  catch {
    console.log(JSON.stringify({schema_version: 'worker-observation-1', status: 'invalid-request'}));
    return 2;
  }
  const result = {
    schema_version: 'worker-observation-1', operation_id: request.operation,
    variant: request.variant, tool: 'node:test', tool_version: process.versions.node,
    status: 'tool-error', exit_code: 1, timed_out: false, truncated: false,
    stdout: '', stderr: '',
  };
  // Preinstalled Node 24+ with native erasable-TypeScript support, NOT tsc.
  const child = spawn(process.execPath, ['--test', '--test-concurrency=1', '--test-reporter=tap', '/worker/observe.test.mjs'], {
    shell: false, cwd: '/tmp', stdio: ['ignore', 'pipe', 'pipe'],
    env: {LANG: 'C', HOME: '/tmp', TMPDIR: '/tmp', LABPROOF_VARIANT: request.variant},
  });
  const chunks = {stdout: [], stderr: []};
  let total = 0;
  const timer = setTimeout(() => { result.timed_out = true; child.kill('SIGKILL'); }, 5000);
  for (const name of ['stdout', 'stderr']) {
    child[name].on('data', chunk => {
      const remaining = Math.max(0, 32768 - total);
      chunks[name].push(chunk.subarray(0, remaining));
      total += chunk.length;
      if (total > 32768) { result.truncated = true; child.kill('SIGKILL'); }
    });
  }
  await new Promise(resolve => {
    child.on('error', () => { result.diagnostic = 'tool-start-failed'; });
    child.on('close', code => {
      clearTimeout(timer);
      result.exit_code = code;
      result.status = result.timed_out ? 'timeout' : code === 0 && !result.truncated ? 'completed' : 'tool-error';
      resolve();
    });
  });
  for (const name of ['stdout', 'stderr']) result[name] = Buffer.concat(chunks[name]).toString('utf8');
  console.log(JSON.stringify(result));
  return result.status === 'completed' ? 0 : 1;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = await main(process.argv.slice(2));
}
