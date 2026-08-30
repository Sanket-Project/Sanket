import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const scriptsDir = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(scriptsDir, "..");
const assetsDir = resolve(projectRoot, "public", "assets");
const logoSvg = await readFile(resolve(projectRoot, "public", "sanket-logo.svg"), "utf8");
const logoDataUrl = `data:image/svg+xml;base64,${Buffer.from(logoSvg).toString("base64")}`;

const launchBrowser = async () => {
  const attempts = [{}, { channel: "chrome" }, { channel: "msedge" }];
  let lastError;

  for (const options of attempts) {
    try {
      return await chromium.launch({ headless: true, ...options });
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError;
};

const browser = await launchBrowser();

try {
  const socialContext = await browser.newContext({
    viewport: { width: 1200, height: 630 },
    deviceScaleFactor: 2,
  });
  const socialPage = await socialContext.newPage();

  await socialPage.setContent(`
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <style>
          @import url("https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap");

          * { box-sizing: border-box; }
          html, body { margin: 0; width: 1200px; height: 630px; overflow: hidden; }
          body {
            background: #fbf7ef;
            color: #16292b;
            font-family: "IBM Plex Sans", sans-serif;
          }
          .cover {
            display: grid;
            grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr);
            gap: 64px;
            width: 100%;
            height: 100%;
            padding: 62px 66px 58px;
          }
          .copy { display: flex; min-width: 0; flex-direction: column; }
          .wordmark {
            display: flex;
            align-items: center;
            gap: 13px;
            color: #03363d;
            font-family: "IBM Plex Mono", monospace;
            font-size: 17px;
            font-weight: 600;
            letter-spacing: 0.28em;
          }
          .brand-icon {
            display: block;
            width: 36px;
            height: 36px;
          }
          h1 {
            max-width: 590px;
            margin: auto 0 23px;
            font-family: "DM Serif Display", Georgia, serif;
            font-size: 65px;
            font-weight: 400;
            letter-spacing: -0.035em;
            line-height: 0.98;
          }
          .descriptor {
            margin: 0;
            color: #03363d;
            font-family: "IBM Plex Mono", monospace;
            font-size: 13px;
            font-weight: 500;
            letter-spacing: 0.12em;
            line-height: 1.6;
            text-transform: uppercase;
          }
          .console {
            align-self: center;
            min-width: 0;
            border: 1px solid rgba(58, 48, 34, 0.13);
            border-radius: 22px;
            background: #fffdf8;
            overflow: hidden;
          }
          .console-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            min-height: 54px;
            padding: 0 20px;
            border-bottom: 1px solid rgba(58, 48, 34, 0.13);
            font-family: "IBM Plex Mono", monospace;
            font-size: 11px;
            letter-spacing: 0.04em;
          }
          .live { display: flex; align-items: center; gap: 8px; color: #03363d; }
          .live::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: #03363d; }
          .console-body { padding: 22px; }
          .eyebrow {
            margin: 0 0 12px;
            color: #03363d;
            font-family: "IBM Plex Mono", monospace;
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 0.14em;
            text-transform: uppercase;
          }
          .question { margin: 0; font-size: 17px; font-weight: 600; line-height: 1.45; }
          .answer {
            margin: 18px 0 20px;
            padding: 17px 18px;
            border-radius: 14px;
            background: #03363d;
            color: #fbf7ef;
          }
          .answer strong { display: block; margin-bottom: 6px; font-size: 21px; font-weight: 600; }
          .answer span { font-size: 13px; line-height: 1.5; opacity: 0.78; }
          .signals { display: grid; gap: 9px; }
          .signal {
            display: grid;
            grid-template-columns: 8px minmax(0, 1fr) auto;
            align-items: center;
            gap: 10px;
            padding: 11px 12px;
            border: 1px solid rgba(58, 48, 34, 0.13);
            border-radius: 14px;
            font-size: 12px;
          }
          .signal::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: #03363d; }
          .signal b { font-family: "IBM Plex Mono", monospace; font-size: 11px; font-weight: 600; }
          .foot {
            margin-top: 20px;
            color: rgba(22, 41, 43, 0.62);
            font-family: "IBM Plex Mono", monospace;
            font-size: 10px;
            letter-spacing: 0.09em;
            text-transform: uppercase;
          }
        </style>
      </head>
      <body>
        <main class="cover">
          <section class="copy">
            <div class="wordmark"><img class="brand-icon" src="${logoDataUrl}" alt="" />SANKET</div>
            <h1>Stop guessing demand.<br />Forecast every SKU.</h1>
            <p class="descriptor">Demand intelligence for supply-chain teams</p>
          </section>
          <section class="console" aria-label="Sanket console preview">
            <div class="console-head"><span>app.sanket.ai/console</span><span class="live">Live</span></div>
            <div class="console-body">
              <p class="eyebrow">Ask Sanket</p>
              <p class="question">SKU-8820 has four days of cover. What should I reorder?</p>
              <div class="answer"><strong>Reorder 1,800 units.</strong><span>Covers the lead-time shift and the demand pull in the north zone.</span></div>
              <div class="signals">
                <div class="signal"><span>Demand signal</span><b>+34%</b></div>
                <div class="signal"><span>Supplier lead time</span><b>+6d</b></div>
                <div class="signal"><span>Decision confidence</span><b>89%</b></div>
              </div>
              <div class="foot">Evidence visible · decision traceable</div>
            </div>
          </section>
        </main>
      </body>
    </html>
  `, { waitUntil: "networkidle" });
  await socialPage.evaluate(() => document.fonts.ready);
  await socialPage.screenshot({
    path: resolve(assetsDir, "og-cover.png"),
    scale: "css",
  });
  await socialContext.close();

  const iconContext = await browser.newContext({
    viewport: { width: 180, height: 180 },
    deviceScaleFactor: 1,
  });
  const iconPage = await iconContext.newPage();
  await iconPage.setContent(`
    <!doctype html>
    <html>
      <head>
        <style>
          * { box-sizing: border-box; }
          html, body { margin: 0; width: 180px; height: 180px; overflow: hidden; background: #03363d; }
          img { display: block; width: 180px; height: 180px; }
        </style>
      </head>
      <body><img src="${logoDataUrl}" alt="" /></body>
    </html>
  `);
  await iconPage.locator("img").waitFor({ state: "visible" });
  await iconPage.screenshot({
    path: resolve(projectRoot, "public", "apple-touch-icon.png"),
    scale: "css",
  });
  await iconContext.close();
} finally {
  await browser.close();
}

console.log("Rendered public/assets/og-cover.png (1200x630) and public/apple-touch-icon.png (180x180).");
