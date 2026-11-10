import { test, expect, Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs';
import path from 'node:path';
const samples=path.resolve(import.meta.dirname,'../../backend/reconcile/demo_samples');
const output=process.env.RECONCILE_BROWSER_ARTIFACTS||'/tmp/reconcile-browser/local-completion';

async function finish(page:Page) {
  await expect.poll(()=>page.url().split('/invoices/')[1],{timeout:15000}).toBeTruthy();
  const id=page.url().split('/invoices/')[1];
  await expect.poll(async()=>{
    const r=await page.request.get('/api/invoices/'+id);
    return (await r.json()).run.state;
  },{timeout:45000}).toBe('completed');
  const detail=await (await page.request.get('/api/invoices/'+id)).json();
  await expect(page.getByText('RECOMMENDATION · VERSION '+detail.decision.version,{exact:true})).toBeVisible();
  return detail;
}
async function upload(page:Page,name:string) {
  await page.goto('/');
  await page.getByLabel('Invoice PDF',{exact:true}).setInputFiles(path.join(samples,name+'.pdf'));
  return finish(page);
}
async function screenshot(page:Page,name:string) {
  await page.screenshot({path:path.join(output,name+'.png'),fullPage:true});
}

test('Local user journey: login, source evidence, approval, human correction, MiniLM and ledger',async({page})=>{
  fs.mkdirSync(output,{recursive:true});
  const errors:string[]=[];
  page.on('pageerror',e=>errors.push(e.message));
  await expect.poll(async()=>{try{return (await page.request.get('/health/ready')).status();}catch{return 0;}},{timeout:45000}).toBe(200);
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible();
  const loginScan=await new AxeBuilder({page}).analyze();
  expect(loginScan.violations.filter(v=>['serious','critical'].includes(v.impact||''))).toEqual([]);
  await page.getByLabel('Email address').fill('browser@test.invalid');
  await page.getByLabel('Password',{exact:true}).fill('browser-test-only-password-42');
  await page.getByRole('button',{name:'Sign in to workspace'}).click();
  await expect(page.getByRole('heading',{name:'Clarity before approval.'})).toBeVisible();
  await expect(page.getByText('Processing worker online',{exact:true})).toBeVisible();
  await expect(page.getByText('Your invoice history starts here',{exact:true})).toBeVisible();
  await screenshot(page,'01-workspace');
  let d=await upload(page,'happy');
  expect(d.decision.bucket).toBe('accept');
  await page.getByRole('button',{name:'View printed row'}).first().click();
  await expect(page.locator('rect.highlight')).toBeVisible();
  await screenshot(page,'02-evidence-and-checks');
  await page.getByRole('button',{name:'Approve invoice',exact:true}).click();
  await expect.poll(async()=>(await (await page.request.get('/api/invoices/'+d.invoice.id)).json()).invoice.review_state).toBe('approved');
  d=await upload(page,'missing-pack');
  expect(d.decision.bucket).toBe('human_review');
  await page.getByRole('button',{name:'Review or correct fields'}).click();
  await page.getByLabel('Verified items per box').fill('100');
  await page.getByLabel('Evidence and reason for these changes').fill('Verified 100 gloves per box against the approved supplier specification.');
  await screenshot(page,'03-human-review');
  await page.getByRole('button',{name:'Save corrections and recheck'}).click();
  await expect.poll(async()=>(await (await page.request.get('/api/invoices/'+d.invoice.id)).json()).decision.version,{timeout:30000}).toBe(2);
  let updated=await (await page.request.get('/api/invoices/'+d.invoice.id)).json();
  expect(updated.decision.bucket).toBe('accept');
  expect(updated.extraction.fields.lines[0].description.value).not.toContain('100');
  await expect(page.getByText('RECOMMENDATION · VERSION 2',{exact:true})).toBeVisible();
  await screenshot(page,'04-revalidated-decision');
  d=await upload(page,'semantic');
  expect(d.decision.bucket).toBe('human_review');
  const c=d.decision.retrieval.lines[0].candidates[0];
  expect(c.sku).toBe('GLV-M');
  await page.getByRole('button',{name:'Review or correct fields'}).click();
  await page.getByLabel('Confirm a matching order item').selectOption(c.po_line_id);
  await page.getByLabel('Evidence and reason for these changes').fill('Compared material and size with the printed invoice and approved purchase order specification.');
  await page.getByRole('button',{name:'Save corrections and recheck'}).click();
  await expect.poll(async()=>(await (await page.request.get('/api/invoices/'+d.invoice.id)).json()).decision.version,{timeout:30000}).toBe(2);
  updated=await (await page.request.get('/api/invoices/'+d.invoice.id)).json();
  expect(updated.decision.bucket).toBe('accept');
  await page.getByRole('link',{name:'Purchase orders',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Purchase order ledger.'})).toBeVisible();
  await screenshot(page,'05-current-ledger');
  await page.getByRole('link',{name:'Evaluation & scope',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Indian GST invoice extraction — primary benchmark',exact:true})).toBeVisible();
  await expect(page.locator('section.panel').first()).toContainText('197');
  await screenshot(page,'05-indian-gst-benchmark');
  await page.getByRole('link',{name:'Invoice activity',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Invoice activity',exact:true})).toBeVisible();
  await page.getByLabel('Search invoices').fill('SH-DEMO-HAPPY');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await page.getByLabel('Search invoices').fill('');
  await page.setViewportSize({width:390,height:844});
  await screenshot(page,'06-mobile');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)).toBe(false);
  const scan=await new AxeBuilder({page}).analyze();
  fs.writeFileSync(path.join(output,'accessibility.json'),JSON.stringify({login:loginScan.violations,workspace:scan.violations},null,2));
  expect(scan.violations.filter(v=>['serious','critical'].includes(v.impact||''))).toEqual([]);
  expect(errors).toEqual([]);
  await page.getByRole('button',{name:'Sign out',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Welcome back'})).toBeVisible();
  expect((await page.request.get('/api/invoices')).status()).toBe(401);
});
