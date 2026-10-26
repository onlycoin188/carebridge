// 데모 영상 녹화 (docs/demo_script.md 순서를 따라 화면만 녹화, 내레이션은 따로 입힘)
//   서버를 띄운 뒤:  node docs/record_demo.js [URL] [출력폴더]
//   기본값: http://localhost:7860, ./demo_video   → 출력폴더에 .webm 생성
// 앱 실행에는 필요 없는 녹화 도구라 playwright는 여기서만 쓴다.
const { chromium } = require("playwright");

const URL = process.argv[2] || "http://localhost:7860";
const OUT = process.argv[3] || "demo_video";
const W = 1440, H = 900;
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: { width: W, height: H }, deviceScaleFactor: 1,
    recordVideo: { dir: OUT, size: { width: W, height: H } },
  });
  const page = await ctx.newPage();
  const sample = (text) => page.locator("#samples button", { hasText: text }).first();
  const analyze = async () => {
    await page.click("#btn-analyze");
    await page.waitForSelector("#out:not([hidden]) .verdict", { timeout: 90000 });
  };
  const show = async (sel) => {
    await page.locator(sel).first().scrollIntoViewIfNeeded();
    await pause(2500);
  };

  // 0:00 첫 화면
  await page.goto(URL);
  await page.waitForSelector("#ai-status.ai", { timeout: 15000 });
  await pause(6000);

  // 0:20 베트남어 예시
  await sample("약 뱉음").click();
  await pause(5000);

  // 0:45 AI로 정리하기
  await analyze();
  await pause(5000);

  // 1:00 근거 형광펜: 관찰 항목을 차례로 클릭
  const items = page.locator("#out .obs .item, #out .risks .item");
  const n = Math.min(await items.count(), 3);
  for (let i = 0; i < n; i++) {
    await items.nth(i).click();
    await pause(3500);
  }

  // 2:00 권장 조치, 기록지 초안, 되묻기
  await show("#out [data-k='acts']");
  const box = page.locator("#out .acts input[type=checkbox]").first();
  if (await box.count()) await box.check();
  await show("#out [data-k='draft']");
  await show("#out [data-k='ask']");

  // 2:30 직접 쓴 메시지 번역
  await page.fill("#reply-ko", "");
  await page.type("#reply-ko", "넘어진 시간과 장소를 알려 주세요.", { delay: 60 });
  await page.click("#out .btn-reply");
  await page.waitForSelector("#out .reply-out:not([hidden])", { timeout: 60000 });
  await pause(5000);

  // 2:50 지시 무시 문장이 섞인 메모
  await page.click("#btn-edit");
  await pause(1000);
  await sample("지시 무시").click();
  await pause(4000);
  await analyze();
  await pause(7000);

  // 3:10 검토 완료 → 검토함
  await page.locator("#out .btn-save").scrollIntoViewIfNeeded();
  await pause(1000);
  await page.click("#out .btn-save");
  await pause(2000);
  await page.click("#tab-review");
  await pause(7000);

  await ctx.close();
  await browser.close();
  console.log(`녹화 완료: ${OUT}/`);
}

main().catch((e) => { console.error(e); process.exit(1); });
