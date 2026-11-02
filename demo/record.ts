/**
 * Grabación automatizada de la demo de Croupier.
 *
 * - Chromium + Playwright con recordVideo a 1920x1080 / 30 fps.
 * - Cursor y efecto de clic inyectados en todas las páginas.
 * - Escritura de preguntas a ~45 ms por carácter.
 * - Esperas por selectores (data-testid). La única espera por tiempo es el
 *   relleno necesario para que cada segmento dure al menos audio + 0.6 s.
 *
 * Uso:
 *   node --experimental-strip-types --no-warnings record.ts
 *   node --experimental-strip-types --no-warnings record.ts --dry-run
 */

import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { basename, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

import { chromium, type Browser, type BrowserContext, type Page } from '@playwright/test';
import { parse as parseYaml } from 'yaml';

interface ScriptSegment {
  id: string;
  action: string;
  narration: string;
  question: string | null;
  audio_file: string | null;
}

interface TimedSegment extends ScriptSegment {
  audioDuration: number;
  minDuration: number;
}

interface RecordedSegment {
  index: number;
  id: string;
  action: string;
  narration: string;
  question: string | null;
  start: number;
  duration: number;
  audioDuration: number;
  minDuration: number;
}

interface DocumentRecord {
  id: string;
  filename: string;
  jobId?: string | null;
  chunkCount?: number | null;
  pageCount?: number | null;
}

const DEMO_DIR = resolve(
  process.env.DEMO_DIR ??
    (basename(process.cwd()) === 'demo' ? process.cwd() : join(process.cwd(), 'demo')),
);
const OUT_DIR = join(DEMO_DIR, 'out');
const VIDEO_DIR = join(OUT_DIR, 'video');
const SCRIPT_YAML = join(DEMO_DIR, 'script.yaml');
const DURATIONS_JSON = join(OUT_DIR, 'durations.json');
const TIMELINE_JSON = join(OUT_DIR, 'timeline.json');
const DRY_TIMELINE_JSON = join(OUT_DIR, 'timeline.dry.json');

const APP_URL = (process.env.APP_URL ?? 'http://localhost:4200').replace(/\/+$/, '');
const DEMO_PDF = process.env.DEMO_PDF ?? join(process.env.HOME ?? '', 'Downloads', 'Manual de usuario app.pdf');
const DRY_RUN = process.argv.includes('--dry-run');
const HEADLESS = process.env.HEADLESS !== 'false';
const ARCHITECTURE_URL = pathToFileURL(join(DEMO_DIR, 'assets', 'architecture.html')).href;

const VIEWPORT = { width: 1920, height: 1080 };
const TYPE_DELAY_MS = 45;
const SEGMENT_PADDING_MS = 600;

let mousePosition = { x: VIEWPORT.width / 2, y: VIEWPORT.height / 2 };
let apiBase = '';

function log(message: string): void {
  console.log(`[record] ${message}`);
}

function fail(message: string, error?: unknown): never {
  const detail = error instanceof Error ? `\n${error.stack ?? error.message}` : '';
  console.error(`\n[record] ERROR: ${message}${detail}\n`);
  process.exit(1);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, ms));
}

function readJson<T>(path: string): T | null {
  if (!existsSync(path)) {
    return null;
  }
  try {
    return JSON.parse(readFileSync(path, 'utf8')) as T;
  } catch {
    return null;
  }
}

function loadSegments(): TimedSegment[] {
  if (!existsSync(SCRIPT_YAML)) {
    fail(`No existe ${SCRIPT_YAML}. Ejecuta el comando desde la raíz del repositorio.`);
  }
  const parsed = parseYaml(readFileSync(SCRIPT_YAML, 'utf8')) as {
    segments?: Array<Record<string, unknown>>;
  };
  const entries = parsed?.segments;
  if (!Array.isArray(entries) || entries.length === 0) {
    fail('script.yaml no contiene `segments`.');
  }

  const durationsFile = readJson<{
    byId?: Record<string, number>;
    segments?: Array<{ id: string; duration: number }>;
  }>(DURATIONS_JSON);
  const byId: Record<string, number> = durationsFile?.byId ?? {};
  if (!durationsFile?.byId && Array.isArray(durationsFile?.segments)) {
    for (const item of durationsFile.segments) {
      byId[item.id] = item.duration;
    }
  }

  return entries.map((entry) => {
    const id = String(entry.id ?? '').trim();
    const action = String(entry.action ?? '').trim();
    const narration = String(entry.narration ?? '').replace(/\s+/g, ' ').trim();
    if (!id || !action || !narration) {
      fail(`Segmento inválido en script.yaml: ${JSON.stringify(entry)}`);
    }
    const audioDuration = Number(byId[id] ?? 0);
    if (!DRY_RUN && (!Number.isFinite(audioDuration) || audioDuration <= 0)) {
      fail(
        `Falta la duración de \`${id}\` en ${DURATIONS_JSON}. ` +
          'Ejecuta `make demo-tts` (o `make demo`) para generar la narración.',
      );
    }
    return {
      id,
      action,
      narration,
      question: entry.question ? String(entry.question).replace(/\s+/g, ' ').trim() : null,
      audio_file: entry.audio_file ? String(entry.audio_file) : null,
      audioDuration: DRY_RUN ? audioDuration || 1.2 : audioDuration,
      minDuration: DRY_RUN
        ? 0.4
        : Number((audioDuration + SEGMENT_PADDING_MS / 1000).toFixed(3)),
    };
  });
}

