#!/usr/bin/env node
// notion-push/push.js
// Push the Kynd Hermes Agent course into Notion.
//
// Usage:
//   node notion-push/push.js --dry-run                          # convert everything, no API calls
//   node notion-push/push.js --token <NOTION_TOKEN> --parent <pageIdOrUrl> [--layout hub|single]
//
// --layout hub    (default) hub page with section subpages + a Templates page
// --layout single one long page with a table of contents
//
// The parent page must be shared with your Notion integration.

const fs = require('fs');
const path = require('path');
const { mdToBlocks } = require('./convert');

const ROOT = path.join(__dirname, '..', 'HERMES-AGENT-RESOURCE');
const ASSETS_DIR = path.join(ROOT, 'ASSETS');

const SECTIONS = [
  '01-start-here.md',
  '02-installation-setup.md',
  '03-understanding-the-harness.md',
  '04-build-your-first-agent.md',
  '05-kynd-starter-kit.md',
  '06-real-projects.md',
  '07-prompt-vault.md',
  '08-troubleshooting.md',
];

const BLURBS = [
  'What it is , what it can and can\'t do , prerequisites',
  'Install for every OS , provider setup , first test',
  'Tools , skills , memory , context files . Only what you need',
  'Complete beginner build : the Research Brief Agent',
  'Copy-paste templates : SOUL.md , AGENTS.md , skills , tasks , QA',
  'Practical agent builds : research , assistant , content , ops , multi-agent',
  'Prompts by job : research , planning , QA , automation',
  'Problem → cause → fix → verify',
];

const SECTION_ICONS = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣'];

const NOTION_VERSION = '2022-06-28';
const CHUNK = 90; // max blocks per request is 100; stay under

const API = 'https://api.notion.com/v1';

// --- helpers ---------------------------------------------------------------

function readArg(name) {
  const argv = process.argv.slice(2);
  const eq = argv.find((a) => a.startsWith(`--${name}=`));
  if (eq) return eq.slice(name.length + 3);
  const idx = argv.indexOf(`--${name}`);
  if (idx !== -1 && argv[idx + 1] && !argv[idx + 1].startsWith('--')) return argv[idx + 1];
  if (argv.includes(`--${name}`)) return ''; // flag present
  return null;
}

function toId(s) {
  const v = String(s).trim();
  if (v.startsWith('http')) {
    const m = v.match(/[0-9a-fA-F]{32}/);
    if (m) return m[0].toLowerCase();
    const q = v.match(/[?&]p=([0-9a-fA-F]{32})/);
    if (q) return q[1].toLowerCase();
  }
  return v.replace(/-/g, '').toLowerCase();
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function api(headers, method, url, body, retries = 5) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    const res = await fetch(API + url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (res.status === 429 && attempt < retries) {
      const retryAfter = Number(res.headers.get('retry-after') || '1') * 1000;
      console.log(`  rate limited — waiting ${retryAfter}ms …`);
      await sleep(retryAfter);
      continue;
    }
    const json = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(`${method} ${url} → ${res.status} ${json.code || ''} ${json.message || ''}\n${JSON.stringify(json).slice(0, 800)}`);
    }
    return json;
  }
}

async function createPage(headers, parentId, title, icon) {
  const body = {
    parent: parentId === 'workspace'
      ? { type: 'workspace', workspace: true }
      : { type: 'page_id', page_id: parentId },
    properties: { title: { title: [{ type: 'text', text: { content: title } }] } },
  };
  if (icon) body.icon = { type: 'emoji', emoji: icon };
  return api(headers, 'POST', '/pages', body);
}

async function appendBlocks(headers, pageId, blocks) {
  for (let i = 0; i < blocks.length; i += CHUNK) {
    const slice = blocks.slice(i, i + CHUNK);
    await api(headers, 'PATCH', `/blocks/${pageId}/children`, { children: slice });
    await sleep(250);
  }
}

// --- content builders ------------------------------------------------------

function callout(emoji, richText, color = 'gray_background') {
  return {
    object: 'block', type: 'callout',
    callout: { rich_text: richText, icon: { type: 'emoji', emoji }, color },
  };
}

function paragraph(richText) {
  return { object: 'block', type: 'paragraph', paragraph: { rich_text: richText } };
}

function heading2(content) {
  return { object: 'block', type: 'heading_2', heading_2: { rich_text: [{ type: 'text', text: { content } }] } };
}

function bullet(richText) {
  return { object: 'block', type: 'bulleted_list_item', bulleted_list_item: { rich_text: richText } };
}

function text(content) { return { type: 'text', text: { content } }; }

function link(content, url) { return { type: 'text', text: { content, link: { url } } }; }

function mentionPage(id, label) {
  return { type: 'mention', mention: { type: 'page', page: { id } }, plain_text: label };
}

function divider() {
  return { object: 'block', type: 'divider', divider: {} };
}

