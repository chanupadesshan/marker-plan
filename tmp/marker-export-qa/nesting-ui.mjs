import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const browser = await chromium.launch({headless:true,channel:'msedge'});
try {
  const page = await browser.newPage();
  const errors=[]; page.on('pageerror',error=>errors.push(error.message));
  const request={table_length_m:'8',min_plies:10,time_limit_seconds:20,
    orders:[{label:'Test',size_rows:[{size:'S',quantity:'40'},{size:'M',quantity:'40'}]}],
    materials:[{material_code:'R1310',consumption:'2.09',max_plies:75,unit:'m'}]};
  let payload, posts=0;
  await page.addInitScript(()=>localStorage.setItem('auth_token','isolated-test-token'));
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    let json=[];
    if(path==='/api/auth/me') json={user:{full_name:'Reviewer',permissions:{marker_plan:'edit'}}};
    if(path.endsWith('/rerun-settings')) json={request,notes:[]};
    else if(path==='/api/marker-plans' && route.request().method()==='POST'){
      posts++; payload=route.request().postDataJSON(); json={id:'new-nesting-plan'};
    } else if(path.startsWith('/api/marker-plans/')) json={id:'old',status:'complete',saved:true,
      order_labels:['Test'],materials:[],summary:{},sizes:['S','M'],quantities:[40,40],total_quantity:80,request};
    await route.fulfill({json});
  });
  await page.goto('http://localhost:5173/marker-plans/old?rerun=1');
  await page.getByRole('heading',{name:'Run again',exact:true}).waitFor();
  await page.locator('summary').filter({hasText:'Verified nesting'}).click();
  await page.getByRole('button',{name:'Add verified marker',exact:true}).click();
  const length=page.getByLabel('Verified length (m), marker 1',{exact:true});
  await length.fill('8.1');
  await page.getByLabel('S count, marker 1, R1310',{exact:false}).fill('2');
  await page.getByLabel('M count, marker 1, R1310',{exact:false}).fill('2');
  const verify=page.getByRole('checkbox');
  await verify.check();
  await page.getByRole('button',{name:'Generate new plan',exact:true}).click();
  assert.equal(posts,0);
  await length.fill('7.3');
  assert.equal(await verify.isChecked(),false);
  await page.getByLabel('Width (cm, optional), marker 1',{exact:true}).fill('148');
  await page.getByLabel('Efficiency (%, optional), marker 1',{exact:true}).fill('91.35');
  await verify.check();
  await page.getByRole('button',{name:'Generate new plan',exact:true}).click();
  await page.waitForURL('**/marker-plans/new-nesting-plan');
  assert.equal(posts,1);
  assert.deepEqual(payload.materials[0].nesting_markers,[{label:null,length_m:'7.3',width_cm:'148',efficiency_percent:'91.35',verified:true,size_rows:[{size:'S',quantity:2},{size:'M',quantity:2}]}]);
  assert.deepEqual(errors,[]);
  console.log('PASS: verified nesting form validates length, requires re-verification after edits, and sends exact confirmed ratios and dimensions.');
} finally { await browser.close(); }