async function probeJson(url: string, timeoutMs = 4000): Promise<boolean> {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
    return response.ok;
  } catch {
    return false;
  }
}

async function resolveApiBase(): Promise<string> {
  const candidates = [
    process.env.API_URL,
    `${APP_URL}/api/v1`,
    'http://localhost:8000/v1',
    'http://localhost:8000',
    'http://localhost:8000/api/v1',
  ].filter((candidate): candidate is string => Boolean(candidate));

  for (const candidate of candidates) {
    const base = candidate.replace(/\/+$/, '');
    if (await probeJson(`${base}/health`)) {
      return base;
    }
  }
  fail(
    'La API no responde. Levanta el stack completo con:\n' +
      '  docker compose up -d --build\n' +
      `Comprobado en: ${candidates.join(', ')}`,
  );
  throw new Error('unreachable');
}

async function assertServices(): Promise<void> {
  if (!(await probeJson(`${APP_URL}/`))) {
    fail(
      `El frontend no responde en ${APP_URL}.\n` +
        'Levanta los servicios con:\n' +
        '  docker compose up -d --build\n' +
        'Y espera a que `docker compose ps` muestre api, worker, redis, qdrant y web en marcha.',
    );
  }
  apiBase = await resolveApiBase();
  log(`frontend=${APP_URL} api=${apiBase}`);
}

async function api<T>(path: string, init?: RequestInit): Promise<T | null> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...(init?.headers ?? {}) },
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) {
    throw new Error(`API ${init?.method ?? 'GET'} ${path} → HTTP ${response.status}`);
  }
  if (response.status === 204) {
    return null;
  }
  return (await response.json()) as T;
}

async function listDocuments(): Promise<DocumentRecord[]> {
  return (await api<DocumentRecord[]>('/documents')) ?? [];
}

async function findDemoDocument(): Promise<DocumentRecord | null> {
  const filename = basename(DEMO_PDF);
  const documents = await listDocuments();
  return documents.find((document) => document.filename === filename) ?? null;
}

async function cleanupDemoDocument(): Promise<void> {
  const filename = basename(DEMO_PDF);
  const documents = await listDocuments();
  const matches = documents.filter((document) => document.filename === filename);
  if (matches.length === 0) {
    log(`biblioteca limpia para «${filename}»`);
    return;
  }
  for (const document of matches) {
    log(`eliminando documento previo ${document.id}…`);
    try {
      await api(`/documents/${document.id}`, { method: 'DELETE' });
    } catch (error) {
      fail(
        `No se pudo eliminar el documento previo ${document.id}. ` +
          'Comprueba que el worker y Qdrant estén sanos (`docker compose ps`).',
        error,
      );
    }
  }
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const remaining = (await listDocuments()).filter((document) => document.filename === filename);
    if (remaining.length === 0) {
      log(`biblioteca limpia para «${filename}»`);
      return;
    }
    await sleep(500);
  }
  fail(`El documento «${filename}» sigue apareciendo después de eliminarlo.`);
}

async function waitForDemoDocument(timeoutMs = 45000): Promise<DocumentRecord> {
  const filename = basename(DEMO_PDF);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const document = (await listDocuments()).find((item) => item.filename === filename);
    if (document) {
      return document;
    }
    await sleep(400);
  }
  fail(`La API no registró el documento «${filename}» después de subirlo.`);
  throw new Error('unreachable');
}

function tid(page: Page, id: string) {
  return page.locator(`[data-testid="${id}"]`);
}

async function moveMouse(page: Page, x: number, y: number): Promise<void> {
  const targetX = Math.max(2, Math.min(VIEWPORT.width - 2, x));
  const targetY = Math.max(2, Math.min(VIEWPORT.height - 2, y));
  const from = mousePosition;
  const dx = targetX - from.x;
  const dy = targetY - from.y;
  const distance = Math.hypot(dx, dy);
  const steps = Math.max(8, Math.min(40, Math.round(distance / 22)));
  for (let step = 1; step <= steps; step += 1) {
    const t = step / steps;
    const eased = t * t * (3 - 2 * t);
    const wobble = Math.sin(t * Math.PI) * Math.min(16, distance * 0.035);
    const normalX = distance > 0 ? -dy / distance : 0;
    const normalY = distance > 0 ? dx / distance : 0;
    await page.mouse.move(
      Math.round(from.x + dx * eased + normalX * wobble),
      Math.round(from.y + dy * eased + normalY * wobble),
    );
  }
  mousePosition = { x: targetX, y: targetY };
}

async function clickTestId(page: Page, testId: string): Promise<void> {
  const locator = tid(page, testId).first();
  await locator.waitFor({ state: 'visible', timeout: 30000 });
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) {
    throw new Error(`No pude calcular la posición de [data-testid="${testId}"]`);
  }
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await moveMouse(page, x, y);
  await page.mouse.down();
  await sleep(90);
  await page.mouse.up();
  await sleep(140);
}

async function moveToTestId(page: Page, testId: string, offsetX = 0, offsetY = 0): Promise<void> {
  const locator = tid(page, testId).first();
  await locator.waitFor({ state: 'visible', timeout: 30000 });
  await locator.scrollIntoViewIfNeeded();
  const box = await locator.boundingBox();
  if (!box) {
    return;
  }
  await moveMouse(page, box.x + box.width / 2 + offsetX, box.y + box.height / 2 + offsetY);
}

