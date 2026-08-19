#!/usr/bin/env node
/* Regression test: formatDateLong() must render feed timestamps as the UTC
 * instant they already are, in every viewer timezone.
 *
 * Feed rows carry "YYYY-MM-DD HH:MM:SS" in UTC. That is not ISO 8601 (space
 * instead of "T", no zone), so V8 parses it as LOCAL time. The function reads
 * the result back with getUTC* and appends a literal "UTC", so before this was
 * pinned a UTC+2 viewer saw "2026-01-01 00:00:00" as
 * "December 31st, 2025 23:00:00 UTC" - wrong year, wrong day, still labelled UTC.
 *
 * Run:  node scripts/test_utils_dates.js
 */
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const UTILS = path.join(__dirname, '..', 'js', 'utils.js');
const ZONES = ['UTC', 'Europe/Madrid', 'America/Los_Angeles', 'Asia/Tokyo', 'Pacific/Kiritimati'];
const CASES = [
  ['2026-08-19 00:52:38', 'August 19th, 2026 00:52:38 UTC'],
  ['2026-08-19 23:30:00', 'August 19th, 2026 23:30:00 UTC'],
  ['2026-01-01 00:00:00', 'January 1st, 2026 00:00:00 UTC'],
  ['2026-12-31 23:59:59', 'December 31st, 2026 23:59:59 UTC'],
  ['2026-08-19T00:52:38Z', 'August 19th, 2026 00:52:38 UTC'],
];

if (process.env.TF_DATE_CHILD) {
  global.window = {};
  global.document = { addEventListener() {} };
  global.$ = () => ({ length: 0, on() {}, off() {} });
  new Function(fs.readFileSync(UTILS, 'utf8'))();
  const f = global.window.formatDateLong;
  const out = CASES.map(([i, want]) => [i, f(i), want]);
  process.stdout.write(JSON.stringify(out));
  process.exit(0);
}

let failures = [];
for (const tz of ZONES) {
  const raw = execFileSync(process.execPath, [__filename], {
    env: { ...process.env, TZ: tz, TF_DATE_CHILD: '1' }, encoding: 'utf8',
  });
  for (const [input, got, want] of JSON.parse(raw)) {
    if (got !== want) failures.push(`TZ=${tz} ${JSON.stringify(input)} -> ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
  }
}
if (failures.length) {
  console.log('[FAIL] formatDateLong UTC test:');
  failures.forEach(f => console.log('  - ' + f));
  process.exit(1);
}
console.log(`[PASS] formatDateLong UTC test: ${CASES.length} timestamps stable across ${ZONES.length} timezones`);
