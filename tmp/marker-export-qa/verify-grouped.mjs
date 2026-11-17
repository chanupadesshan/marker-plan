import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';
const root = 'C:/Users/chanupa.d/Documents/concord/wovens-bom-extractor';
const job = JSON.parse(await fs.readFile(`${root}/output/optimization-benchmark/saved-plan.json`, 'utf8'));
const book = await SpreadsheetFile.importXlsx(await FileBlob.load(`${root}/output/optimization-benchmark/358449-359259-improved-marker-plan.xlsx`));
const sheet = book.worksheets.getItem('Marker plan');
const col = index => { let text = ''; for (let n=index+1;n;n=Math.floor((n-1)/26)) text=String.fromCharCode(65+(n-1)%26)+text; return text; };
const groups = job.materials.map(material => {
  const found = new Map();
  for (const lay of material.result.lays) {
    const key = JSON.stringify(lay.counts);
    if (!found.has(key)) found.set(key, { id: lay.marker_id, plies: 0, lays: [] });
    const group = found.get(key); group.plies += lay.plies; group.lays.push(lay);
  }
  return [...found.values()];
});
const slots = Math.max(12,job.sizes.length), pliesStart = 6+slots, usage = pliesStart+job.materials.length;
const layCountCol = usage + job.materials.length*3;
const total = 11 + groups.reduce((n,group)=>n+1+Math.max(4,group.length+2),0);
book.recalculate();
let firstRow = 12;
for (let mi=0;mi<groups.length;mi++) {
  for (const [offset,group] of groups[mi].entries()) {
    const row = firstRow+offset;
    assert.ok(String(sheet.getRange(`A${row}`).values[0][0]).endsWith(group.id));
    assert.equal(Number(sheet.getRange(`${col(pliesStart+mi)}${row}`).values[0][0]),group.plies);
    assert.equal(Number(sheet.getRange(`${col(layCountCol)}${row}`).values[0][0]),group.lays.length);
    assert.equal(String(sheet.getRange(`${col(layCountCol+1)}${row}`).values[0][0]),group.lays.map(lay=>`L${lay.number}: ${lay.plies}`).join('; '));
  }
  assert.equal(Number(sheet.getRange(`${col(usage+mi*3)}${total}`).values[0][0]),job.total_quantity);
  firstRow += Math.max(4,groups[mi].length+2)+1;
}
assert.equal(Number(sheet.getRange(`${col(layCountCol)}${total}`).values[0][0]),job.materials.reduce((n,m)=>n+m.result.lay_count,0));
for(const row of sheet.getRange(`F${total+3}:${col(4+job.sizes.length)}${total+2+job.materials.length}`).values) assert.ok(row.every(value=>Number(value)===0));
const preview = await book.render({ sheetName: 'Marker plan', range: `A1:${col(layCountCol+1)}${total+2*job.materials.length+6}`, scale: 1.5, format: 'png' });
await fs.writeFile(`${root}/tmp/marker-export-qa/grouped-marker-plan.png`,new Uint8Array(await preview.arrayBuffer()));
console.log('PASS: all unique marker groups, summed plies and lay breakdowns preserved, cut totals 2625 per material and zero size differences.');
