#!/usr/bin/env node
/* Regression test: the quote-free fast path of parseCSV() must return exactly
 * what the original character loop returns, for every quote-free input.
 *
 * js/utils.js parseCSV() splits on line breaks + commas when the text holds no
 * double quote (week.csv has none, ~4,900 rows), and keeps the RFC 4180 char
 * loop for anything quoted. The two must stay deep-equal: same rows, same
 * empty fields, blank lines dropped, CR / LF / CRLF all line breaks.
 * referenceParse below is a verbatim copy of the ORIGINAL char loop.
 *
 * Run:  node scripts/test_parse_csv.js
 */
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const UTILS = path.join(__dirname, '..', 'js', 'utils.js');

// Same stubs as scripts/test_utils_dates.js: utils.js only needs window/document/$
// at load time. Chainable like jQuery: utils.js binds with $(document).off(...).on(...).
global.window = {};
global.document = { addEventListener() {} };
global.$ = () => { const q = { length: 0, on() { return q; }, off() { return q; } }; return q; };
new Function(fs.readFileSync(UTILS, 'utf8'))();
const parseCSV = global.window.TweetFeed.parseCSV;
if (typeof parseCSV !== 'function') {
  console.log('[FAIL] parseCSV test: window.TweetFeed.parseCSV is not exposed by js/utils.js');
  process.exit(1);
}

// ─── Verbatim copy of the original char-loop parser (pre fast path) ──────────
  function referenceParse(text) {
    var rows = [];
    var row = [];
    var field = '';
    var inQuotes = false;
    var i = 0;
    var len = text.length;

    while (i < len) {
      var c = text.charAt(i);

      if (inQuotes) {
        if (c === '"') {
          if (text.charAt(i + 1) === '"') {
            // Escaped quote inside quoted field
            field += '"';
            i += 2;
            continue;
          }
          // End of quoted field
          inQuotes = false;
          i++;
          continue;
        }
        field += c;
        i++;
        continue;
      }

      if (c === '"' && field === '') {
        inQuotes = true;
        i++;
        continue;
      }
      if (c === ',') {
        row.push(field);
        field = '';
        i++;
        continue;
      }
      if (c === '\n' || c === '\r') {
        row.push(field);
        field = '';
        // Only push non-empty rows (ignore trailing empty lines)
        if (row.length > 1 || (row.length === 1 && row[0] !== '')) {
          rows.push(row);
        }
        row = [];
        if (c === '\r' && text.charAt(i + 1) === '\n') {
          i += 2;
        } else {
          i++;
        }
        continue;
      }
      field += c;
      i++;
    }

    // Handle last field/row if no trailing newline
    if (field !== '' || row.length > 0) {
      row.push(field);
      if (row.length > 1 || (row.length === 1 && row[0] !== '')) {
        rows.push(row);
      }
    }

    return rows;
  }

// ─── Fixed fixtures ──────────────────────────────────────────────────────────
const WEEK_SAMPLE =
  '2026-10-17 00:03:12,example_user,url,hxxps://bad.example/a/b?x=1&y=2,#phishing #scam,https://twitter.com/example_user/status/1\r\n' +
  '2026-10-17 00:05:40,another_u,domain,evil.example,#malware,https://twitter.com/another_u/status/2\r\n' +
  '2026-10-17 00:09:01,third,ip,203.0.113.7,,https://twitter.com/third/status/3\r\n' +
  '2026-10-17 00:11:55,fourth,sha256,' + 'a'.repeat(64) + ',#stealer #Lumma,https://twitter.com/fourth/status/4\r\n' +
  '2026-10-17 00:12:30,fifth,md5,' + 'b'.repeat(32) + ',#c2,https://twitter.com/fifth/status/5\r\n';

