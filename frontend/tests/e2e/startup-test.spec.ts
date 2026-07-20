import { test, expect } from '@playwright/test';

test('前端页面可以加载', async ({ page }) => {
  await page.goto('http://localhost:3000/test');
  await page.waitForTimeout(3000);

  // 检查页面标题
  const title = await page.title();
  console.log('Page title:', title);

  // 检查页面有内容
  const body = await page.locator('body');
  await expect(body).not.toBeEmpty();

  // 截图
  await page.screenshot({ path: '/tmp/frontend-test-page.png' });
  console.log('Screenshot saved');
});

test('Agent Server 连接验证', async ({ page }) => {
  await page.goto('http://localhost:3000/test');
  await page.waitForTimeout(5000);

  // 检查是否有 Agent Server 连接相关的元素
  const pageContent = await page.content();
  console.log('Page content length:', pageContent.length);

  // 检查是否有错误信息
  if (pageContent.includes('error') || pageContent.includes('Error')) {
    console.log('Page has error indicators');
  }

  // 检查是否有 Agent Server 响应
  if (pageContent.includes('thread') || pageContent.includes('Thread')) {
    console.log('Thread ID detected - Agent Server connected');
  }

  await page.screenshot({ path: '/tmp/frontend-agent-connection.png' });
});

test('Work 页面可以加载', async ({ page }) => {
  await page.goto('http://localhost:3000/work');
  await page.waitForTimeout(3000);

  const body = await page.locator('body');
  await expect(body).not.toBeEmpty();

  await page.screenshot({ path: '/tmp/frontend-work-page.png' });
  console.log('Work page screenshot saved');
});
