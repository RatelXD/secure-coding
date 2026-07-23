const { expect, test } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

test('home satisfies the responsive visual and accessibility contract', async (
  { page },
  testInfo,
) => {
  const applicationOrigin = new URL(testInfo.project.use.baseURL).origin;
  const remoteRuntimeURLs = [];

  const recordRemoteRuntimeURL = (url) => {
    const parsedURL = new URL(url);
    let comparableOrigin = parsedURL.origin;
    if (parsedURL.protocol === 'ws:' || parsedURL.protocol === 'wss:') {
      const httpProtocol = parsedURL.protocol === 'wss:' ? 'https:' : 'http:';
      comparableOrigin = `${httpProtocol}//${parsedURL.host}`;
    }
    if (
      ['http:', 'https:', 'ws:', 'wss:'].includes(parsedURL.protocol) &&
      comparableOrigin !== applicationOrigin
    ) {
      remoteRuntimeURLs.push(url);
    }
  };

  page.on('request', (request) => recordRemoteRuntimeURL(request.url()));
  page.on('websocket', (webSocket) =>
    recordRemoteRuntimeURL(webSocket.url()),
  );

  const settleResources = async () => {
    await page.waitForLoadState('networkidle');
    await page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all(
        [...document.images].map((image) =>
          image.complete ? Promise.resolve() : image.decode(),
        ),
      );
    });
  };

  const response = await page.goto('/');
  expect(response).not.toBeNull();
  expect(response.ok()).toBe(true);
  await expect(page).toHaveURL(/\/$/);
  await expect(
    page.getByRole('main').getByRole('heading', {
      level: 1,
      name: '필요한 건 받고, 쓰지 않는 건 건네세요',
      exact: true,
    }),
  ).toBeVisible();
  const firstCategory = page.getByRole('navigation', { name: '상품 카테고리' }).getByRole('link').first();
  const categoryResponse = await page.goto(await firstCategory.getAttribute('href'));
  expect(categoryResponse.ok()).toBe(true);
  await expect(page.getByRole('heading', { level: 1, name: '중고 상품 둘러보기' })).toBeVisible();

  await page.goto('/');
  await page.getByRole('link', { name: '상품 검색' }).click();
  await expect(page).toHaveURL(/\/products\/$/);

  await page.goto('/');
  await settleResources();

  const overflow = await page.evaluate(() => ({
    body: document.body.scrollWidth - document.body.clientWidth,
    document:
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  }));
  expect(overflow.body).toBeLessThanOrEqual(0);
  expect(overflow.document).toBeLessThanOrEqual(0);

  await page.keyboard.press('Tab');
  const skipLink = page.getByRole('link', { name: '본문으로 바로가기' });
  await expect(skipLink).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('main')).toBeFocused();

  await page.goto('/');
  await settleResources();
  await page.keyboard.press('Tab');
  await page.keyboard.press('Tab');
  const brandLink = page.getByRole('link', { name: '주거니 받거니 홈' });
  await expect(brandLink).toBeFocused();
  const focusStyle = await brandLink.evaluate((element) => {
    const style = window.getComputedStyle(element);
    return {
      outlineStyle: style.outlineStyle,
      outlineWidth: Number.parseFloat(style.outlineWidth),
    };
  });
  expect(focusStyle.outlineStyle).not.toBe('none');
  expect(focusStyle.outlineWidth).toBeGreaterThanOrEqual(2);

  if (testInfo.project.name === 'chromium-mobile') {
    const mobileHome = page
      .getByRole('navigation', { name: '모바일 주요 메뉴' })
      .getByRole('link', { name: '홈', exact: true });
    await mobileHome.focus();
    await expect(mobileHome).toBeFocused();
  } else {
    await page.keyboard.press('Tab');
    await expect(
      page.getByRole('navigation', { name: '주요 메뉴' }).getByRole('link', {
        name: '홈',
        exact: true,
      }),
    ).toBeFocused();
  }

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze();
  expect(results.violations).toEqual([]);

  await expect(page).toHaveScreenshot(
    `home-${testInfo.project.name}.png`,
    { mask: [page.locator(".latest-products .product-grid")] },
  );
  expect(remoteRuntimeURLs).toEqual([]);
});
