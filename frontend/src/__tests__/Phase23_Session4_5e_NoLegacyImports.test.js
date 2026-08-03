// Phase 23 Session 4.5e — legacy ScratchCard hygiene guard.
//
// Static checks that the legacy `frontend/src/games/ScratchCard.js`
// file is permanently gone, and that no source file imports from
// that path.  Keeps the 4.5c/4.5d "two implementations" bug from
// reappearing — any future PR that re-introduces the legacy file
// or imports it will be caught by CI.
const fs    = require("fs");
const path = require("path");

const SRC_ROOT = path.resolve(__dirname, "..");
const LEGACY_FILE = path.resolve(SRC_ROOT, "games/ScratchCard.js");
const LEGACY_FILE_JSX = path.resolve(SRC_ROOT, "games/ScratchCard.jsx");


function* walk(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const e of entries) {
    if (e.name === "node_modules" || e.name === "build"
            || e.name === ".cache") continue;
    const full = path.join(dir, e.name);
    if (e.isDirectory()) yield* walk(full);
    else if (/\.(js|jsx|ts|tsx)$/.test(e.name)) yield full;
  }
}


describe("Phase 23 Session 4.5e — no legacy ScratchCard", () => {
  test("legacy file does not exist on disk", () => {
    expect(fs.existsSync(LEGACY_FILE)).toBe(false);
    expect(fs.existsSync(LEGACY_FILE_JSX)).toBe(false);
  });

  test("no source file imports from games/ScratchCard", () => {
    const offenders = [];
    const RE = /from\s+['"][^'"]*games\/ScratchCard(?:['"]|\/)/;
    for (const f of walk(SRC_ROOT)) {
      // Skip this test file itself (it contains the regex string).
      if (f === __filename) continue;
      const txt = fs.readFileSync(f, "utf8");
      if (RE.test(txt)) offenders.push(path.relative(SRC_ROOT, f));
    }
    expect(offenders).toEqual([]);
  });
});