function buildHubBlocks(sections, templatesId) {
  const b = [];
  b.push(callout('🧭', [text('Welcome to the Kynd full course for Hermes Agent . The most powerful LLM agent harness as of August 2026 .')]));
  b.push(paragraph([text('In this course you go from zero to a working Hermes Agent . Then to real projects . This is the resource I wish I had when I started working with this technology .')]));
  b.push(callout('📸', [text('If you don\'t understand something , take a picture with your phone of what I\'m talking about and ask an AI to help you out — or ask a question in the Discord .')]));
  b.push(heading2('The path'));
  for (const s of ['Understand', 'Setup', 'Build', 'Use', 'Extend']) b.push(bullet([text(s)]));
  b.push(heading2('Course sections'));
  for (const s of sections) {
    b.push(bullet([mentionPage(s.id, `${s.title} — ${s.blurb}`)]));
  }
  if (templatesId) b.push(bullet([mentionPage(templatesId, 'Templates — ready-to-copy starter kit assets')]));
  b.push(heading2('Sources'));
  b.push(bullet([link('Official repo', 'https://github.com/NousResearch/hermes-agent')]));
  b.push(bullet([link('Official docs', 'https://hermes-agent.nousresearch.com/docs/')]));
  b.push(bullet([link('Nous Portal', 'https://portal.nousresearch.com/manage-subscription')]));
  b.push(divider());
  b.push(paragraph([text('When you\'ve finished the course , send me a message on Discord starting with "FINISHED" and tell me what you built . Good luck .')]));
  const first = sections[0];
  if (first) {
    b.push(callout('🚀', [text('START HERE → '), mentionPage(first.id, first.title)], 'blue_background'));
  }
  return b;
}

// --- dry run ---------------------------------------------------------------

function histogram(blocks) {
  const h = {};
  for (const b of blocks) h[b.type] = (h[b.type] || 0) + 1;
  return h;
}

