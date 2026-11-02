import { existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

const output = 'src/app/core/api/schema.d.ts';
const candidates = [
  process.env.OPENAPI_URL,
  'http://localhost:8000/openapi.json',
  'http://localhost:8000/v1/openapi.json',
].filter(Boolean);

const binary = join(
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'openapi-typescript.cmd' : 'openapi-typescript',
);

if (!existsSync(binary)) {
  console.error('openapi-typescript is not installed. Run npm install first.');
  process.exit(1);
}

mkdirSync('src/app/core/api', { recursive: true });

for (const url of candidates) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(3000) });
    if (!response.ok) {
      console.warn(`Skipping ${url}: HTTP ${response.status}`);
      continue;
    }
    const result = spawnSync(binary, [url, '-o', output], { stdio: 'inherit' });
    if (result.status === 0) {
      console.log(`OpenAPI types generated from ${url}`);
      process.exit(0);
    }
  } catch (error) {
    console.warn(`Skipping ${url}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

console.error(
  'Could not generate the API client. Start the API or set OPENAPI_URL to a reachable schema.',
);
process.exit(1);
