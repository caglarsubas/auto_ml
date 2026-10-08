#!/usr/bin/env node
// Local preview of built assets for browser qualification; production serving is D07 work.
import { createServer } from 'node:http';
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';

const root = resolve(process.argv[2] || 'frontend/dist/frontend/browser');
const port = Number(process.argv[3] || 4300);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid preview port');
if (!(await stat(root)).isDirectory()) throw new Error('Build the frontend before serving it');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.woff': 'font/woff' };
const server = createServer(async (req, res) => {
  const fail = (status) => { res.writeHead(status); res.end(); };
  if (!['GET', 'HEAD'].includes(req.method)) return fail(405);
  try {
    const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    if (pathname.split('/').some(part => part.startsWith('.'))) return fail(404);
    let file = resolve(root, `.${pathname}`);
    if (file !== root && !file.startsWith(root + sep)) return fail(404);
    let info = await stat(file).catch(() => null);
    if (!info?.isFile()) {
      if (!req.headers.accept?.includes('text/html')) return fail(404);
      file = resolve(root, 'index.html');
      info = await stat(file);
    }
    res.writeHead(200, { 'Content-Type': types[extname(file)] || 'application/octet-stream',
      'Content-Length': info.size, 'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store' });
    if (req.method === 'HEAD') return res.end();
    createReadStream(file).on('error', () => res.destroy()).pipe(res);
  } catch { fail(400); }
});
server.listen(port, '127.0.0.1', () => console.log(`Built frontend preview: http://localhost:${port}`));
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => server.close(() => process.exit(0)));