const FIXTURES = [
  ['empty string', ''],
  ['only LF', '\n'],
  ['only CR', '\r'],
  ['only CRLF', '\r\n'],
  ['only blank lines', '\n\n\r\n\r\r'],
  ['single field no newline', 'a'],
  ['LF rows', 'a,b\nc,d\n'],
  ['CRLF rows', 'a,b\r\nc,d\r\n'],
  ['lone CR rows', 'a,b\rc,d\r'],
  ['\\n\\r pair is two breaks', 'a,b\n\rc,d'],
  ['mixed line endings', 'a,b\nc,d\r\ne,f\rg,h'],
  ['\\r\\r\\n', 'a\r\r\nb'],
  ['no trailing newline', 'a,b\nc,d'],
  ['trailing newline', 'a,b\nc,d\n'],
  ['several trailing newlines', 'a,b\nc,d\n\n\n'],
  ['leading blank lines', '\n\na,b'],
  ['blank line between rows', 'a,b\n\nc,d'],
  ['line that is only a comma', ',\n'],
  ['only a comma, no newline', ','],
  ['two commas', ',,'],
  ['empty fields', 'a,,c\n,b,\n,,\n'],
  ['trailing comma at EOF', 'a,b,'],
  ['leading comma at EOF', ',a'],
  ['spaces and hashes', ' ,# a,#\n  \n#,\n'],
  ['whitespace-only line is a row', ' \na'],
  ['quoted file takes the fallback', 'a,"b,c",d\r\n"e ""q"" f",g,h\r\n'],
  ['quoted field spanning lines', 'a,"b\nc",d\ne,f,g\n'],
  ['quote in the last field only', 'a,b\nc,"d"'],
  ['real-looking week.csv sample, CRLF', WEEK_SAMPLE],
  ['week.csv sample, LF', WEEK_SAMPLE.replace(/\r\n/g, '\n')],
  ['week.csv sample, no final newline', WEEK_SAMPLE.replace(/\r\n$/, '')],
];

let checked = 0;
const failures = [];
function check(label, input) {
  checked++;
  let got, want;
  try {
    got = parseCSV(input);
    want = referenceParse(input);
    assert.deepStrictEqual(got, want);
  } catch (e) {
    failures.push(`${label} ${JSON.stringify(input)}\n      got  ${JSON.stringify(got)}\n      want ${JSON.stringify(want)}`);
  }
}

FIXTURES.forEach(([label, input]) => check(label, input));

// Pin a few absolute results too, so a bug shared by both parsers cannot hide.
function pin(label, input, want) {
  checked++;
  const got = parseCSV(input);
  try {
    assert.deepStrictEqual(got, want);
  } catch (e) {
    failures.push(`pinned ${label} ${JSON.stringify(input)}\n      got  ${JSON.stringify(got)}\n      want ${JSON.stringify(want)}`);
  }
}
pin('comma-only line', ',\n', [['', '']]);
pin('blank lines only', '\n\n', []);
pin('CRLF without final newline', 'a,b\r\nc,d', [['a', 'b'], ['c', 'd']]);
pin('quoted comma', 'a,"b,c"\n', [['a', 'b,c']]);
pin('week sample, 5 rows x 6 fields', WEEK_SAMPLE, WEEK_SAMPLE.split('\r\n').filter(l => l).map(l => l.split(',')));

// ─── Random strings (seeded, so a failure reproduces) ────────────────────────
const ALPHABET = ['a', 'b', ',', '\n', '\r', ' ', '#'];
let seed = 0x7f4a7c15;
function rand() { // mulberry32
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}
const RANDOM_RUNS = 2000;
for (let n = 0; n < RANDOM_RUNS; n++) {
  const len = Math.floor(rand() * 41);
  let s = '';
  for (let i = 0; i < len; i++) s += ALPHABET[Math.floor(rand() * ALPHABET.length)];
  check('random #' + n, s);
}

if (failures.length) {
  console.log(`[FAIL] parseCSV fast-path test: ${failures.length} of ${checked} inputs differ from the char loop:`);
  failures.slice(0, 20).forEach(f => console.log('  - ' + f));
  process.exit(1);
}
console.log(`[PASS] parseCSV fast-path test: ${checked} inputs (${FIXTURES.length} fixtures + ${RANDOM_RUNS} random) deep-equal to the original char loop`);
