'use strict';
const assert = require('node:assert/strict');
const math = require('../src/pdi_nomad_plugin/mbe/substrate_intake/static/intake_ysz_dopants.js');
const v = math.yszFromOxideFraction(0.08);
assert.equal(v.oxide_mol_percent, 8);
assert.ok(Math.abs(v.atomic_fraction - 0.05063291139240506) < 1e-14);
assert.ok(Math.abs(v.mass_fraction - 0.1082328976107106) < 1e-14);
assert.ok(Math.abs(v.cation_fraction - 0.14814814814814814) < 1e-14);
assert.ok(Math.abs(math.oxideFractionFromAtomicFraction(v.atomic_fraction) - 0.08) < 1e-14);
assert.ok(Math.abs(math.oxideFractionFromMassFraction(v.mass_fraction) - 0.08) < 1e-14);
for (const bad of [NaN, Infinity, -0.01, 1, undefined]) {
    assert.throws(() => math.yszFromOxideFraction(bad));
}
assert.throws(() => math.oxideFractionFromAtomicFraction(0.7));
console.log('PASS: 8YSZ 8 mol-% Y2O3, atomic/mass fractions and inverses');
