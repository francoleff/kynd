// Verify the deployed Kynd Library page renders correctly (camoufox / Firefox).
// Usage: node verify-library.mjs
import { Camoufox } from 'camoufox-js';
import { mkdirSync } from 'fs';

const OUT = '/Users/francoleff/workspace/kynd/screenshots';
mkdirSync(OUT, { recursive: true });

const browser = await Camoufox({ headless: true, os: ['macos'] });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

async function shot(name, url, extra) {
  await page.goto(url, { waitUntil: 'load', timeout: 60000 });
  await page.waitForTimeout(2500);
  if (extra) await extra();
  await page.screenshot({ path: `${OUT}/${name}.png` });
  console.log(name, 'OK', await page.title());
}

await shot('lib-top', 'https://join-kynd.netlify.app/library');

// visible card count + search behaviour
const visible = await page.evaluate(() =>
  Array.from(document.querySelectorAll('.tool')).filter(e => !e.hidden).length);
const countText = await page.textContent('#count');
console.log('visible cards:', visible, '| count label:', countText);

await page.fill('#q', 'voice');
await page.waitForTimeout(600);
const afterSearch = await page.evaluate(() =>
  Array.from(document.querySelectorAll('.tool')).filter(e => !e.hidden).length);
console.log('after search "voice":', afterSearch, '|', await page.textContent('#count'));
await page.screenshot({ path: `${OUT}/lib-search-voice.png` });

await page.fill('#q', '');
await page.click('.chip[data-filter="Coding Agents"]');
await page.waitForTimeout(600);
const afterChip = await page.evaluate(() =>
  Array.from(document.querySelectorAll('.tool')).filter(e => !e.hidden).length);
console.log('after chip "Coding Agents":', afterChip, '|', await page.textContent('#count'));
await page.screenshot({ path: `${OUT}/lib-chip-coding.png` });

// scroll to grid + cta
await page.click('.chip[data-filter="all"]');
await page.waitForTimeout(400);
await page.evaluate(() => window.scrollTo(0, 1100));
await page.waitForTimeout(800);
await page.screenshot({ path: `${OUT}/lib-grid.png` });

await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await page.waitForTimeout(800);
await page.screenshot({ path: `${OUT}/lib-bottom.png` });

// homepage with the new library link
await shot('home-with-library', 'https://join-kynd.netlify.app/');
const linkHref = await page.getAttribute('.hero__link', 'href');
console.log('homepage library link href:', linkHref);

// mobile
const m = await browser.newPage({ viewport: { width: 390, height: 844 } });
await m.goto('https://join-kynd.netlify.app/library', { waitUntil: 'load', timeout: 60000 });
await m.waitForTimeout(2000);
await m.screenshot({ path: `${OUT}/lib-mobile.png` });
console.log('mobile OK');

await browser.close();
