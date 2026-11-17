import fs from 'node:fs/promises';
import { chromium } from 'playwright';
const root = 'C:/Users/chanupa.d/Documents/concord/wovens-bom-extractor';
const env = Object.fromEntries((await fs.readFile(`${root}/.env`, 'utf8')).split(/\r?\n/).map(line => {
  const match = line.match(/^([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*)$/);
  return match ? [match[1], match[2].replace(/^(['"])(.*)\1$/, '$2')] : ['', ''];
}));
let options = { headless: true };
try { await fs.access(chromium.executablePath()); } catch { options.channel = 'msedge'; }
const browser = await chromium.launch(options);
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1050 }, acceptDownloads: true });
  const response = await page.request.post('http://127.0.0.1:8000/api/auth/login', {
    data: { email: env.ADMIN_EMAIL || env.admin_email, password: env.ADMIN_PASSWORD || env.admin_password },
  });
  if (!response.ok()) throw new Error('Test login failed');
  const { token } = await response.json();
  await page.addInitScript(value => { if (location.hostname === 'localhost') localStorage.setItem('auth_token', value); }, token);
  await page.goto('http://localhost:5173');
  await page.getByRole('tab', { name: 'Marker Plan', exact: true }).click();
  await page.getByRole('heading', { name: 'Saved plans', exact: true }).waitFor();
  const row = page.getByRole('row').filter({ hasText: '361061' }).first();
  await row.getByRole('button', { name: 'Open', exact: true }).click();
  await page.getByText('Saved to database', { exact: true }).waitFor();
  const material = page.locator('.saved-plan-opened .plan-material').first();
  if (await material.locator('.plan-details[open], .plan-outcome, .status').count()) throw new Error('Result message is still colored or expanded');
  await material.screenshot({ path: `${root}/tmp/marker-export-qa/neutral-material-ui.png` });
  await page.locator('.saved-plans > .panel').screenshot({ path: `${root}/tmp/marker-export-qa/history-ui.png` });
  const [download] = await Promise.all([
    page.waitForEvent('download'), row.getByRole('link', { name: 'Download Excel', exact: true }).click(),
  ]);
  await download.saveAs(`${root}/tmp/marker-export-qa/ui-download.xlsx`);
  if (await download.failure()) throw new Error(await download.failure());
  console.log('PASS: Marker Plan history opens the saved result and downloads Excel through the browser.');
  await page.reload();
  await page.getByRole('tab', { name: 'Marker Plan', exact: true }).click();
  await page.getByRole('row').filter({ hasText: '361061' }).first().waitFor();
  console.log('PASS: saved history is available after refreshing, with no materials or POs selected.');
} finally { await browser.close(); }
