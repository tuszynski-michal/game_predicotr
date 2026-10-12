export async function waitForHistory(page) {
  await page.waitForFunction(
    () =>
      document.querySelector('select[aria-label="Ostatnie projekty"]')?.options
        .length > 1 ||
      [...document.querySelectorAll('button')].some((b) =>
        /^Kontynuuj:/.test(b.textContent),
      ),
  );
}
/** Supports the old pilot UI solely for cross-version update checks. */
export async function continueFromHistory(page) {
  await waitForHistory(page);
  const history = page.getByLabel('Ostatnie projekty', { exact: true });
  if (await history.count()) {
    const id = await history.evaluate((element) => element.options[1].value);
    await history.selectOption(id);
    await page.getByRole('button', { name: 'Kontynuuj', exact: true }).click();
  } else {
    await page.getByRole('button', { name: /^Kontynuuj:/ }).click();
  }
}
