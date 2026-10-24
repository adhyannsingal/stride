import assert from 'node:assert/strict'
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const browser=await chromium.launch({headless:true}), page=await browser.newPage({reducedMotion:'reduce'})
const button=name=>page.getByRole('button',{name,exact:true})
try {
 for(let i=0;i<5;i++) {
  await page.goto('http://127.0.0.1:8443/');await button('Open STRIDE').click();await button('Settings').click()
  await page.getByLabel('Session ID',{exact:true}).fill(`recovery-${i}`);await page.getByLabel('Session token',{exact:true}).fill(`recovery-token-${i}`)
  await button('Connect backend').click();await page.getByText(`Connected to backend session recovery-${i}.`).waitFor();await button('Guidance').click()
  if([1,2,3].includes(i)){await button('Start').click();await button('Stop awareness').waitFor()}
  if(i===2){await button('Pause').click();await button('Resume').waitFor()}
  const target=['start','pause','resume','stop','start'][i], requests=[];let dropped=false,release
  const hold=new Promise(r=>release=r)
  await page.route('**/vision',async route=>{
   const body=route.request().postDataJSON();requests.push(body)
   if(!dropped&&body.action===target){dropped=true;if(i!==2)await route.fetch();if(i===4){await hold;await route.fulfill({status:200,contentType:'application/json',body:'{}'})}else await route.abort('failed')}
   else await route.continue()
  })
  await button(['Start','Pause','Resume','Stop awareness','Start'][i]).click()
  if(i===4){await button('Stop awareness').waitFor();await button('Stop awareness').click();release()}
  else {await button('Retry awareness command').waitFor();await button(i===3?'Retry awareness command':'Stop awareness').click()}
  await page.getByText('Awareness stopped for this session.').waitFor()
  await page.waitForFunction(()=>![...document.querySelectorAll('button')].some(b=>b.textContent==='Retry awareness command'))
  if(i!==4){const a=requests.filter(r=>r.action===target);assert.equal(a.length,2);assert.deepEqual(a[0],a[1])}
  assert.equal(await button('Start').count(),0);await page.unroute('**/vision')
  console.log('PASS recovery:', ['lost successful Start → Stop','lost successful Pause → Stop','undelivered Resume → Stop','lost successful Stop → exact-ID retry','Stop queued during Start'][i])
 }
 console.log('5 network recovery browser regressions passed against actual FastAPI')
}finally{await browser.close()}
