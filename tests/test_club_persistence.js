// Tests for club-selection cookie persistence in docs/programs.js.
// programs.js runs against `window` and touches `document.cookie`, so each
// scenario gets a fresh vm context with a minimal cookie-jar document mock.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const SRC = fs.readFileSync('docs/programs.js', 'utf8');

function makeContext(cookieJar) {
  const jar = cookieJar || {};
  const document = {
    get cookie() {
      return Object.entries(jar).map(([k, v]) => `${k}=${v}`).join('; ');
    },
    set cookie(raw) {
      const [pair, ...attrs] = String(raw).split('; ');
      const eq = pair.indexOf('=');
      const name = pair.slice(0, eq);
      const value = pair.slice(eq + 1);
      const maxAge = attrs.find((a) => a.toLowerCase().startsWith('max-age='));
      if (maxAge && Number(maxAge.slice('max-age='.length)) <= 0) {
        delete jar[name];
      } else {
        jar[name] = value;
      }
    },
  };
  const context = { window: {}, document };
  vm.createContext(context);
  vm.runInContext(SRC, context);
  return { P: context.window.ProgramRegistry, jar };
}

const LABELS = ['חבר', 'חבר שלי', 'HOT', 'מפתח דיסקונט', 'GiftCard max'];
const COOKIE = 'icc_selected_clubs';

// 1. No cookie: everything is selected by default.
{
  const { P } = makeContext();
  const r = P.build(LABELS);
  const sel = P.initialSelection(r);
  assert.deepStrictEqual(new Set(sel), new Set(r.selectableIds));
}

// 2. A subset change is written to the cookie and restored on the next "session".
{
  const { P, jar } = makeContext();
  const r = P.build(LABELS);
  const selected = new Set(['mcc', 'discount-key']);
  P.persistSelection(r, selected);
  assert(jar[COOKIE], 'cookie should be written for a subset selection');
  const stored = JSON.parse(decodeURIComponent(jar[COOKIE]));
  assert.deepStrictEqual(stored.sort(), ['discount-key', 'mcc']);
  // Stored value must contain only club identifiers: no names, no other data.
  assert(stored.every((id) => r.selectableIds.includes(id)));

  // New session over the same jar.
  const next = makeContext(arguments[0] === undefined ? jar : jar);
  const r2 = next.P.build(LABELS);
  const restored = next.P.initialSelection(r2);
  assert.deepStrictEqual(new Set(restored), new Set(['mcc', 'discount-key']));
}

// 3. Selecting every club is the default: the cookie is cleared, not frozen.
{
  const { P, jar } = makeContext();
  const r = P.build(LABELS);
  P.persistSelection(r, new Set(['mcc']));
  assert(jar[COOKIE]);
  P.persistSelection(r, new Set(r.selectableIds));
  assert.strictEqual(jar[COOKIE], undefined, 'cookie should be cleared when all clubs are selected');
}

// 4. A stale cookie whose clubs no longer exist falls back to all clubs and is removed.
{
  const { P, jar } = makeContext();
  jar[COOKIE] = encodeURIComponent(JSON.stringify(['gone-club', 'another-missing']));
  const r = P.build(LABELS);
  const sel = P.initialSelection(r);
  assert.deepStrictEqual(new Set(sel), new Set(r.selectableIds));
  assert.strictEqual(jar[COOKIE], undefined, 'stale cookie should be cleared');
}

// 5. A corrupted cookie is ignored safely and falls back to all clubs.
{
  const { P, jar } = makeContext();
  jar[COOKIE] = '%7Bnot-json';
  const r = P.build(LABELS);
  const sel = P.initialSelection(r);
  assert.deepStrictEqual(new Set(sel), new Set(r.selectableIds));
}

// 6a. A saved subset is restored exactly as chosen, even when the data has
//     since gained a club (the new club simply is not part of the saved choice).
{
  const { P, jar } = makeContext();
  jar[COOKIE] = encodeURIComponent(JSON.stringify(['mcc', 'discount-key']));
  const r = P.build([...LABELS, 'מועדון חדש']);
  const sel = P.initialSelection(r);
  assert.deepStrictEqual(new Set(sel), new Set(['mcc', 'discount-key']));
}

// 6b. A saved selection that still matches today's full club list normalizes
//     back to the default state (cookie cleared).
{
  const { P, jar } = makeContext();
  const r0 = P.build(LABELS);
  jar[COOKIE] = encodeURIComponent(JSON.stringify(r0.selectableIds));
  const r = P.build(LABELS);
  const sel = P.initialSelection(r);
  assert.strictEqual(jar[COOKIE], undefined, 'full-list cookie should be normalized away');
  assert.deepStrictEqual(new Set(sel), new Set(r.selectableIds));
}

// 7. Without a document (cookies unavailable) nothing throws and the default applies.
{
  const context = { window: {} };
  vm.createContext(context);
  vm.runInContext(SRC, context);
  const P = context.window.ProgramRegistry;
  const r = P.build(LABELS);
  const sel = P.initialSelection(r);
  assert.deepStrictEqual(new Set(sel), new Set(r.selectableIds));
  P.persistSelection(r, new Set(['mcc'])); // must not throw
  P.clearSavedSelection(); // must not throw
}

console.log('club selection persistence tests passed');
