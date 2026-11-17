import fs from 'node:fs/promises';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';
const root = 'C:/Users/chanupa.d/Documents/concord/wovens-bom-extractor';
const job = JSON.parse(await fs.readFile(`${root}/output/marker-plan-multiple-po/saved-plan.json`, 'utf8'));
const book = await SpreadsheetFile.importXlsx(await FileBlob.load(`${root}/output/marker-plan-multiple-po/358449-359259-marker-plan-8m.xlsx`));
const sheet = book.worksheets.getItem('Marker plan');
const col = index => { let text = ''; for (let n = index + 1; n; n = Math.floor((n - 1) / 26)) text = String.fromCharCode(65 + (n - 1) % 26) + text; return text; };
const slots = Math.max(12, job.sizes.length);
const usage = 6 + slots + job.materials.length;
const totalRow = 11 + job.materials.reduce((sum, material) => sum + 1 + Math.max(4, material.result.lays.length + 2), 0);
book.recalculate();
for (let i = 0; i < job.materials.length; i++) {
  const address = `${col(usage + 3 * i)}${totalRow}`;
  if (Number(sheet.getRange(address).values[0][0]) !== 2625) throw new Error(`Incorrect combined cut total ${address}`);
}
for (const row of sheet.getRange(`F${totalRow + 3}:${col(4 + job.sizes.length)}${totalRow + 2 + job.materials.length}`).values) {
  if (row.some(value => Number(value) !== 0)) throw new Error('Combined size quantity difference is nonzero');
}
const top = sheet.getRange('D1:F7').values.flat().map(String);
if (!top.includes('358449') || !top.includes('359259')) throw new Error('Missing PO in workbook');
const preview = await book.render({ sheetName: 'Marker plan', range: `A1:${col(usage + 3 * job.materials.length - 1)}${totalRow + job.materials.length * 2 + 6}`, scale: 1.5, format: 'png' });
await fs.writeFile(`${root}/tmp/marker-export-qa/multiple-po-marker-plan.png`, new Uint8Array(await preview.arrayBuffer()));
console.log('PASS: both contracts appear in one worksheet; each material cuts 2625 garments; every combined size difference is zero.');