async function waitUntil(page: Page, deadline: number): Promise<void> {
  const remaining = Math.max(0, deadline - Date.now());
  if (remaining === 0) {
    return;
  }
  await page.waitForFunction(
    (target) => Date.now() >= target,
    Date.now() + remaining,
    { timeout: remaining + 5000 },
  );
}

async function padToMinimum(page: Page, startedAt: number, minDurationSeconds: number): Promise<void> {
  const deadline = startedAt + Math.round(minDurationSeconds * 1000);
  if (DRY_RUN) {
    return;
  }
  await waitUntil(page, deadline);
}

async function countAssistantMessages(page: Page): Promise<number> {
  return tid(page, 'assistant-message').count();
}

async function waitForAnswer(page: Page, previousCount: number, timeoutMs = 240000): Promise<void> {
  await page.waitForFunction(
    (previous) => {
      const messages = document.querySelectorAll('[data-testid="assistant-message"]');
      const thinking = document.querySelector('app-thinking-bubble');
      const log = document.querySelector('[role="log"]');
      return (
        messages.length > previous &&
        !thinking &&
        log?.getAttribute('aria-busy') === 'false'
      );
    },
    previousCount,
    { timeout: timeoutMs },
  );
}

async function alreadyAnswered(page: Page, question: string): Promise<boolean> {
  const wanted = question.replace(/\s+/g, ' ').trim();
  return page.evaluate((text) => {
    const nodes = Array.from(
      document.querySelectorAll(
        '[data-testid="user-message"], [data-testid="assistant-message"]',
      ),
    );
    let lastUser = -1;
    nodes.forEach((node, index) => {
      if (node.getAttribute('data-testid') === 'user-message') {
        lastUser = index;
      }
    });
    if (lastUser < 0) {
      return false;
    }
    const content = (nodes[lastUser].textContent ?? '').replace(/\s+/g, ' ').trim();
    const hasAssistantAfter = nodes
      .slice(lastUser + 1)
      .some((node) => node.getAttribute('data-testid') === 'assistant-message');
    return content === text && hasAssistantAfter;
  }, wanted);
}

async function typeQuestion(page: Page, question: string): Promise<void> {
  const input = tid(page, 'chat-input');
  await input.waitFor({ state: 'visible', timeout: 30000 });
  await input.click();
  await input.fill('');
  await page.keyboard.type(question, { delay: TYPE_DELAY_MS });
  await page.waitForFunction(() => {
    const button = document.querySelector('[data-testid="chat-send"]');
    return button instanceof HTMLButtonElement && !button.disabled;
  }, null, { timeout: 15000 });
  await sleep(180);
}

async function askQuestion(page: Page, question: string): Promise<void> {
  if (await alreadyAnswered(page, question)) {
    log(`la última respuesta ya corresponde a «${question.slice(0, 48)}…»; no la repito`);
    return;
  }
  const previous = await countAssistantMessages(page);
  await typeQuestion(page, question);
  await clickTestId(page, 'chat-send');
  await waitForAnswer(page, previous);
  await sleep(250);
}

async function ensureChatWithDocument(page: Page, documentId: string): Promise<void> {
  if (!page.url().includes('/chat')) {
    await page.goto(`${APP_URL}/chat`, { waitUntil: 'domcontentloaded' });
  }
  await tid(page, 'chat-page').waitFor({ state: 'visible', timeout: 30000 });
  const select = tid(page, 'chat-document-select');
  await select.waitFor({ state: 'visible', timeout: 30000 });
  await page.waitForFunction(
    ({ id }) => {
      const element = document.querySelector('[data-testid="chat-document-select"]');
      return (
        element instanceof HTMLSelectElement &&
        Array.from(element.options).some((option) => option.value === id)
      );
    },
    { id: documentId },
    { timeout: 30000 },
  );
  await select.selectOption(documentId);
  await page.waitForFunction(
    ({ id }) => {
      const element = document.querySelector('[data-testid="chat-document-select"]');
      return element instanceof HTMLSelectElement && element.value === id;
    },
    { id: documentId },
    { timeout: 15000 },
  );
}

async function openChatFromDocument(page: Page, documentId: string, filename: string): Promise<void> {
  await page.goto(`${APP_URL}/documents`, { waitUntil: 'domcontentloaded' });
  await tid(page, 'documents-page').waitFor({ state: 'visible', timeout: 30000 });
  const card = page
    .locator('[data-testid="document-card"]')
    .filter({ hasText: filename })
    .first();
  await card.waitFor({ state: 'visible', timeout: 30000 });
  await card.scrollIntoViewIfNeeded();
  const askButton = card.locator('[data-testid="document-ask"]').first();
  const box = await askButton.boundingBox();
  if (box) {
    await moveMouse(page, box.x + box.width / 2, box.y + box.height / 2);
  }
  await askButton.click();
  await tid(page, 'chat-page').waitFor({ state: 'visible', timeout: 30000 });
  await ensureChatWithDocument(page, documentId);
}

async function assertNotMockMode(page: Page): Promise<void> {
  if ((await tid(page, 'mock-badge').count()) > 0) {
    fail(
      'El frontend está en modo mock (badge «Demo local»). ' +
        'La demo necesita el build de producción conectado a la API.\n' +
        'Ejecuta: docker compose up -d --build web',
    );
  }
}