function dryRun() {
  const manifest = { sections: [], assets: [], warnings: [] };

  for (const file of SECTIONS) {
    const md = fs.readFileSync(path.join(ROOT, file), 'utf8');
    const { blocks, title } = mdToBlocks(md, { dropFirstH1: true });
    manifest.sections.push({ file, title, blocks: blocks.length, histogram: histogram(blocks) });
  }

  const assets = fs.readdirSync(ASSETS_DIR).filter((f) => f.endsWith('.md')).sort();
  for (const file of assets) {
    const md = fs.readFileSync(path.join(ASSETS_DIR, file), 'utf8');
    const { blocks, title } = mdToBlocks(md, { dropFirstH1: true });
    manifest.assets.push({ file, title, blocks: blocks.length, histogram: histogram(blocks) });
  }

  // Sanity checks: look for raw markdown that survived as paragraph text.
  for (const s of manifest.sections) {
    const md = fs.readFileSync(path.join(ROOT, s.file), 'utf8');
    const { blocks } = mdToBlocks(md, { dropFirstH1: true });
    for (const b of blocks) {
      if (b.type === 'paragraph' || b.type === 'bulleted_list_item' || b.type === 'to_do') {
        const txt = (b[b.type].rich_text || []).map((r) => r.plain_text || r.text?.content || '').join('').trim();
        if (/^(#{1,6}\s|\|.*\||```|-{3,}$)/.test(txt)) {
          manifest.warnings.push(`${s.file}: suspicious leftover: "${txt.slice(0, 60)}"`);
        }
      }
      if (b.type === 'code') {
        const txt = (b.code.rich_text || []).map((r) => r.text?.content || '').join('');
        if (txt.length > 2000) manifest.warnings.push(`${s.file}: code block over 2000 chars (${txt.length})`);
      }
    }
  }

  console.log('\n=== DRY RUN ===');
  let total = 0;
  for (const s of manifest.sections) {
    total += s.blocks;
    console.log(`  ${s.file.padEnd(34)} → "${s.title}"  ${String(s.blocks).padStart(4)} blocks  ${JSON.stringify(s.histogram)}`);
  }
  console.log(`  ${'ASSETS (8 files)'.padEnd(34)} → ${manifest.assets.reduce((n, a) => n + a.blocks, 0)} blocks total`);
  if (manifest.warnings.length) {
    console.log('\nWARNINGS:');
    for (const w of manifest.warnings) console.log(`  ⚠ ${w}`);
  } else {
    console.log('\nNo conversion warnings .');
  }
  fs.writeFileSync(path.join(__dirname, 'dry-run-manifest.json'), JSON.stringify(manifest, null, 2));
  console.log(`Total section blocks: ${total} . Manifest written to notion-push/dry-run-manifest.json .`);
}

// --- main ------------------------------------------------------------------

async function main() {
  if (readArg('dry-run') !== null || readArg('dryrun') !== null) {
    dryRun();
    return;
  }

  let token = readArg('token') || process.env.NOTION_TOKEN;
  const parent = readArg('parent');
  const layout = (readArg('layout') || 'hub').toLowerCase();

  if (!token) { console.error('Missing Notion token. Pass --token or set NOTION_TOKEN.'); process.exit(1); }
  if (!parent) { console.error('Missing parent page. Pass --parent <pageIdOrUrl>.'); process.exit(1); }

  token = token.trim();

  // Parent can be a page id/URL, or the special value 'workspace' to create a
  // standalone top-level page at the workspace root.
  const useWorkspace = String(parent).trim().toLowerCase() === 'workspace';
  let parentId = useWorkspace ? 'workspace' : toId(parent);
  if (!useWorkspace && !/^[0-9a-f]{32}$/.test(parentId)) {
    console.error(`Could not read a page id from: ${parent}`); process.exit(1);
  }

  const headers = {
    Authorization: `Bearer ${token}`,
    'Notion-Version': NOTION_VERSION,
    'Content-Type': 'application/json',
  };

  console.log(`Pushing to ${useWorkspace ? 'workspace root (standalone top-level page)' : parentId} (layout: ${layout}) …`);

  // --- read course files
  const sectionData = SECTIONS.map((file, idx) => {
    const md = fs.readFileSync(path.join(ROOT, file), 'utf8');
    return { file, md, num: idx + 1, blurb: BLURBS[idx], icon: SECTION_ICONS[idx] };
  });

  const assetFiles = fs.readdirSync(ASSETS_DIR).filter((f) => f.endsWith('.md')).sort();
  const assetData = assetFiles.map((f) => ({
    file: f,
    md: fs.readFileSync(path.join(ASSETS_DIR, f), 'utf8'),
  }));

  // --- single long page layout
  if (layout === 'single') {
    const page = await createPage(headers, parentId, 'KYND — Hermes Agent', '🧭');
    const blocks = [{ object: 'block', type: 'table_of_contents', table_of_contents: {} }];
    for (const s of sectionData) {
      const { blocks: b } = mdToBlocks(s.md, { dropFirstH1: false });
      blocks.push(...b);
      blocks.push(divider());
    }
    blocks.push(heading2('Templates'));
    for (const a of assetData) {
      const { blocks: b, title } = mdToBlocks(a.md, { dropFirstH1: true });
      blocks.push({ object: 'block', type: 'toggle', toggle: { rich_text: [text(title || a.file)], children: b } });
    }
    console.log(`Created page with ${blocks.length} blocks — appending in chunks…`);
    await appendBlocks(headers, page.id, blocks);
    console.log(`Done → https://www.notion.so/${page.id}`);
    return;
  }

  // --- hub layout
  const hub = await createPage(headers, parentId, 'KYND — Hermes Agent', '🧭');
  console.log(`Hub created: ${hub.id}`);

  const created = [];
  for (const s of sectionData) {
    const page = await createPage(headers, hub.id, sectionTitle(s), s.icon);
    created.push({ file: s.file, id: page.id, title: sectionTitle(s), blurb: s.blurb });
    console.log(`  created ${s.file} → ${page.id}`);
    await sleep(200);
  }

  const templatesPage = await createPage(headers, hub.id, 'Templates — starter kit', '🧰');
  created.push({ file: 'ASSETS', id: templatesPage.id, title: 'Templates', blurb: '' });
  console.log(`  created Templates → ${templatesPage.id}`);

  // Map relative .md links to page ids (turns "NEXT →" links into real page links).
  const linkMap = {};
  for (const c of created) linkMap[c.file] = c.id;
  linkMap['README.md'] = hub.id;
  for (const a of assetData) {
    linkMap[`ASSETS/${a.file}`] = templatesPage.id;
    linkMap[a.file] = templatesPage.id;
  }
  linkMap['ASSETS/'] = templatesPage.id;
  linkMap['ASSETS'] = templatesPage.id;

  // Append section content.
  for (let idx = 0; idx < sectionData.length; idx++) {
    const s = sectionData[idx];
    const c = created[idx];
    const { blocks } = mdToBlocks(s.md, { linkMap, dropFirstH1: true });
    console.log(`  appending ${s.file} (${blocks.length} blocks) …`);
    await appendBlocks(headers, c.id, blocks);
  }

  // Templates page: each asset as a toggle.
  const tplBlocks = [paragraph([text('Ready-to-copy template files from Section 5 . Open a toggle and copy the contents .')])];
  for (const a of assetData) {
    const { blocks, title } = mdToBlocks(a.md, { linkMap, dropFirstH1: true });
    tplBlocks.push({
      object: 'block', type: 'toggle',
      toggle: { rich_text: [text(title || a.file)], children: blocks },
    });
  }
  console.log(`  appending Templates (${tplBlocks.length} toggles) …`);
  await appendBlocks(headers, templatesPage.id, tplBlocks);

  // Hub content last (it links to the child pages).
  const hubBlocks = buildHubBlocks(
    sectionData.map((s, idx) => ({ id: created[idx].id, title: sectionTitle(s), blurb: s.blurb })),
    templatesPage.id
  );
  console.log(`  appending hub intro (${hubBlocks.length} blocks) …`);
  await appendBlocks(headers, hub.id, hubBlocks);

  console.log(`\nDone . Open it here:`);
  console.log(`  https://www.notion.so/${hub.id}`);
}

// Section pages need a computed title — read it from the file's first H1.
function sectionTitle(s) {
  const m = s.md.match(/^#\s+(.+)$/m);
  return m ? m[1].trim() : s.file;
}

main().catch((err) => {
  console.error('\nFAILED:');
  console.error(err.message);
  process.exit(1);
});
