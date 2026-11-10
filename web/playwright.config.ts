import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir:'./tests', workers:1, fullyParallel:false, timeout:120000,
  reporter:[['list'],['json',{outputFile:process.env.RECONCILE_BROWSER_REPORT||'/tmp/reconcile-browser/acceptance-results.json'}]],
  use:{baseURL:'http://127.0.0.1:18000',headless:true,viewport:{width:1440,height:1000},trace:'off',screenshot:'only-on-failure'},
});