async function performArchitecture(page: Page): Promise<void> {
  if (!page.url().startsWith('file://')) {
    await page.goto(ARCHITECTURE_URL, { waitUntil: 'load' });
  }
  await tid(page, 'architecture-slide').waitFor({ state: 'visible', timeout: 30000 });
  await page.evaluate(() => document.fonts?.ready);
  await moveMouse(page, 1500, 330);
  await sleep(400);
  await moveMouse(page, 520, 700);
  await sleep(350);
  await moveMouse(page, 970, 760);
  await sleep(350);
  await moveMouse(page, 1440, 700);
  await sleep(350);
}

async function performUploadStart(page: Page, filename: string): Promise<void> {
  await page.goto(`${APP_URL}/documents`, { waitUntil: 'domcontentloaded' });
  await tid(page, 'documents-page').waitFor({ state: 'visible', timeout: 30000 });
  await assertNotMockMode(page);

  const existing = await findDemoDocument();
  if (existing && (existing.chunkCount ?? 0) > 0) {
    log('el documento de demo ya estaba indexado; no vuelvo a subirlo');
    return;
  }

  await tid(page, 'documents-file-input').waitFor({ state: 'attached', timeout: 30000 });
  const chooserPromise = page.waitForEvent('filechooser', { timeout: 30000 });
  await clickTestId(page, 'documents-select-file');
  const chooser = await chooserPromise;
  await chooser.setFiles(DEMO_PDF);

  await tid(page, 'job-timeline').waitFor({ state: 'visible', timeout: 45000 });
  await page.waitForFunction(
    () => {
      const element = document.querySelector('[data-testid="job-timeline"]');
      const status = element?.getAttribute('data-job-status');
      return status === 'PROCESSING' || status === 'COMPLETED';
    },
    null,
    { timeout: 45000 },
  );
  await moveToTestId(page, 'job-progress');
  await sleep(300);
  await moveToTestId(page, 'job-stage');
  log(`subida lanzada para «${filename}»`);
}

async function performUploadStage(page: Page, stageKey: string): Promise<void> {
  await tid(page, 'job-timeline').waitFor({ state: 'visible', timeout: 45000 });
  const stage = page
    .locator(`[data-testid="job-stage"][data-stage-key="${stageKey}"]`)
    .first();
  await stage.waitFor({ state: 'visible', timeout: 30000 });
  await page.waitForFunction(
    ({ key }) => {
      const element = document.querySelector(
        `[data-testid="job-stage"][data-stage-key="${key}"]`,
      );
      const state = element?.getAttribute('data-stage-state');
      return state === 'active' || state === 'done';
    },
    { key: stageKey },
    { timeout: 300000 },
  );
  await stage.scrollIntoViewIfNeeded();
  const box = await stage.boundingBox();
  if (box) {
    await moveMouse(page, box.x + 40, box.y + box.height / 2);
    await moveMouse(page, box.x + box.width - 60, box.y + box.height / 2);
  }
  await moveToTestId(page, 'job-progress');
  await sleep(250);
}

async function performUploadComplete(page: Page, filename: string): Promise<void> {
  await tid(page, 'job-timeline').waitFor({ state: 'visible', timeout: 45000 });
  await page.waitForFunction(
    () => {
      const element = document.querySelector('[data-testid="job-timeline"]');
      return element?.getAttribute('data-job-status') === 'COMPLETED';
    },
    null,
    { timeout: 300000 },
  );
  const card = page
    .locator('[data-testid="document-card"]')
    .filter({ hasText: filename })
    .first();
  await card.waitFor({ state: 'visible', timeout: 45000 });
  await card.scrollIntoViewIfNeeded();
  await page.waitForFunction(
    ({ name }) => {
      const cards = Array.from(document.querySelectorAll('[data-testid="document-card"]'));
      const target = cards.find((element) => element.getAttribute('data-filename') === name);
      const status = target
        ?.querySelector('[data-testid="document-status"]')
        ?.textContent?.trim();
      return /Indexado/i.test(status ?? '');
    },
    { name: filename },
    { timeout: 45000 },
  );
  const box = await card.boundingBox();
  if (box) {
    await moveMouse(page, box.x + box.width / 2, box.y + 90);
    await sleep(300);
    await moveMouse(page, box.x + box.width / 2, box.y + box.height - 50);
  }
}

async function observeFigureAnswer(page: Page): Promise<void> {
  const figure = tid(page, 'figure-viewer').first();
  await figure.waitFor({ state: 'visible', timeout: 60000 });
  const image = figure.locator('img').first();
  await page.waitForFunction(
    () => {
      const image = document.querySelector('[data-testid="figure-viewer"] img');
      return image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0;
    },
    null,
    { timeout: 30000 },
  );
  await image.scrollIntoViewIfNeeded();
  const box = await image.boundingBox();
  if (box) {
    await moveMouse(page, box.x + box.width / 2, box.y + box.height / 2);
  }
  await sleep(300);
}

