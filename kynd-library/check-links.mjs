// Audit: resolve every markdown link in the Kynd Library against the real
// file tree. Flags broken internal links (relative .md / .html paths).
import { readFileSync, readdirSync, statSync } from 'fs';
import { join, dirname, resolve, extname } from 'path';

const ROOT = new URL('.', import.meta.url).pathname;

function walk(dir) {
  const out = [];
  for (const e of readdirSync(dir)) {
    const p = join(dir, e);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (extname(p) === '.md') out.push(p);
  }
  return out;
}

const files = walk(ROOT);
const errors = [];
const linkRe = /\[[^\]]+\]\(([^)]+)\)/g;

for (const f of files) {
  const text = readFileSync(f, 'utf8');
  const rel = f.slice(ROOT.length);
  let m;
  while ((m = linkRe.exec(text))) {
    const target = m[1].split('#')[0]; // drop anchor
    if (!target) continue;
    if (/^https?:\/\//.test(target)) continue; // external, skip
    const abs = resolve(dirname(f), target);
    try {
      statSync(abs);
    } catch {
      errors.push(`${rel}  ->  ${target}  (broken)`);
    }
  }
}

console.log(`Checked ${files.length} markdown files.`);
if (errors.length === 0) {
  console.log('No broken internal links.');
} else {
  console.log(`BROKEN (${errors.length}):`);
  for (const e of errors) console.log('  ' + e);
  process.exit(1);
}
