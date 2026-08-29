import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

test('上传、点词翻译、刷新持久化并进入单词本', async ({ page }) => {
  await page.goto('/shelf')
  const filePath = path.join(import.meta.dirname, 'fixtures', 'Context Reading Sample.txt')
  const bookTitle = `Context Reading Sample ${Date.now()}`
  await page.getByTestId('book-upload').setInputFiles({
    name: `${bookTitle}.txt`,
    mimeType: 'text/plain',
    buffer: fs.readFileSync(filePath),
  })

  const card = page.getByTestId('book-card')
    .filter({ hasText: bookTitle })
    .filter({ hasText: '可以阅读' })
    .first()
  await expect(card).toContainText('可以阅读', { timeout: 20_000 })
  const openReader = card.getByRole('button', { name: '打开阅读' })
  await expect(openReader).toBeEnabled()
  await openReader.click()

  await expect(page.getByTestId('continuous-reader')).toBeVisible()
  await expect(page.getByText('上一章')).toHaveCount(0)
  await expect(page.getByText('The', { exact: true })).toBeVisible()

  const sidebarToggle = page.getByRole('button', { name: '切换目录' })
  const sidebarPerformance = await page.evaluate(async () => {
    const reader = document.querySelector<HTMLElement>('[data-testid="continuous-reader"]')!
    const toggle = document.querySelector<HTMLButtonElement>('[aria-label="切换目录"]')!
    const widthBefore = reader.getBoundingClientRect().width
    const started = performance.now()
    toggle.click()
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    return {
      duration: performance.now() - started,
      widthChange: Math.abs(reader.getBoundingClientRect().width - widthBefore),
    }
  })
  expect(sidebarPerformance.duration).toBeLessThan(500)
  expect(sidebarPerformance.widthChange).toBeLessThan(1)
  await expect(sidebarToggle).toHaveAttribute('aria-expanded', 'false')

  await page.getByRole('button', { name: 'company', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('The company faced an existential crisis.')
  await expect(page.getByTestId('contextual-meaning')).toHaveText('公司')
  await page.getByTestId('save-translation').click()
  await expect(page.locator('.inline-annotation')).toHaveText('（公司）')

  const existential = await page.getByRole('button', { name: 'existential', exact: true }).boundingBox()
  const crisis = await page.getByRole('button', { name: 'crisis', exact: true }).boundingBox()
  if (!existential || !crisis) throw new Error('没有找到词组拖选位置')
  await page.mouse.move(existential.x + 2, existential.y + existential.height / 2)
  await page.mouse.down()
  await page.mouse.move(crisis.x + crisis.width - 2, crisis.y + crisis.height / 2, { steps: 8 })
  await page.mouse.up()
  await expect(page.getByRole('dialog')).toContainText('existential crisis')
  await expect(page.getByTestId('contextual-meaning')).toHaveText('公司')
  await page.getByRole('button', { name: '取消' }).click()

  await page.reload()
  await expect(page.locator('.inline-annotation')).toHaveText('（公司）')
  await page.getByRole('link', { name: '单词本' }).click()

  const entry = page.getByTestId('vocabulary-entry').filter({ hasText: 'company' }).first()
  await expect(entry).toContainText('公司')
  await expect(entry).toContainText('The company faced an existential crisis.')
  await expect(entry).not.toContainText('Context Reading Sample')
})
