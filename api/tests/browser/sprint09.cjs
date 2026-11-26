const assert = require("node:assert/strict");
const path = require("node:path");
const { chromium } = require("playwright");

const base = (process.env.ARIANO_TEST_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const email = process.env.ARIANO_TEST_ADMIN_EMAIL;
const password = process.env.ARIANO_TEST_ADMIN_PASSWORD;
const evidence = process.env.ARIANO_TEST_EVIDENCE_DIR;

async function run() {
  if (!email || !password) throw new Error("Defina ARIANO_TEST_ADMIN_EMAIL e ARIANO_TEST_ADMIN_PASSWORD.");
  const browser = await chromium.launch({ executablePath: process.env.ARIANO_CHROMIUM_PATH });
  try {
    const page = await browser.newPage({ viewport: { width: 1360, height: 980 } });
    const tokenResponse = page.waitForResponse((response) => response.url() === base + "/auth/login");
    await page.goto(base + "/app/");
    await page.locator("#auth-email").fill(email);
    await page.locator("#auth-password").fill(password);
    await page.getByRole("button", { name: "Entrar", exact: true }).click();
    const login = await tokenResponse;
    assert.equal(login.status(), 200);
    const { access_token: token } = await login.json();
    await page.locator("#overview-kpis .kpi").first().waitFor();
    const headers = { Authorization: `Bearer ${token}` };
    const tags = await (await page.request.get(base + "/tags", { headers })).json();
    const ml = tags.find((tag) => tag.code === "MACHINE_LEARNING");
    assert(ml, "O cenário requer a tag MACHINE_LEARNING do seed.");
    const nonce = Date.now();
    async function createDemand(label) {
      const response = await page.request.post(base + "/demands", {
        headers,
        data: { title: `${label} Sprint 09 ${nonce}`, tags: [{ tag_id: ml.id, type: "REQUIRED", weight: 1 }] },
      });
      assert.equal(response.status(), 201);
      return response.json();
    }
    async function capture(target, filename) {
      if (evidence) await target.screenshot({ path: path.join(evidence, filename) });
    }

    await page.locator("#nav-demands").click();
    await page.locator("#new-demand").click();
    await page.locator("#demand-title").fill("Validação de competência Sprint 09");
    await page.locator("#save-demand").click();
    await page.locator("#demand-form-message").getByText(/Selecione ao menos uma competência/).waitFor();
    await capture(page, "s09-validacao.png");
    await page.locator("#back-from-create").click();

    const first = await createDemand("Demanda A");
    const second = await createDemand("Demanda B");
    await page.locator("#refresh-demands").click();
    const row = (entry) => page.locator("#demand-rows tr").filter({ hasText: entry.title });
    const firstUrl = `${base}/demands/${first.id}`;
    let entered;
    let release;
    const intercepted = new Promise((resolve) => { entered = resolve; });
    const gate = new Promise((resolve) => { release = resolve; });
    const holdFirst = async (route) => {
      entered();
      await gate;
      await route.continue();
    };
    await page.route(firstUrl, holdFirst);
    await row(first).getByRole("button", { name: "Abrir" }).click();
    await intercepted;
    await row(second).getByRole("button", { name: "Abrir" }).click();
    await page.locator("#detail-title").getByText(second.title, { exact: true }).waitFor();
    const lateResponse = page.waitForResponse((response) => response.url() === firstUrl);
    release();
    await lateResponse;
    await page.waitForLoadState("networkidle");
    assert.equal(await page.locator("#detail-title").textContent(), second.title,
      "A resposta mais antiga substituiu a demanda escolhida por último.");
    await page.unroute(firstUrl, holdFirst);

    await page.locator("#run-ranking").click();
    await page.locator("#ranking-results button").first().waitFor();
    await capture(page.locator("#demand-detail-view"), "s09-ranking.png");
    await page.locator("#back-from-detail").click();
    await row(second).getByRole("button", { name: "Abrir" }).click();
    await page.locator("#ranking-results button").first().waitFor();

    // Sair do módulo com a consulta em andamento também encerra a navegação iniciada.
    await page.locator("#back-from-detail").click();
    let leaveEntered;
    let leaveRelease;
    const leaveIntercepted = new Promise((resolve) => { leaveEntered = resolve; });
    const leaveGate = new Promise((resolve) => { leaveRelease = resolve; });
    const holdDuringLeave = async (route) => {
      leaveEntered();
      await leaveGate;
      await route.continue();
    };
    await page.route(firstUrl, holdDuringLeave);
    await row(first).getByRole("button", { name: "Abrir" }).click();
    await leaveIntercepted;
    await page.locator("#nav-actors").click();
    await page.locator("#actors-section h1").waitFor();
    await page.locator("#nav-demands").click();
    await row(second).waitFor();
    const responseAfterLeave = page.waitForResponse((response) => response.url() === firstUrl);
    leaveRelease();
    await responseAfterLeave;
    await page.waitForLoadState("networkidle");
    assert.equal(await page.locator("#demand-list-view").isVisible(), true,
      "A consulta anterior abriu um detalhe depois que o usuário voltou à lista.");
    await page.unroute(firstUrl, holdDuringLeave);

    await page.setViewportSize({ width: 420, height: 920 });
    await row(second).waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await capture(page, "s09-mobile.png");
    await page.locator("#nav-history").click();
    await page.locator("#history-rows").getByText(`Ranking da demanda #${second.id}`, { exact: true }).waitFor();
    await page.locator("#logout").click();
    await page.locator("#auth-email").waitFor();
    console.log(JSON.stringify({ status: "PASS", login: true, validation: true, latest_selection: true,
      leave_cancels_detail: true, ranking_reopened: true, mobile: true, history: true, logout: true,
      first_demand: first.id, second_demand: second.id }));
  } finally {
    await browser.close();
  }
}

run().catch((error) => { console.error(error); process.exitCode = 1; });
