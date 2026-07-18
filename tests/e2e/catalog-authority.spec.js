const { createHash } = require('node:crypto');
const path = require('node:path');
const { expect, test } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const PRODUCT_TITLE = '안전한 다중 이미지 상품';
const PRODUCT_DESCRIPTION = '분류와 거래 지역, 네 장의 이미지를 확인하는 상품입니다.';

function comparableOrigin(url) {
  const parsedURL = new URL(url);
  if (parsedURL.protocol === 'ws:') {
    return `http://${parsedURL.host}`;
  }
  if (parsedURL.protocol === 'wss:') {
    return `https://${parsedURL.host}`;
  }
  if (parsedURL.protocol === 'http:' || parsedURL.protocol === 'https:') {
    return parsedURL.origin;
  }
  return null;
}
function e2eUsername(testInfo) {
  const identity = [
    testInfo.project.name,
    testInfo.workerIndex,
    testInfo.repeatEachIndex,
    testInfo.retry,
    Date.now(),
  ].join(':');
  const suffix = createHash('sha256').update(identity).digest('hex').slice(0, 24);
  return `e2e_${suffix}`;
}


test('catalog authority renders four ordered local images accessibly', async (
  { page },
  testInfo,
) => {
  const applicationOrigin = new URL(testInfo.project.use.baseURL).origin;
  const responsesByURL = new Map();
  const remoteRuntimeURLs = [];
  const recordRuntimeURL = (url) => {
    const origin = comparableOrigin(url);
    if (origin !== null && origin !== applicationOrigin) {
      remoteRuntimeURLs.push(url);
    }
  };
  page.on('request', (request) => recordRuntimeURL(request.url()));
  page.on('websocket', (webSocket) => recordRuntimeURL(webSocket.url()));
  page.on('response', (response) => responsesByURL.set(response.url(), response));

  const username = e2eUsername(testInfo);
  const password = 'Browser-Authority-47!';
  await page.goto('/accounts/signup/');
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password1"]').fill(password);
  await page.locator('input[name="password2"]').fill(password);
  await page.getByRole('button', { name: '가입하기' }).click();
  await expect(page).toHaveURL(/\/account\/$/);

  await page.goto('/products/new/');
  await page.getByLabel('상품명').fill(PRODUCT_TITLE);
  await page.getByLabel('설명').fill(PRODUCT_DESCRIPTION);
  await page.getByLabel('가격').fill('25000');
  await page.getByLabel('분류').selectOption('OTHER');
  await page.getByLabel('거래 지역').selectOption('KR-11-680');
  const fixture = path.resolve(__dirname, 'fixtures/product.png');
  await page.getByLabel('상품 이미지').setInputFiles([
    fixture,
    fixture,
    fixture,
    fixture,
  ]);
  await page.getByRole('button', { name: '저장' }).click();

  await expect(page).toHaveURL(/\/products\/\d+\/$/);
  await expect(
    page.getByRole('heading', { level: 1, name: PRODUCT_TITLE }),
  ).toBeVisible();
  await expect(page.getByText('기타', { exact: true })).toBeVisible();
  await expect(page.getByText('서울특별시 강남구', { exact: true })).toBeVisible();
  await expect(page.getByText('판매 중', { exact: true })).toHaveCount(2);
  await expect(
    page.locator('.product-gallery__item > img'),
  ).toHaveCount(4);
  const galleryImages = page.locator('.product-gallery__item > img');

  await page.waitForLoadState('networkidle');
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(
      [...document.images].map((image) =>
        image.complete ? Promise.resolve() : image.decode(),
      ),
    );
  });
  const galleryImageState = await galleryImages.evaluateAll((images) =>
    images.map((image) => ({
      alt: image.alt,
      complete: image.complete,
      currentSrc: image.currentSrc,
      id: image.parentElement?.id,
      naturalHeight: image.naturalHeight,
      naturalWidth: image.naturalWidth,
    })),
  );
  expect(galleryImageState.map(({ id }) => id)).toEqual([
    'product-image-1',
    'product-image-2',
    'product-image-3',
    'product-image-4',
  ]);
  expect(galleryImageState.map(({ alt }) => alt)).toEqual([
    `${PRODUCT_TITLE} 이미지 1`,
    `${PRODUCT_TITLE} 이미지 2`,
    `${PRODUCT_TITLE} 이미지 3`,
    `${PRODUCT_TITLE} 이미지 4`,
  ]);
  expect(new Set(galleryImageState.map(({ currentSrc }) => currentSrc)).size).toBe(4);
  for (const image of galleryImageState) {
    expect(image.complete).toBe(true);
    expect(image.naturalWidth).toBeGreaterThan(0);
    expect(image.naturalHeight).toBeGreaterThan(0);
    expect(new URL(image.currentSrc).origin).toBe(applicationOrigin);

    const response = responsesByURL.get(image.currentSrc);
    expect(response, `missing response for ${image.currentSrc}`).toBeDefined();
    expect(response.ok(), `unsuccessful response for ${image.currentSrc}`).toBe(true);
    expect(response.headers()['content-type']).toMatch(/^image\//i);
  }
  const overflow = await page.evaluate(() => ({
    body: document.body.scrollWidth - document.body.clientWidth,
    document:
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  }));
  expect(overflow.body).toBeLessThanOrEqual(0);
  expect(overflow.document).toBeLessThanOrEqual(0);

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze();
  expect(results.violations).toEqual([]);

  await expect(page).toHaveScreenshot(
    `catalog-authority-${testInfo.project.name}.png`,
    {
      fullPage: true,
      mask: [page.getByText(username, { exact: true })],
    },
  );
  expect(remoteRuntimeURLs).toEqual([]);
});
