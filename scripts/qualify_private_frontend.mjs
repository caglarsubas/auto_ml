// Owned private fixture only: real compiled Angular over the fixed TLS ingress.
// The exact generated test certificate is pinned; global TLS verification stays on.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const { chromium } = require('@playwright/test');
let input = '';
for await (const chunk of process.stdin) input += chunk;
const value = JSON.parse(input);
assert.match(value.pin, /^[A-Za-z0-9+/]{43}=$/);
assert.ok(Number.isInteger(value.port) && value.port > 0 && value.port <= 65535);
const origin = 'https://api.private.test:8443';
const browser = await chromium.launch({ args: [
  '--no-proxy-server',
  `--host-resolver-rules=MAP api.private.test:8443 127.0.0.1:${value.port}`,
  `--ignore-certificate-errors-spki-list=${value.pin}`,
] });
const external = [], errors = [], violations = [];
const scripts = new Map();
const bootstrapCodes = new Set();
let stage = 'create_context';
let loginStatus = null;
let page;
function scriptPath(request) {
  const url = new URL(request.url());
  return request.resourceType() === 'script' && url.origin === origin &&
    /^\/[a-zA-Z0-9._/-]{1,120}\.js$/.test(url.pathname) ? url.pathname : null;
}
try {
  const context = await browser.newContext();
  page = await context.newPage();
  page.on('response', response => {
    const path = scriptPath(response.request());
    if (!path || scripts.size >= 16) return;
    const mediaType = response.headers()['content-type']?.split(';')[0];
    scripts.set(path, { status: response.status(), javascript: /^(application|text)\/javascript$/.test(mediaType ?? '') });
  });
  page.on('requestfailed', request => {
    const path = scriptPath(request);
    if (path && scripts.size < 16) scripts.set(path, { failed: true });
  });
  page.on('console', message => {
    if (message.type() !== 'error' || bootstrapCodes.size >= 16) return;
    // Capture standard codes only. Console output can contain response values.
    const code = message.text().match(/\bNG\d{4,5}\b|\b(?:Reference|Type|Syntax|Range)Error\b/)?.[0];
    if (code) bootstrapCodes.add(code);
  });
  page.on('pageerror', error => errors.push(error.message));
  await page.exposeFunction('policyViolation', directive => violations.push(directive));
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', e => window.policyViolation(e.violatedDirective));
  });
  page.on('dialog', dialog => dialog.accept());
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin === origin) return route.continue();
    external.push(url.origin);
    return route.abort();
  });
  stage = 'load_login';
  const login = await page.goto(origin + '/login');
  loginStatus = login.status();
  assert.equal(login.status(), 200);
  assert.match(login.headers()['content-type'], /text\/html/);
  assert.equal(login.headers()['cache-control'], 'no-store');
  assert.match(login.headers()['content-security-policy'], /connect-src 'self'/);
  stage = 'render_login';
  await page.getByLabel('Username', { exact: true }).fill(value.username);
  await page.getByLabel('Password', { exact: true }).fill(value.password);
  stage = 'sign_in';
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  await page.waitForURL(origin + '/home');
  await page.reload();
  await page.getByLabel('Current project').waitFor();
  const selection = page.getByLabel('Current project');
  assert.ok(await selection.inputValue());
  assert.match(await page.locator('#workspace-role').innerText(), /developer/);
  const cookies = await context.cookies();
  assert.ok(cookies.find(c => c.name === 'sessionid' && c.secure && c.httpOnly));
  assert.ok(cookies.find(c => c.name === 'csrftoken' && c.secure));
  stage = 'verify_private_workflow';
  await page.goto(origin + '/model-development/declaration');
  await page.getByRole('heading', { name: 'Model Development', exact: true }).waitFor();
  const fonts = await page.evaluate(async () => {
    const names = ['400 16px "Instrument Sans"', '400 16px "Instrument Serif"',
      '400 16px "IBM Plex Mono"', '400 24px "Material Icons"'];
    await Promise.all(names.map(font => document.fonts.load(font)));
    return names.every(font => document.fonts.check(font));
  });
  assert.ok(fonts);
  await page.locator('.pipeline-type-dropdown select').selectOption('boosting');
  const creation = page.waitForResponse(r => r.url().includes('/pipeline/create/') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Start', exact: true }).click();
  assert.equal((await creation).status(), 201);
  const csv = 'x,target\n1,0\n2,1\n3,0\n4,1\n';
  await page.locator('app-declaration input[type="file"]').first().setInputFiles({
    name: 'private-browser.csv', mimeType: 'text/csv', buffer: Buffer.from(csv),
  });
  await page.getByLabel('COLUMN SEPARATOR').selectOption('comma');
  const upload = page.waitForResponse(r => r.url().endsWith('/api/declaration/') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'IMPORT DATA', exact: true }).click();
  const uploaded = await upload;
  assert.equal(uploaded.status(), 201);
  const created = await uploaded.json();
  const path = new URL(created.file, origin).pathname;
  const get = path => page.evaluate(async path => {
    const response = await fetch(path);
    return { status: response.status, body: await response.text(), type: response.headers.get('content-type'),
      cache: response.headers.get('cache-control') };
  }, path);
  assert.deepEqual(await get(path), { status: 200, body: csv, type: 'text/csv', cache: 'private, no-store' });
  const protectedHeaders = await page.evaluate(async path => {
    const response = await fetch(path);
    return { disposition: response.headers.get('content-disposition'), policy: response.headers.get('content-security-policy') };
  }, path);
  assert.equal(protectedHeaders.disposition, 'attachment');
  assert.ok(protectedHeaders.policy.startsWith('sandbox;'));
  // A same-origin data artifact must not qualify as an application script.
  const blocked = await page.evaluate(path => new Promise(resolve => {
    const script = document.createElement('script');
    script.src = path;
    script.onload = () => resolve(false);
    script.onerror = () => resolve(true);
    document.head.append(script);
  }), path);
  assert.equal(blocked, true);
  for (const [path, status] of [['/admin/', 404], ['/.env', 404], ['/assets/missing.js', 404],
    ['/assets/fonts/sources.json', 404], ['/api/not-a-route/', 404], ['/media/unassigned.csv', 403]]) {
    const result = await get(path);
    assert.equal(result.status, status);
    assert.ok(!result.body.includes('<app-root>'));
  }
  const denied = await page.evaluate(async () => {
    const response = await fetch('/api/pipeline/create/', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: '{}' });
    return response.status;
  });
  assert.equal(denied, 403);
  await page.getByRole('button', { name: /sign out/i }).click();
  await page.waitForURL(origin + '/login');
  assert.equal((await get(path)).status, 403);
  await page.goto(origin + '/home');
  await page.waitForURL(origin + '/login');
  assert.deepEqual(external, []);
  assert.deepEqual(errors, []);
  assert.deepEqual(violations, ['script-src-elem']);
  console.log(JSON.stringify({ compiled_private_browser: 'passed', certificate: 'exact_fixture_leaf_spki_pin',
    same_origin_session_csrf: 'passed', project_selection_reload: 'passed', local_fonts: 'passed',
    pipeline_and_upload: 'passed', protected_download_logout: 'passed',
    missing_assets_metadata_admin_api_fallback: 'blocked', media_as_application_script: 'blocked_by_csp',
    protected_media_document: 'attachment_and_sandbox', external_requests: 0, runtime_errors: 0,
    unexpected_csp_violations: 0, deliberate_script_violation: 1 }));
} catch (error) {
  const loginDom = await page?.evaluate(() => ({
    app_root: !!document.querySelector('app-root'),
    login_component: !!document.querySelector('app-login'),
    username_input: !!document.querySelector('#username'),
  })).catch(() => null);
  console.error(JSON.stringify({
    private_browser_failure: stage, login_status: loginStatus, login_dom: loginDom ?? null,
    script_responses: Object.fromEntries(scripts), bootstrap_codes: [...bootstrapCodes],
    page_errors: errors.length, external_requests: external.length,
    csp_directives: violations.filter(value => /^[a-z-]{1,40}$/.test(value)).slice(0, 16),
  }));
  throw error;
} finally {
  await browser.close();
}
