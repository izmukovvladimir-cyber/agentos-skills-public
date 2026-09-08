// Full-page screenshot helper: node src/shot.mjs <url> <out.png> [w] [h]
// Playwright is not vendored here: point PLAYWRIGHT_PATH at an existing checkout,
// e.g. export PLAYWRIGHT_PATH=~/node_modules/playwright/index.mjs
const { chromium } = await import(process.env.PLAYWRIGHT_PATH || 'playwright');

const [url, out, w = 1440, h = 900] = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', args: ['--no-sandbox'] });
const page = await browser.newPage({ viewport: { width: +w, height: +h } });
await page.goto(url, { waitUntil: 'networkidle' });
await page.evaluate(async () => {
  const step = window.innerHeight * 0.8;
  for (let y = 0; y < document.body.scrollHeight; y += step) {
    window.scrollTo(0, y);
    await new Promise((r) => setTimeout(r, 120));
  }
  window.scrollTo(0, 0);
});
// lazy images never load in a full-page shot, and reveal-on-scroll may not have fired
await page.evaluate(async () => {
  document.querySelectorAll('img').forEach((i) => { i.loading = 'eager'; i.src = i.src; });
  await Promise.all([...document.images].map((i) => (i.complete ? 0 : new Promise((r) => { i.onload = i.onerror = r; }))));
  document.querySelectorAll('.rv').forEach((e) => e.classList.add('in'));
});
await page.waitForTimeout(600);
await page.screenshot({ path: out, fullPage: true });
await browser.close();
