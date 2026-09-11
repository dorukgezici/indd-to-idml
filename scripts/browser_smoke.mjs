// A local runtime smoke test. Full INDD import requires a real user document.
import { chromium } from 'playwright';
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.setContent('<title>INDD conversion runtime</title><p>Ready</p>');
  if (await page.title() !== 'INDD conversion runtime') {
    throw new Error('Unexpected browser response');
  }
  console.log('Headless Chromium runtime passed.');
} finally {
  await browser.close();
}
