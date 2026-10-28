const {chromium}=require('../frontend/node_modules/@playwright/test');
(async()=>{
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1920,height:1080}});
await page.goto('http://127.0.0.1:5173/review/size-recognition-preview.html');
await page.locator('input[type=file]').setInputFiles({name:'fixture.csv',mimeType:'text/csv',buffer:Buffer.from('fixture')});
await page.getByLabel('Size for code 2X').waitFor();
await page.screenshot({path:'tmp/size-recognition-desktop.png'});
console.log('Desktop', await page.getByRole('dialog').boundingBox());
for(const width of [375,768,1440]){
await page.setViewportSize({width,height:900});
console.log(width, await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,cards:[...document.querySelectorAll('select[aria-label^="Size for code"]')].every(e=>e.getBoundingClientRect().right<=innerWidth)})));
if(width===375)await page.screenshot({path:'tmp/size-recognition-mobile.png'});
}
await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
