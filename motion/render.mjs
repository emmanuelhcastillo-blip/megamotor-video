// Renderiza gráficos con transparencia (ProRes 4444) para que ffmpeg los superponga al reel.
// Uso: node render.mjs trabajos.json   con [{"props": {...}, "out": "/ruta/archivo.mov"}, ...]
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';
import {renderMedia, selectComposition} from '@remotion/renderer';

const here = path.dirname(fileURLToPath(import.meta.url));
const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const browserExecutable =
  process.env.REMOTION_BROWSER ||
  ['/opt/pw-browsers/chromium_headless_shell-1243/chrome-linux/headless_shell'].find((p) => fs.existsSync(p)) ||
  null;

const serveUrl = await bundle({entryPoint: path.join(here, 'src/index.ts')});
for (const j of jobs) {
  const t0 = Date.now();
  const composition = await selectComposition({serveUrl, id: 'Grafico', inputProps: j.props, browserExecutable});
  await renderMedia({
    serveUrl,
    composition,
    inputProps: j.props,
    codec: 'prores',
    proResProfile: '4444',
    pixelFormat: 'yuva444p10le',
    imageFormat: 'png',
    muted: true,
    outputLocation: j.out,
    browserExecutable,
    concurrency: Number(process.env.REMOTION_CONCURRENCY || 2),
    logLevel: 'error',
  });
  console.log(JSON.stringify({out: j.out, seconds: (Date.now() - t0) / 1000}));
}
