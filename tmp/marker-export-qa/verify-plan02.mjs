import fs from 'node:fs/promises';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';
const root = 'C:/Users/chanupa.d/Documents/concord/wovens-bom-extractor';
const book = await SpreadsheetFile.importXlsx(await FileBlob.load(`${root}/output/marker-plan-02/355800-marker-plan-8m.xlsx`));
const sheet = book.worksheets.getItem('Marker plan');
book.recalculate();
for (const address of ['W33', 'Z33', 'AC33', 'AF33']) {
  if (Number(sheet.getRange(address).values[0][0]) !== 1410) throw new Error(`Incorrect material total at ${address}`);
}
for (const row of sheet.getRange('F36:O39').values) if (row.some(value => Number(value) !== 0)) throw new Error('Nonzero size difference');
const preview = await book.render({ sheetName: 'Marker plan', range: 'A1:AH47', scale: 1.5, format: 'png' });
await fs.writeFile(`${root}/tmp/marker-export-qa/355800-marker-plan.png`, new Uint8Array(await preview.arrayBuffer()));
console.log('PASS: shared sheet with four material groups; all cut totals 1410, all 10 size differences zero. Workbook unchanged.');
