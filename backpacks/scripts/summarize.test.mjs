import { execFileSync } from 'node:child_process';
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import assert from 'node:assert/strict';
import { test } from 'node:test';

test('reads reports relative to the script and uses the check thresholds and units', () => {
  const root = mkdtempSync(join(tmpdir(), 'anymachine-backpack-summary-'));
  try {
    const scripts = join(root, 'scripts');
    mkdirSync(scripts);
    const script = join(scripts, 'summarize.mjs');
    copyFileSync(new URL('./summarize.mjs', import.meta.url), script);
    for (const bag of ['rucksack', 'daypack', 'rolltop']) {
      const dir = join(root, 'out', bag);
      mkdirSync(dir, { recursive: true });
      const check = {
        states: 3,
        tol_mm: 2,
        clamp_max_dev_mm: { fill: 0 },
        rows: [
          {
            tag: 'pair:clipxroll',
            parts: {
              collar: { max_pen_mm: 1, min_z_mm: -0.25 },
              _self: { collar: 1 },
            },
          },
          {
            tag: 'pair:clipxroll',
            parts: {
              collar: { max_pen_mm: 3, min_z_mm: -0.75 },
              _self: { collar: 0 },
            },
          },
          {
            tag: 'pair:clear',
            parts: { collar: { max_pen_mm: 1, min_z_mm: -0.25 } },
          },
        ],
      };
      const verification = { size_kb: 1, actions: [], pose_match: { 'demo@60': { median_mm: 0 } } };
      writeFileSync(join(dir, 'check.json'), JSON.stringify(check));
      writeFileSync(join(dir, 'verify_glb.json'), JSON.stringify(verification));
    }

    const output = execFileSync(process.execPath, [script], { cwd: tmpdir(), encoding: 'utf8' });
    assert.match(output, /rucksack: 3 states, tolerance 2 mm/);
    assert.match(output, /\| clipxroll \| collar 3\.00 mm; collar min z -0\.75 mm; self:collar 1 triangle pair \|/);
    assert.match(output, /\| clear \| within limits \|/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
