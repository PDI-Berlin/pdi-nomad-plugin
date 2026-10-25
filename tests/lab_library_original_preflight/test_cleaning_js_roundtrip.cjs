const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const src = fs.readFileSync(
    'src/pdi_nomad_plugin/mbe/lab_library/static/app.js', 'utf8'
);

function section(start, end) {
    const a = src.indexOf(start);
    const b = src.indexOf(end, a + start.length);
    assert(a >= 0 && b > a, 'Missing JS section: ' + start);
    return src.slice(a, b);
}

const rows = [
    {
        medium: 'n-Butanol', time: '10', unit: 'min',
        temp: '23', agitation: 'Sonication',
        ref: {name: 'n-Butanol', lab_id: 'R001'},
        source: {name: 'n-Butanol', start_time: '2026-10-20T09:00:00'}
    },
    {
        medium: 'VE-H2O', time: '90', unit: 's',
        temp: '23', agitation: '', ref: {}, source: {}
    },
    {
        medium: 'N2 gun drying', time: '15', unit: 's',
        temp: '', agitation: '', ref: {}, source: {}
    }
];

const input = value => ({value: String(value ?? '')});

const mockRows = rows.map(r => {
    const fields = {
        '.cleaning-reagent': r.medium,
        '.cleaning-reagent-custom': '',
        '.cleaning-duration': r.time,
        '.cleaning-duration-unit': r.unit,
        '.cleaning-temperature': r.temp,
        '.cleaning-agitation': r.agitation,
        '.cleaning-comment': '',
        '.cleaning-start-time': r.source.start_time || '',
        '.cleaning-ref-name': r.ref.name,
        '.cleaning-ref-lab-id': r.ref.lab_id,
        '.cleaning-ref-reference': r.ref.reference
    };
    return {
        __recipeSourceStep: r.source,
        querySelector: selector => {
            assert(Object.hasOwn(fields, selector), 'Unexpected field: ' + selector);
            return input(fields[selector]);
        }
    };
});

const fields = {
    chemicalTreatmentName: 'Test cleaning',
    chemicalTreatmentType: 'Solvent cleaning',
    chemicalTreatmentDescription: 'Regression test',
    cleaningCustomTags: 'Custom tag',
    cleaningInstrumentReferences: JSON.stringify([
        {name: 'Ultrasonic Bath', lab_id: 'US001',
         reference: '../uploads/test/archive#/data'}
    ])
};

const document = {
    getElementById: id => {
        assert(Object.hasOwn(fields, id), 'Unexpected element: ' + id);
        return input(fields[id]);
    },
    querySelectorAll: selector => {
        if (selector.endsWith('.cleaning-step-row')) return mockRows;
        if (selector === '.cleaning-tag-option:checked')
            return [input('Cleaning'), input('Ultrasonic')];
        if (selector === '.cleaning-instrument:checked')
            return [input('US'), input('FB')];
        throw new Error('Unexpected selector: ' + selector);
    }
};

const context = {
    document,
    cleaningReagentName: step => step?.cleaning_reagents?.name || ''
};

const code = [
    section('const CLEANING_INSTRUMENTS =', 'function cleaningInstrumentCode('),
    section('function cleaningInstrumentCode(', 'function cleaningReferenceFromRow('),
    section('function cleaningReferenceFromRow(', 'function clearCleaningReferenceFields('),
    section('function readCleaningFields(data) {', 'function readAnnealingFields(data) {')
].join('\n');

vm.runInNewContext(code, context, {timeout: 2000});

const data = {tags: ['Cleaning', 'Existing tag']};
context.readCleaningFields(data);

assert.equal(data.method, 'Solvent cleaning');
assert.equal(data.duration, 705);
assert.equal(data.steps.length, 3);
assert.equal(data.steps[0].duration, 600);
assert.equal(data.steps[1].duration, 90);
assert.equal(data.steps[2].duration, 15);
assert.equal(data.steps[0].agitation, 'Sonication');
assert.equal(data.steps[0].cleaning_reagents.lab_id, 'R001');
assert.equal(data.steps[0].start_time, '2026-10-20T09:00:00');
assert.equal(data.steps[2].temperature, undefined);
assert.equal(data.steps[2].agitation, undefined);
assert(data.tags.includes('Existing tag'));
assert(data.tags.includes('Cleaning'));
assert(data.instruments.some(i => i.name === 'Ultrasonic Bath'));
assert(data.instruments.every(i =>
    Object.keys(i).length === 1 && i.name));

console.log('PASS: Cleaning JS serialization');
console.log('PASS: s/min conversion, optional temperature');
console.log('PASS: Agitation, reagents, generic instruments, tags');
console.log('PASS: Existing original step fields preserved');

if (process.env.CLEANING_TEST_JSON === "1") console.log(JSON.stringify(data));