async function performOpenFigureAnswer(page: Page, question: string): Promise<void> {
  await askQuestion(page, question);
  const figure = tid(page, 'figure-viewer').first();
  await figure.waitFor({ state: 'visible', timeout: 60000 });
  const image = figure.locator('img').first();
  await page.waitForFunction(
    () => {
      const image = document.querySelector('[data-testid="figure-viewer"] img');
      return image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0;
    },
    null,
    { timeout: 30000 },
  );
  await image.scrollIntoViewIfNeeded();
  const box = await image.boundingBox();
  if (box) {
    await moveMouse(page, box.x + box.width / 2, box.y + box.height / 2);
  }
  await sleep(300);
}

async function performWarmupAnswer(page: Page): Promise<void> {
  const source = tid(page, 'source-chip').last();
  await source.waitFor({ state: 'visible', timeout: 60000 });
  await source.scrollIntoViewIfNeeded();
  const box = await source.boundingBox();
  if (box) {
    await moveMouse(page, box.x + box.width / 2, box.y + box.height / 2);
  }
  await sleep(300);
}

async function closeFigureModalIfOpen(page: Page): Promise<void> {
  const modal = tid(page, 'figure-page-modal');
  if ((await modal.count()) > 0 && (await modal.first().isVisible())) {
    await clickTestId(page, 'figure-page-close');
    await modal.first().waitFor({ state: 'hidden', timeout: 15000 });
  }
}

async function performShowPage(page: Page): Promise<void> {
  await closeFigureModalIfOpen(page);
  await clickTestId(page, 'figure-page-link');
  await tid(page, 'figure-page-modal').waitFor({ state: 'visible', timeout: 30000 });
  await tid(page, 'figure-page-image').waitFor({ state: 'visible', timeout: 30000 });
  await page.waitForFunction(
    () => {
      const image = document.querySelector('[data-testid="figure-page-image"]');
      return image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0;
    },
    null,
    { timeout: 30000 },
  );
  await moveMouse(page, VIEWPORT.width / 2, VIEWPORT.height / 2);
  await sleep(500);
}

async function performShowPageHold(page: Page): Promise<void> {
  const modal = tid(page, 'figure-page-modal');
  await modal.waitFor({ state: 'visible', timeout: 30000 });
  await moveMouse(page, VIEWPORT.width / 2 + 120, VIEWPORT.height / 2 - 40);
  await sleep(350);
  await page.mouse.wheel(0, 260);
  await sleep(450);
  await page.mouse.wheel(0, -260);
  await sleep(350);
  await moveToTestId(page, 'figure-page-close');
  await clickTestId(page, 'figure-page-close');
  await modal.waitFor({ state: 'hidden', timeout: 15000 });
}

async function performUnknown(page: Page, question: string): Promise<void> {
  await closeFigureModalIfOpen(page);
  await askQuestion(page, question);
  const panel = tid(page, 'insufficient-answer').last();
  await panel.waitFor({ state: 'visible', timeout: 60000 });
  await panel.scrollIntoViewIfNeeded();
  const box = await panel.boundingBox();
  if (box) {
    await moveMouse(page, box.x + box.width / 2, box.y + 70);
  }
  await sleep(300);
}

async function performUnknownAnswer(page: Page): Promise<void> {
  const panel = tid(page, 'insufficient-answer').last();
  await panel.waitFor({ state: 'visible', timeout: 30000 });
  await panel.scrollIntoViewIfNeeded();
  const box = await panel.boundingBox();
  if (box) {
    await moveMouse(page, box.x + box.width / 2, box.y + box.height / 2);
    await sleep(350);
    await moveMouse(page, box.x + 90, box.y + box.height - 30);
  }
  await sleep(250);
}

async function enableAuditor(page: Page): Promise<void> {
  const toggle = tid(page, 'auditor-toggle');
  await toggle.waitFor({ state: 'visible', timeout: 30000 });
  const pressed = await toggle.getAttribute('aria-pressed');
  if (pressed !== 'true') {
    await clickTestId(page, 'auditor-toggle');
  }
  await page.waitForFunction(
    () =>
      document.querySelector('[data-testid="auditor-toggle"]')?.getAttribute('aria-pressed') ===
      'true',
    null,
    { timeout: 15000 },
  );
}

async function performAuditorEnable(page: Page, question: string): Promise<void> {
  if ((await tid(page, 'retrieval-inspector').count()) > 0) {
    await clickTestId(page, 'inspector-close');
    await tid(page, 'retrieval-inspector').waitFor({ state: 'hidden', timeout: 15000 });
  }
  await enableAuditor(page);
  await askQuestion(page, question);
  await moveToTestId(page, 'assistant-message');
  await sleep(250);
}

async function performAuditorTraces(page: Page): Promise<void> {
  await clickTestId(page, 'inspector-open');
  await tid(page, 'retrieval-inspector').waitFor({ state: 'visible', timeout: 30000 });
  await page.waitForFunction(
    () => document.querySelectorAll('[data-testid="retrieval-hit"]').length > 0,
    null,
    { timeout: 60000 },
  );
  const hits = page.locator('[data-testid="retrieval-hit"]');
  const lastHit = hits.last();
  await lastHit.scrollIntoViewIfNeeded();
  const box = await lastHit.boundingBox();
  if (box) {
    await moveMouse(page, box.x + box.width * 0.55, box.y + 30);
    await sleep(300);
    await moveMouse(page, box.x + box.width * 0.75, box.y + box.height - 35);
  }
  await moveToTestId(page, 'inspector-best-score');
  await sleep(300);
}

