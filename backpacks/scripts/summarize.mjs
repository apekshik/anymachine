// Summarise check.json + verify_glb.json for all bags into Markdown (stdout).
import { readFileSync } from 'node:fs';

function readReport(bag, name) {
  return JSON.parse(readFileSync(new URL(`../out/${bag}/${name}.json`, import.meta.url), 'utf8'));
}

function record(rows, tag, label, value, unit, aggregate, fails) {
  if (!rows.has(tag)) rows.set(tag, new Map());
  const metrics = rows.get(tag);
  const prev = metrics.get(label);
  metrics.set(label, {
    value: prev ? aggregate(prev.value, value) : value,
    unit,
    fails: fails || (prev?.fails ?? false),
  });
}

function format([label, { value, unit }]) {
  return unit === 'mm' ? `${label} ${value.toFixed(2)} mm` : `${label} ${value} triangle pair${value === 1 ? '' : 's'}`;
}

for (const bag of ['rucksack', 'daypack', 'rolltop']) {
  const r = readReport(bag, 'check');
  const v = readReport(bag, 'verify_glb');
  const sweeps = new Map();
  const pairs = new Map();
  for (const row of r.rows) {
    const [kind, tag] = row.tag.split(':');
    const results = kind === 'sweep' ? sweeps : pairs;
    for (const [part, metrics] of Object.entries(row.parts)) {
      if (part === '_self') {
        for (const [object, count] of Object.entries(metrics)) {
          record(results, tag, `self:${object}`, count, 'pairs', Math.max, count > 0);
        }
        continue;
      }
      const depth = metrics.max_pen_mm;
      record(results, tag, part, depth, 'mm', Math.max, depth > r.tol_mm);
      if ('min_z_mm' in metrics) {
        const height = metrics.min_z_mm;
        record(results, tag, `${part} min z`, height, 'mm', Math.min, height < -0.5);
      }
    }
  }

  console.log(`\n### ${bag}: ${r.states} states, tolerance ${r.tol_mm} mm, clamp max dev ${Math.max(...Object.values(r.clamp_max_dev_mm))} mm, GLB ${v.size_kb} KB, actions ${v.actions.join(', ')}, demo pose match median ${v.pose_match['demo@60'].median_mm} mm`);
  console.log('\n| sweep (others at default) | worst measurements |\n|---|---|');
  for (const [tag, measurements] of sweeps) {
    console.log(`| ${tag} | ${[...measurements].map(format).join('; ')} |`);
  }
  console.log('\n| coupled pair (5x5) | measurements outside limits |\n|---|---|');
  for (const [tag, measurements] of pairs) {
    const failures = [...measurements].filter(([, measurement]) => measurement.fails);
    console.log(`| ${tag} | ${failures.map(format).join('; ') || 'within limits'} |`);
  }
}
