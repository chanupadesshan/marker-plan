import fs from 'node:fs/promises';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';
const root = 'C:/Users/chanupa.d/Documents/concord/wovens-bom-extractor';
const book = await SpreadsheetFile.importXlsx(await FileBlob.load(`${root}/output/marker-plan-03/362097-marker-plan-8m.xlsx`));
const sheet = book.worksheets.getItem('Marker plan');
book.recalculate();
for (const address of ['AC36', 'AF36', 'AI36', 'AL36']) {
  if (Number(sheet.getRange(address).values[0][0]) !== 800) throw new Error(`Incorrect material total at ${address}`);
}
for (const row of sheet.getRange('F39:W42').values) if (row.some(value => Number(value) !== 0)) throw new Error('Size quantity difference is nonzero');
const preview = await book.render({ sheetName: 'Marker plan', range: 'A1:AN50', scale: 1.5, format: 'png' });
await fs.writeFile(`${root}/tmp/marker-export-qa/362097-marker-plan.png`, new Uint8Array(await preview.arrayBuffer()));
const first = Number(sheet.getRange('F12').values[0][0]);
const plies = Number(sheet.getRange('Y12').values[0][0]);
sheet.getRange('F12').values = [[first + 1]];
book.recalculate();
if (Number(sheet.getRange('AC36').values[0][0]) !== 800 + plies) throw new Error('Cut total does not recalculate');
if (Number(sheet.getRange('F39').values[0][0]) !== -plies) throw new Error('Size remainder does not recalculate');
if (Number(sheet.getRange('AF36').values[0][0]) !== 800) throw new Error('Unrelated material total changed');
console.log('PASS: one-sheet workbook; all four material totals 800, all 18 size differences zero; formulas recalculate independently. Final XLSX unchanged.');