async function performSegment(page: Page, segment: TimedSegment, docId: string): Promise<void> {
  switch (segment.action) {
    case 'intro':
    case 'outro':
      log(`${segment.id}: tarjeta generada por ffmpeg (no se graba navegador)`);
      return;
    case 'architecture':
      await performArchitecture(page);
      return;
    case 'upload':
      if (segment.id === 'upload-start') {
        await performUploadStart(page, basename(DEMO_PDF));
      } else if (segment.id === 'upload-parse') {
        await performUploadStage(page, 'parse');
      } else if (segment.id === 'upload-images') {
        await performUploadStage(page, 'images');
      } else if (segment.id === 'upload-chunk') {
        await performUploadStage(page, 'chunk');
      } else if (segment.id === 'upload-embed') {
        await performUploadStage(page, 'embed');
      } else if (segment.id === 'upload-index') {
        await performUploadComplete(page, basename(DEMO_PDF));
      } else {
        await performUploadStage(page, 'embed');
      }
      return;
    case 'ask_figure':
      if (!segment.question) {
        if (segment.id === 'warmup-answer') {
          await performWarmupAnswer(page);
        } else {
          await observeFigureAnswer(page);
        }
        return;
      }
      if (segment.id === 'warmup') {
        await openChatFromDocument(page, docId, basename(DEMO_PDF));
        await askQuestion(page, segment.question);
        return;
      }
      await performOpenFigureAnswer(page, segment.question);
      return;
    case 'show_page':
      if (segment.id === 'show-page') {
        await performShowPage(page);
      } else {
        await performShowPageHold(page);
      }
      return;
    case 'ask_unknown':
      if (segment.question) {
        await performUnknown(page, segment.question);
      } else {
        await performUnknownAnswer(page);
      }
      return;
    case 'auditor_mode':
      if (segment.id === 'auditor-enable') {
        await performAuditorEnable(page, segment.question ?? '');
      } else {
        await performAuditorTraces(page);
      }
      return;
    default:
      fail(`Acción no implementada: ${segment.action} (${segment.id})`);
  }
}

async function recover(page: Page, segment: TimedSegment, docId: string): Promise<void> {
  log(`recuperando la página antes de reintentar ${segment.id}…`);
  try {
    if (segment.action === 'upload') {
      await page.goto(`${APP_URL}/documents`, { waitUntil: 'domcontentloaded' });
      await tid(page, 'documents-page').waitFor({ state: 'visible', timeout: 30000 });
    } else if (segment.action === 'auditor_mode') {
      await page.goto(`${APP_URL}/chat`, { waitUntil: 'domcontentloaded' });
      await tid(page, 'chat-page').waitFor({ state: 'visible', timeout: 30000 });
      if (docId) {
        await ensureChatWithDocument(page, docId);
      }
    } else if (segment.action !== 'intro' && segment.action !== 'outro') {
      await page.goto(`${APP_URL}/chat`, { waitUntil: 'domcontentloaded' });
      await tid(page, 'chat-page').waitFor({ state: 'visible', timeout: 30000 });
      if (docId) {
        await ensureChatWithDocument(page, docId);
      }
    }
  } catch (error) {
    log(`la recuperación encontró un error adicional: ${(error as Error).message}`);
  }
}

async function installCursor(context: BrowserContext): Promise<void> {
  await context.addInitScript(() => {
    try {
      window.localStorage.setItem('croupier.theme', 'dark');
    } catch {
      // file:// y about:blank pueden no tener localStorage.
    }

    const install = () => {
      if (!document.documentElement || document.getElementById('__croupier_cursor')) {
        return;
      }
      const style = document.createElement('style');
      style.id = '__croupier_cursor_style';
      style.textContent = `
        html, body, * { cursor: none !important; }
        #__croupier_cursor {
          position: fixed; left: 0; top: 0; z-index: 2147483647;
          width: 34px; height: 34px; margin: -3px 0 0 -3px;
          pointer-events: none; transform: translate(960px, 540px);
          transition: transform 45ms linear;
          filter: drop-shadow(0 3px 6px rgba(0,0,0,.55));
        }
        #__croupier_cursor svg { display:block; width:34px; height:34px; }
        #__croupier_cursor.is-down { transform: translate(var(--x), var(--y)) scale(.88); }
        #__croupier_click {
          position: fixed; left: 0; top: 0; z-index: 2147483646;
          width: 42px; height: 42px; margin: -21px 0 0 -21px;
          border: 2px solid #d2ab63; border-radius: 999px;
          pointer-events: none; opacity: 0;
        }
        #__croupier_click.pulse {
          animation: __croupier_pulse 520ms ease-out forwards;
        }
        @keyframes __croupier_pulse {
          0% { opacity: .85; transform: scale(.35); }
          100% { opacity: 0; transform: scale(1.65); }
        }
      `;
      document.documentElement.appendChild(style);

      const cursor = document.createElement('div');
      cursor.id = '__croupier_cursor';
      cursor.innerHTML = `
        <svg viewBox="0 0 34 34" aria-hidden="true">
          <path d="M4 3 L4 26 L10.5 20.2 L14.4 29.5 L19.2 27.5 L15.2 18.3 L24 18.1 Z"
                fill="#f4efe6" stroke="#07130d" stroke-width="2.2" stroke-linejoin="round"/>
          <path d="M6.5 6.5 L6.5 21.2 L11 17.3 L15 26.4 L17.1 25.5 L13 16.3 L19 16.2 Z"
                fill="#d2ab63"/>
        </svg>
      `;
      document.documentElement.appendChild(cursor);

      const ring = document.createElement('span');
      ring.id = '__croupier_click';
      document.documentElement.appendChild(ring);

      let lastX = 960;
      let lastY = 540;
      const place = (x: number, y: number) => {
        lastX = x;
        lastY = y;
        cursor.style.setProperty('--x', `${x}px`);
        cursor.style.setProperty('--y', `${y}px`);
        cursor.style.transform = `translate(${x}px, ${y}px)`;
      };
      window.addEventListener(
        'mousemove',
        (event) => place(event.clientX, event.clientY),
        true,
      );
      window.addEventListener(
        'mousedown',
        () => {
          cursor.classList.add('is-down');
          ring.style.left = `${lastX}px`;
          ring.style.top = `${lastY}px`;
          ring.classList.remove('pulse');
          void ring.offsetWidth;
          ring.classList.add('pulse');
        },
        true,
      );
      window.addEventListener('mouseup', () => cursor.classList.remove('is-down'), true);
    };

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', install, { once: true });
    } else {
      install();
    }
  });
}

