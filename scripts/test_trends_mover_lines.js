#!/usr/bin/env node
/* Regression test: buildMoverLines() in trends/index.html, the Bootstrap
 * tooltip text of each /trends/ top-mover row (TF-6, 2026-11-12).
 *
 * The function is pulled out of the page by brace matching and run against
 * real movers rows (api.tweetfeed.live/v1/trends, 2026-11-12), a legacy row
 * without tweets/reporters (the stage data repo is pinned to 2026-07-18) and
 * the singular / zero edges. Also pins that the row carries no native title=,
 * which would override the tooltip content.
 *
 * Run:  node scripts/test_trends_mover_lines.js
 */
const fs = require('fs');
const path = require('path');

const PAGE = fs.readFileSync(path.join(__dirname, '..', 'trends', 'index.html'), 'utf8');
const UTILS = fs.readFileSync(path.join(__dirname, '..', 'js', 'utils.js'), 'utf8');

global.window = {};
global.document = { addEventListener() {} };
global.$ = () => { const q = { length: 0, on() { return q; }, off() { return q; } }; return q; };
new Function(UTILS)();
const TweetFeed = global.window.TweetFeed;
if (!TweetFeed || typeof TweetFeed.numberFormat !== 'function') throw new Error('TweetFeed.numberFormat missing');

function extract(src, name) {
  const start = src.indexOf('function ' + name + '(');
  if (start < 0) throw new Error(name + ' not found in trends/index.html');
  let depth = 0, i = src.indexOf('{', start);
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}' && --depth === 0) break;
  }
  return src.slice(start, i + 1);
}
const buildMoverLines = new Function('TweetFeed', extract(PAGE, 'buildMoverLines') + '\nreturn buildMoverLines;')(TweetFeed);

const CASES = [
  [{ tag: 'malware', count: 234, previous: 148, delta: 86, pct: 58.1, tweets: 44, previous_tweets: 44, reporters: 11, previous_reporters: 8 },
   ['Last 7 days: 234 IOCs from 44 tweets by 11 accounts', '7 days before: 148 IOCs from 44 tweets by 8 accounts']],
  [{ tag: 'vidar', count: 21, previous: 0, delta: 21, pct: null, tweets: 1, previous_tweets: 0, reporters: 1, previous_reporters: 0 },
   ['Last 7 days: 21 IOCs from 1 tweet by 1 account', '7 days before: 0 IOCs']],
  [{ tag: 'ransomware', count: 1, previous: 23, delta: -22, pct: -95.7, tweets: 1, previous_tweets: 10, reporters: 1, previous_reporters: 6 },
   ['Last 7 days: 1 IOC from 1 tweet by 1 account', '7 days before: 23 IOCs from 10 tweets by 6 accounts']],
  [{ tag: 'aitm', count: 0, previous: 8, delta: -8, pct: -100.0, tweets: 0, previous_tweets: 2, reporters: 0, previous_reporters: 1 },
   ['Last 7 days: 0 IOCs', '7 days before: 8 IOCs from 2 tweets by 1 account']],
  [{ tag: 'phishing', count: 1500, previous: 3, delta: 1497, pct: 49900.0 },
   ['Last 7 days: 1,500 IOCs', '7 days before: 3 IOCs']],
  [undefined, ['Last 7 days: 0 IOCs', '7 days before: 0 IOCs']],
];

const failures = [];
for (const [row, want] of CASES) {
  const got = buildMoverLines(row);
  if (JSON.stringify(got) !== JSON.stringify(want)) failures.push({ row, got, want });
}
if (/class="trd-mover"[^>]*\stitle=/.test(PAGE)) failures.push('trd-mover row has a native title= (overrides the tooltip)');

if (failures.length) {
  console.error('FAIL test_trends_mover_lines:\n' + JSON.stringify(failures, null, 2));
  process.exit(1);
}
console.log('ok test_trends_mover_lines: ' + CASES.length + ' cases');