function findFfprobe(): string | null {
  const configured = process.env.FFPROBE;
  if (configured) {
    return configured;
  }
  try {
    execFileSync('ffprobe', ['-version'], { stdio: 'ignore' });
    return 'ffprobe';
  } catch {
    return null;
  }
}

function probeDuration(ffprobe: string | null, path: string): number | null {
  if (!ffprobe) {
    return null;
  }
  try {
    const output = execFileSync(
      ffprobe,
      [
        '-v',
        'error',
        '-show_entries',
        'format=duration',
        '-of',
        'default=noprint_wrappers=1:nokey=1',
        path,
      ],
      { encoding: 'utf8' },
    );
    const value = Number(output.trim());
    return Number.isFinite(value) && value > 0 ? Number(value.toFixed(3)) : null;
  } catch {
    return null;
  }
}

function writeTimeline(payload: Record<string, unknown>): void {
  mkdirSync(OUT_DIR, { recursive: true });
  writeFileSync(
    DRY_RUN ? DRY_TIMELINE_JSON : TIMELINE_JSON,
    `${JSON.stringify(payload, null, 2)}\n`,
    'utf8',
  );
}

async function main(): Promise<void> {
  if (!existsSync(DEMO_PDF)) {
    fail(
      `No existe el PDF de demo: ${DEMO_PDF}\n` +
        'Define DEMO_PDF con la ruta absoluta al manual, por ejemplo:\n' +
        '  DEMO_PDF="$HOME/Downloads/Manual de usuario app.pdf" make demo',
    );
  }
  if (!existsSync(SCRIPT_YAML)) {
    fail(`No existe ${SCRIPT_YAML}.`);
  }

  const segments = loadSegments();
  mkdirSync(OUT_DIR, { recursive: true });
  mkdirSync(VIDEO_DIR, { recursive: true });
  if (!DRY_RUN) {
    rmSync(VIDEO_DIR, { recursive: true, force: true });
    mkdirSync(VIDEO_DIR, { recursive: true });
  }

  await assertServices();
  await cleanupDemoDocument();

  log(
    DRY_RUN
      ? 'modo dry-run: se recorre el flujo sin grabar video'
      : 'iniciando Chromium con recordVideo 1920x1080…',
  );

  let browser: Browser | null = null;
  let context: BrowserContext | null = null;
  let page: Page | null = null;
  let video: ReturnType<Page['video']> = null;
  let recordingStartWall = 0;
  let contentStartWall = 0;
  let closeWall = 0;
  const recorded: RecordedSegment[] = [];
  let docId = '';

  try {
    browser = await chromium.launch({
      headless: HEADLESS,
      args: [
        '--force-device-scale-factor=1',
        '--force-color-profile=srgb',
        '--hide-scrollbars',
        '--disable-lcd-text',
      ],
    });
    // Playwright empieza a escribir el video al crear el contexto.
    recordingStartWall = Date.now();
    context = await browser.newContext({
      viewport: VIEWPORT,
      deviceScaleFactor: 1,
      locale: 'es-ES',
      colorScheme: 'dark',
      reducedMotion: 'reduce',
      recordVideo: DRY_RUN
        ? undefined
        : {
            dir: VIDEO_DIR,
            size: VIEWPORT,
          },
    });
    await installCursor(context);
    page = await context.newPage();
    video = page.video();

    // Preparamos la primera diapositiva antes de abrir el cronómetro del
    // contenido. Así los fotogramas de carga inicial no entran en el video.
    await page.goto(ARCHITECTURE_URL, { waitUntil: 'load' });
    await tid(page, 'architecture-slide').waitFor({ state: 'visible', timeout: 30000 });
    await page.evaluate(() => document.fonts?.ready);
    await sleep(250);
    contentStartWall = Date.now();

    let previousEnd = 0;
    for (let index = 0; index < segments.length; index += 1) {
      const segment = segments[index];
      if (segment.action === 'intro' || segment.action === 'outro') {
        continue;
      }

      const segmentStartWall = previousEnd === 0 ? contentStartWall : contentStartWall + previousEnd * 1000;
      const actionStart = Date.now();
      let attempt = 0;
      let lastError: unknown = null;
      while (attempt < 3) {
        attempt += 1;
        try {
          await performSegment(page, segment, docId);
          lastError = null;
          break;
        } catch (error) {
          lastError = error;
          const message = error instanceof Error ? error.message : String(error);
          log(`segmento ${segment.id} falló (intento ${attempt}/3): ${message}`);
          if (attempt >= 3) {
            break;
          }
          await recover(page, segment, docId);
        }
      }
      if (lastError) {
        fail(
          `El segmento «${segment.id}» falló 3 veces. ` +
            'Revisa que el frontend tenga los data-testid y que la API/worker respondan.',
          lastError,
        );
      }

      // Si acabamos de subir, recuperamos el id real del documento para el filtro.
      if (segment.id === 'upload-start') {
        const document = await waitForDemoDocument();
        docId = document.id;
        log(`documento de demo: ${docId}`);
      }

      const minEndWall = actionStart + Math.round(segment.minDuration * 1000);
      await padToMinimum(page, actionStart, segment.minDuration);
      const endWall = Math.max(Date.now(), minEndWall);
      const start = Number(((segmentStartWall - contentStartWall) / 1000).toFixed(3));
      const duration = Number(((endWall - contentStartWall) / 1000 - start).toFixed(3));
      recorded.push({
        index,
        id: segment.id,
        action: segment.action,
        narration: segment.narration,
        question: segment.question,
        start,
        duration,
        audioDuration: segment.audioDuration,
        minDuration: segment.minDuration,
      });
      previousEnd = start + duration;
      log(
        `${segment.id.padEnd(18)} ${duration.toFixed(2)}s ` +
          `(audio ${segment.audioDuration.toFixed(2)}s, mínimo ${segment.minDuration.toFixed(2)}s)`,
      );
    }

    const contentEndWall = contentStartWall + previousEnd * 1000;
    closeWall = Date.now();
    const wallVideoSpan = (closeWall - recordingStartWall) / 1000;
    const contentStart = (contentStartWall - recordingStartWall) / 1000;

    if (page) {
      await page.close();
    }
    if (context) {
      await context.close();
      context = null;
    }
    const videoPath = video ? await video.path() : null;
    if (browser) {
      await browser.close();
      browser = null;
    }

    let finalVideoPath: string | null = null;
    if (videoPath && !DRY_RUN) {
      finalVideoPath = join(VIDEO_DIR, 'app.webm');
      renameSync(videoPath, finalVideoPath);
    }

    const ffprobe = findFfprobe();
    const videoDuration = finalVideoPath ? probeDuration(ffprobe, finalVideoPath) : null;
    const videoOffset =
      videoDuration !== null ? Number((videoDuration - wallVideoSpan).toFixed(3)) : 0;
    // Si el WebM arranca con fotogramas extra, los recortamos. Si es más corto,
    // no desplazamos el contenido: build.sh rellena el final clonando el último frame.
    const adjustedStart = Number(
      Math.max(0, contentStart + Math.max(0, videoOffset)).toFixed(3),
    );
    const contentDuration = Number(((contentEndWall - contentStartWall) / 1000).toFixed(3));

    if (ffprobe === null && !DRY_RUN) {
      log('aviso: ffprobe no está en PATH; no se pudo calibrar el inicio del video.');
    }

    const payload = {
      dryRun: DRY_RUN,
      appUrl: APP_URL,
      apiUrl: apiBase,
      demoPdf: DEMO_PDF,
      documentId: docId,
      viewport: VIEWPORT,
      fps: 30,
      recordingStartWall,
      contentStartWall,
      contentEndWall,
      wallVideoSpan: Number(wallVideoSpan.toFixed(3)),
      videoDuration,
      videoOffset,
      contentStart: adjustedStart,
      contentDuration,
      video: finalVideoPath,
      segments: recorded,
    };
    writeTimeline(payload);

    const total = recorded.reduce((sum, item) => sum + item.duration, 0);
    log(
      `listo: ${recorded.length} segmentos, ${total.toFixed(2)}s de app ` +
        `(${(total / 60).toFixed(2)} min)`,
    );
    log(DRY_RUN ? `timeline dry-run: ${DRY_TIMELINE_JSON}` : `timeline: ${TIMELINE_JSON}`);
    if (finalVideoPath) {
      log(`video: ${finalVideoPath}`);
    }

    await verifyIndexedDocument(docId);
  } catch (error) {
    if (context) {
      await context.close().catch(() => undefined);
    }
    if (browser) {
      await browser.close().catch(() => undefined);
    }
    fail(
      'No se pudo completar la grabación. ' +
        'Comprueba que `docker compose up -d --build` esté sano y vuelve a intentarlo.',
      error,
    );
  }
}

async function verifyIndexedDocument(documentId: string): Promise<void> {
  if (!documentId) {
    return;
  }
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const documents = await listDocuments();
    const document = documents.find((item) => item.id === documentId);
    if (document && (document.chunkCount ?? 0) > 0) {
      log(
        `documento verificado: ${document.filename} · ` +
          `${document.pageCount ?? '?'} páginas · ${document.chunkCount} chunks`,
      );
      return;
    }
    await sleep(500);
  }
  fail(`El documento ${documentId} no quedó indexado (chunkCount = 0).`);
}

await main();
