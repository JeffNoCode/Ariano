const $ = (id) => document.getElementById(id);
const state = { token: sessionStorage.getItem("ariano_token"), user: null, actors: [], tags: [], demands: [], documentId: null, currentDemand: null, editing: null, mode: "login" };
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const actorTypes = { SOLVER: "Solucionador", STARTUP: "Startup", ORGANIZATION: "Organização", GOVERNMENT_AGENCY: "Órgão público" };
const actorStatuses = { ACTIVE: "Ativo", INACTIVE: "Inativo", SUSPENDED: "Suspenso" };
const userRoles = { ADMIN: "Administrador", EDITOR: "Editor", VIEWER: "Leitor" };

async function api(path, options = {}) {
  const headers = { ...(options.body && !(options.body instanceof FormData) ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let response;
  try { response = await fetch(path, { ...options, headers }); }
  catch { throw new Error("Não foi possível conectar ao sistema. Verifique se a aplicação está em execução."); }
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof body.detail === "string" ? body.detail
      : Array.isArray(body.detail) ? body.detail.map((item) => `${fieldName(item.loc)}: ${validationMessage(item)}`).join("; ")
      : response.status >= 500 ? "Não foi possível concluir a operação. Tente novamente." : `Não foi possível concluir a operação (${response.status}).`;
    if (response.status === 401 && state.user) { state.token = null; state.user = null; sessionStorage.removeItem("ariano_token"); showAuth(); }
    throw new Error(message.replace(/^PDF_VALIDATION:\s*/, ""));
  }
  return body;
}

function fieldName(location = []) {
  const names = { title: "Título", tags: "Competências", weight: "Peso", budget: "Orçamento", deadline: "Prazo", document_id: "Documento", requester_id: "Solicitante", email: "E-mail", password: "Senha", name: "Nome" };
  return [...location].reverse().map((part) => names[part]).find(Boolean) || "Dados informados";
}

function validationMessage(item) {
  const type = item.type || "";
  if (type === "value_error" && item.msg) return item.msg.replace(/^Value error,\s*/, "");
  if (type.includes("missing")) return "campo obrigatório";
  if (type.includes("string_too_short") || type.includes("too_short")) return "informação muito curta ou lista vazia";
  if (type.includes("string_too_long")) return "texto acima do limite";
  if (type.includes("greater_than") || type.includes("greater_than_equal")) return "valor abaixo do permitido";
  if (type.includes("less_than")) return "valor acima do permitido";
  if (type.includes("date")) return "data inválida";
  if (type.includes("float") || type.includes("number")) return "número inválido";
  return "verifique o valor informado";
}

function notify(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => { $("toast").hidden = true; }, 3500);
}

function showMessage(id, message) {
  $(id).textContent = message;
  $(id).hidden = !message;
}

function showAuth() {
  $("app-view").hidden = true;
  $("auth-view").hidden = false;
  document.title = "ARIANO | Acesso";
}

function showApp() {
  $("auth-view").hidden = true;
  $("app-view").hidden = false;
  $("signed-user").textContent = `${state.user.name} · ${state.user.email}`;
  $("role-label").textContent = userRoles[state.user.role];
  $("new-actor").hidden = state.user.role === "VIEWER";
  $("new-demand").hidden = state.user.role === "VIEWER";
  $("run-ranking").hidden = state.user.role === "VIEWER";
  $("nav-users").hidden = state.user.role !== "ADMIN";
  $("overview-new-demand").hidden = state.user.role === "VIEWER";
  document.querySelectorAll('[data-quick="demand"],[data-quick="actor"]').forEach((button) => { button.hidden = state.user.role === "VIEWER"; });
  document.title = "ARIANO | Visão geral";
  switchView("overview");
}

const views = { overview: "Visão geral", demands: "Oportunidades", actors: "Atores", users: "Usuários" };

function switchView(view) {
  Object.keys(views).forEach((name) => {
    $(`${name}-section`).hidden = view !== name;
    $(`nav-${name}`).classList.toggle("active", view === name);
  });
  $("page-label").textContent = views[view];
  document.title = `ARIANO | ${views[view]}`;
  if (view === "overview") loadOverview().catch((error) => notify(error.message));
  if (view === "demands") { showDemandPanel("list"); loadDemands().catch((error) => notify(error.message)); }
  if (view === "actors") loadActors().catch((error) => notify(error.message));
  if (view === "users") loadUsers().catch((error) => notify(error.message));
}

function setAuthMode(mode) {
  state.mode = mode;
  $("name-field").hidden = mode !== "register";
  $("auth-name").required = mode === "register";
  $("auth-password").minLength = mode === "register" ? 12 : 0;
  $("auth-password").autocomplete = mode === "register" ? "new-password" : "current-password";
  $("auth-title").textContent = mode === "register" ? "Criar conta" : "Entrar";
  $("auth-submit").textContent = mode === "register" ? "Cadastrar" : "Entrar";
  $("auth-mode").textContent = mode === "register" ? "Já tenho conta" : "Criar conta";
  showMessage("auth-message", "");
}

async function submitAuth(event) {
  event.preventDefault();
  const email = $("auth-email").value.trim();
  const password = $("auth-password").value;
  try {
    showMessage("auth-message", "");
    if (state.mode === "register") {
      await api("/auth/register", { method: "POST", body: JSON.stringify({ name: $("auth-name").value.trim(), email, password }) });
    }
    const login = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    state.token = login.access_token;
    sessionStorage.setItem("ariano_token", state.token);
    state.user = await api("/auth/me");
    $("auth-password").value = "";
    showApp();
  } catch (error) { showMessage("auth-message", error.message); }
}

async function loadActors() {
  state.actors = await api("/actors?limit=500");
  renderActors();
}

function renderActors() {
  const query = $("actor-search").value.trim().toLocaleLowerCase("pt-BR");
  const visible = state.actors.filter((actor) => `${actor.name} ${actor.actor_type} ${actorTypes[actor.actor_type] || ""} ${actor.city || ""}`.toLocaleLowerCase("pt-BR").includes(query));
  $("actor-empty").hidden = visible.length !== 0;
  $("actor-rows").innerHTML = visible.map((actor) => {
    const actions = state.user.role === "VIEWER"
      ? `<button data-action="view" data-id="${actor.id}" type="button">Ver</button>`
      : `<button data-action="edit" data-id="${actor.id}" type="button">Editar</button><button class="danger" data-action="delete" data-id="${actor.id}" type="button">Excluir</button>`;
    return `<tr><td><strong>${esc(actor.name)}</strong></td><td>${esc(actorTypes[actor.actor_type] || actor.actor_type)}</td><td>${esc(actor.city || "—")}${actor.state ? ` / ${esc(actor.state)}` : ""}</td><td>${esc(actorStatuses[actor.status] || actor.status)}</td><td>${actor.tag_count}</td><td>${actions}</td></tr>`;
  }).join("");
}

async function loadTags() {
  if (!state.tags.length) state.tags = await api("/tags?only_active=true");
}

function profileKey(type) {
  return { ORGANIZATION: ["business_sector", "Setor de atuação"], STARTUP: ["sector", "Setor da startup"], SOLVER: ["bio", "Biografia"], GOVERNMENT_AGENCY: ["agency_type", "Tipo de órgão"] }[type];
}

function updateProfileField() {
  const type = $("actor-type").value;
  $("profile-field").firstChild.textContent = profileKey(type)[1];
  $("maturity-field").hidden = type !== "STARTUP";
}

function renderTagOptions(selected = []) {
  const chosen = new Map(selected.map((tag) => [tag.tag_id, tag.weight]));
  $("tag-options").innerHTML = state.tags.map((tag) => {
    const weight = chosen.get(tag.id) ?? 1;
    return `<label class="tag-option"><input type="checkbox" class="tag-check" value="${tag.id}" ${chosen.has(tag.id) ? "checked" : ""}><span>${esc(tag.name)}</span><input class="tag-weight" type="number" min="0" max="1" step="0.05" value="${weight}" aria-label="Peso de ${esc(tag.name)}"></label>`;
  }).join("") || '<p class="empty">Nenhuma competência cadastrada.</p>';
}

async function openActor(id = null) {
  try {
    await loadTags();
    state.editing = id;
    $("actor-form").reset();
    showMessage("actor-form-message", "");
    const actor = id === null ? null : await api(`/actors/${id}`);
    $("actor-form-title").textContent = actor ? "Ator" : "Novo ator";
    $("actor-type").value = actor?.actor_type || "ORGANIZATION";
    $("actor-type").disabled = Boolean(actor);
    $("actor-status").value = actor?.status || "ACTIVE";
    $("actor-name").value = actor?.name || "";
    $("actor-description").value = actor?.description || "";
    $("actor-city").value = actor?.city || "";
    $("actor-state").value = actor?.state || "";
    updateProfileField();
    $("actor-profile").value = actor?.profile?.[profileKey($("actor-type").value)[0]] || "";
    $("actor-maturity").value = actor?.profile?.maturity_level || "";
    renderTagOptions(actor?.tags || []);
    const readOnly = state.user.role === "VIEWER";
    $("save-actor").hidden = readOnly;
    $("cancel-actor").textContent = readOnly ? "Fechar" : "Cancelar";
    $("actor-form").querySelectorAll("input,select,textarea").forEach((field) => { field.disabled = readOnly || (field.id === "actor-type" && Boolean(actor)); });
    $("actor-dialog").showModal();
  } catch (error) { notify(error.message); }
}

function actorPayload() {
  const type = $("actor-type").value;
  const profile = { [profileKey(type)[0]]: $("actor-profile").value.trim() || null };
  if (type === "STARTUP") profile.maturity_level = $("actor-maturity").value || null;
  const tags = [...$("tag-options").querySelectorAll(".tag-option")].flatMap((row) => {
    const checkbox = row.querySelector(".tag-check");
    return checkbox.checked ? [{ tag_id: Number(checkbox.value), weight: Number(row.querySelector(".tag-weight").value) }] : [];
  });
  return {
    type, name: $("actor-name").value.trim(), description: $("actor-description").value.trim() || null,
    status: $("actor-status").value, city: $("actor-city").value.trim() || null,
    state: $("actor-state").value.trim().toUpperCase() || null, profile, tags,
  };
}

async function saveActor(event) {
  event.preventDefault();
  try {
    const path = state.editing === null ? "/actors" : `/actors/${state.editing}`;
    await api(path, { method: state.editing === null ? "POST" : "PUT", body: JSON.stringify(actorPayload()) });
    $("actor-dialog").close();
    await loadActors();
    notify(state.editing === null ? "Ator cadastrado." : "Ator atualizado.");
  } catch (error) { showMessage("actor-form-message", error.message); }
}

async function actorAction(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const id = Number(button.dataset.id);
  if (button.dataset.action !== "delete") { openActor(id); return; }
  if (!window.confirm("Excluir este ator?")) return;
  try { await api(`/actors/${id}`, { method: "DELETE" }); await loadActors(); notify("Ator excluído."); }
  catch (error) { notify(error.message); }
}

async function loadUsers() {
  const users = await api("/users");
  $("user-rows").innerHTML = users.map((user) => {
    const options = ["ADMIN", "EDITOR", "VIEWER"].map((role) => `<option value="${role}" ${role === user.role ? "selected" : ""}>${userRoles[role]}</option>`).join("");
    return `<tr><td>${esc(user.name)}</td><td>${esc(user.email)}</td><td><select data-user="${user.id}" aria-label="Perfil de ${esc(user.name)}">${options}</select></td><td>${user.is_active ? "Ativo" : "Inativo"}</td><td><button data-save-user="${user.id}" type="button">Salvar</button></td></tr>`;
  }).join("");
}

async function saveUser(event) {
  const button = event.target.closest("button[data-save-user]");
  if (!button) return;
  const id = Number(button.dataset.saveUser);
  const role = $("user-rows").querySelector(`select[data-user="${id}"]`).value;
  try { await api(`/users/${id}/role`, { method: "PATCH", body: JSON.stringify({ role }) }); await loadUsers(); notify("Perfil atualizado."); }
  catch (error) { notify(error.message); }
}

const demandStatuses = { OPEN: "Aberta", EVALUATING: "Em análise", CLOSED: "Encerrada", CANCELLED: "Cancelada" };
const classLabels = { EXACT: "Exata", RELATED: "Relacionada", PARTIAL: "Parcial", NONE: "Sem cobertura", MISSING: "Ausente" };
const pct = (value) => `${Math.round(Number(value || 0) * 100)}%`;
const score3 = (value) => Number(value || 0).toLocaleString("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
const chip = (kind, text) => `<span class="chip chip-${esc(String(kind).toLowerCase())}">${esc(text)}</span>`;
const statusChip = (status) => chip(`status-${status}`, demandStatuses[status] || status);

function greeting() {
  const hour = new Date().getHours();
  return hour < 12 ? "Bom dia" : hour < 18 ? "Boa tarde" : "Boa noite";
}

async function loadOverview() {
  const [stats, demands] = await Promise.all([api("/stats"), api("/demands?limit=6")]);
  $("overview-greeting").textContent = `${greeting()}, ${state.user.name.split(" ")[0]}`;
  const kpis = [
    ["Documentos processados", stats.documents, "Editais lidos pelo scraper"],
    ["Demandas abertas", stats.open_demands, `${stats.demands} no total`],
    ["Atores ativos", stats.active_actors, `${stats.actors} cadastrados`],
    ["Matches gerados", stats.matches, `${stats.tags} competências no catálogo`],
  ];
  $("overview-kpis").innerHTML = kpis.map(([label, value, hint]) => `<div class="kpi"><span>${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(hint)}</small></div>`).join("");
  $("overview-demands").innerHTML = demands.length ? demands.map((item) => `<button class="recent-item" type="button" data-demand="${item.id}"><span class="recent-title"><strong>${esc(item.title)}</strong><small>#${item.id} · ${esc(item.requester_name || "Solicitante não informado")}</small></span>${statusChip(item.status)}<span class="recent-score" title="Melhor score do ranking salvo">${item.best_score == null ? "—" : score3(item.best_score)}</span></button>`).join("") : '<p class="empty">Nenhuma demanda cadastrada ainda.</p>';
  const ecosystem = [["Startups", stats.startups], ["Profissionais (solucionadores)", stats.solvers], ["Organizações", stats.organizations], ["Órgãos públicos", stats.government_agencies]];
  const total = Math.max(1, stats.actors);
  $("overview-ecosystem").innerHTML = ecosystem.map(([label, value]) => `<li><span>${esc(label)}</span><strong>${esc(value)}</strong><i style="--share:${(value / total) * 100}%"></i></li>`).join("");
}

function quickAction(event) {
  const button = event.target.closest("button[data-quick]");
  if (!button) return;
  const target = button.dataset.quick;
  if (target === "demand") { switchView("demands"); startDemand(); }
  else if (target === "actor") { switchView("actors"); openActor(); }
  else switchView(target);
}

function showDemandPanel(panel) {
  ["list", "create", "detail"].forEach((name) => { $(`demand-${name}-view`).hidden = panel !== name; });
}

async function loadDemands() {
  state.demands = await api("/demands?limit=500");
  renderDemands();
}

function renderDemands() {
  const query = $("demand-search").value.trim().toLocaleLowerCase("pt-BR");
  const rows = state.demands.filter((item) => `${item.title} ${item.requester_name || ""}`.toLocaleLowerCase("pt-BR").includes(query));
  $("demand-empty").hidden = rows.length > 0;
  $("demand-rows").innerHTML = rows.map((item) => `<tr><td><strong>${esc(item.title)}</strong><br><small>#${item.id}${item.document_id ? " · PDF vinculado" : ""}</small></td><td>${esc(item.requester_name || "Não informado")}</td><td>${statusChip(item.status)}</td><td>${item.tag_count}</td><td>${item.match_count}${item.best_score == null ? "" : `<br><small>melhor ${score3(item.best_score)}</small>`}</td><td><button type="button" data-demand="${item.id}">Abrir</button></td></tr>`).join("");
}

function renderDemandTags(selectedCodes = []) {
  const selected = new Set(selectedCodes);
  $("demand-tag-options").innerHTML = state.tags.map((tag) => `<div class="demand-tag-row"><label><input type="checkbox" class="demand-tag-check" value="${tag.id}" ${selected.has(tag.code) ? "checked" : ""}><span>${esc(tag.name)}</span></label><select class="demand-tag-type" aria-label="Tipo de ${esc(tag.name)}"><option value="REQUIRED">Obrigatória</option><option value="DESIRABLE">Desejável</option></select><label>Peso<input class="demand-tag-weight" type="number" min="0.01" step="0.01" value="1" aria-label="Peso de ${esc(tag.name)}"></label></div>`).join("") || '<p class="empty">Nenhuma competência cadastrada. Cadastre competências pela API antes de criar demandas.</p>';
}

async function startDemand() {
  try {
    await loadTags();
    state.actors = await api("/actors?limit=500");
    state.documentId = null;
    $("demand-form").reset();
    $("document-status").textContent = "";
    $("document-review").hidden = true;
    showMessage("document-message", "");
    showMessage("demand-form-message", "");
    $("demand-requester").innerHTML = '<option value="">Não informado</option>' + state.actors.map((actor) => `<option value="${actor.id}">${esc(actor.name)}</option>`).join("");
    renderDemandTags();
    showDemandPanel("create");
    $("demand-title").focus();
  } catch (error) { notify(error.message); }
}

function tracked(value) { return value && typeof value === "object" ? value.value : value; }

async function uploadDocument() {
  const file = $("demand-pdf").files[0];
  showMessage("document-message", "");
  if (!file) { showMessage("document-message", "Selecione um arquivo PDF para leitura."); return; }
  if (!file.name.toLowerCase().endsWith(".pdf") || (file.type && file.type !== "application/pdf")) { showMessage("document-message", "O arquivo deve estar em formato PDF."); return; }
  if (file.size > 10 * 1024 * 1024) { showMessage("document-message", "O PDF deve ter no máximo 10 MB."); return; }
  const button = $("upload-document");
  button.disabled = true;
  $("document-status").textContent = "Lendo documento...";
  try {
    const form = new FormData(); form.append("file", file);
    const result = await api("/documents", { method: "POST", body: form });
    const document = await api(`/documents/${result.id}`);
    state.documentId = result.id;
    const payload = document.payload || {};
    const title = tracked(payload.document?.title);
    if (title && title !== "(não identificado)") $("demand-title").value = title.slice(0, 180);
    const deadline = tracked(payload.document?.submission_deadline);
    if (deadline) $("demand-deadline").value = deadline;
    const budget = tracked(payload.financial?.budget);
    if (budget != null) $("demand-budget").value = budget;
    const codes = (payload.competencies || []).map((item) => item.code);
    renderDemandTags(codes);
    const recognized = codes.filter((code) => state.tags.some((tag) => tag.code === code));
    $("document-review").innerHTML = `<strong>Revisão da extração</strong><p>${esc(title || "Título não identificado")} · ${esc(recognized.length)} competência(s) selecionada(s)</p><p>${esc((payload.extraction_warnings || []).length ? "Alguns campos não foram identificados; confira os dados antes de salvar." : "Confira os dados antes de salvar.")}</p>`;
    $("document-review").hidden = false;
    $("document-status").textContent = result.already_existed ? "PDF já registrado; dados recuperados." : "PDF processado e salvo.";
  } catch (error) { state.documentId = null; $("document-status").textContent = ""; showMessage("document-message", error.message); }
  finally { button.disabled = false; }
}

function demandPayload() {
  if ($("demand-pdf").files.length && !state.documentId) throw new Error("Clique em 'Ler PDF' antes de salvar, ou remova o arquivo selecionado.");
  const title = $("demand-title").value.trim();
  if (title.length < 3) throw new Error("Informe um título com pelo menos 3 caracteres.");
  const tags = [...$("demand-tag-options").querySelectorAll(".demand-tag-row")].flatMap((row) => {
    const checked = row.querySelector(".demand-tag-check");
    if (!checked.checked) return [];
    const weight = Number(row.querySelector(".demand-tag-weight").value);
    if (!Number.isFinite(weight) || weight <= 0) throw new Error("O peso de cada competência selecionada deve ser maior que zero.");
    return [{ tag_id: Number(checked.value), type: row.querySelector(".demand-tag-type").value, weight }];
  });
  if (!tags.length) throw new Error("Selecione ao menos uma competência para calcular o ranking.");
  const budgetText = $("demand-budget").value;
  const budget = budgetText === "" ? null : Number(budgetText);
  if (budget !== null && (!Number.isFinite(budget) || budget < 0)) throw new Error("O orçamento deve ser um valor igual ou maior que zero.");
  return { title, description: $("demand-description").value.trim() || null,
    requester_id: $("demand-requester").value ? Number($("demand-requester").value) : null,
    deadline: $("demand-deadline").value || null, budget, document_id: state.documentId, tags };
}

async function saveDemand(event) {
  event.preventDefault();
  showMessage("demand-form-message", "");
  const button = $("save-demand");
  try {
    const payload = demandPayload();
    button.disabled = true;
    const demand = await api("/demands", { method: "POST", body: JSON.stringify(payload) });
    await loadDemands();
    notify("Demanda salva.");
    await openDemand(demand.id);
  } catch (error) { showMessage("demand-form-message", error.message); }
  finally { button.disabled = false; }
}

async function openDemand(id) {
  try {
    await loadTags();
    const demand = await api(`/demands/${id}`);
    state.currentDemand = demand;
    $("detail-title").textContent = demand.title;
    $("detail-subtitle").textContent = `Demanda #${demand.id} · ${demandStatuses[demand.status] || demand.status}`;
    $("demand-facts").innerHTML = `<div><dt>Prazo</dt><dd>${demand.deadline ? esc(new Date(`${demand.deadline}T12:00:00`).toLocaleDateString("pt-BR")) : "Não informado"}</dd></div><div><dt>Orçamento</dt><dd>${demand.budget == null ? "Não informado" : esc(Number(demand.budget).toLocaleString("pt-BR", { style: "currency", currency: demand.currency || "BRL" }))}</dd></div><div><dt>Descrição</dt><dd>${esc(demand.description || "Não informada")}</dd></div>`;
    $("detail-tags").innerHTML = demand.tags.map((tag) => `<span>${esc(tagName(tag.tag_id))} · ${tag.tag_type === "REQUIRED" ? "Obrigatória" : "Desejável"} · peso ${esc(tag.weight)}</span>`).join("");
    if (demand.document_id) {
      const document = await api(`/documents/${demand.document_id}`);
      $("detail-document").innerHTML = `<strong>Documento vinculado</strong><p>${esc(document.title || "PDF processado")} · #${document.id}</p>`;
      $("detail-document").hidden = false;
    } else $("detail-document").hidden = true;
    showMessage("ranking-message", "");
    await loadRanking(id);
    showDemandPanel("detail");
  } catch (error) { notify(error.message); }
}

function tagName(id) {
  return state.tags.find((tag) => tag.id === id)?.name || `Competência #${id}`;
}

function renderDemandKpis(demand, rows) {
  const required = demand.tags.filter((tag) => tag.tag_type === "REQUIRED").length;
  const items = [["Competências", demand.tags.length], ["Obrigatórias", required], ["Desejáveis", demand.tags.length - required], ["Atores no ranking", rows.length], ["Versão do algoritmo", rows[0]?.algorithm_version || "—"]];
  $("demand-kpis").innerHTML = items.map(([label, value]) => `<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("");
}

function detailItem(item) {
  const evidence = item.match === "EXACT" ? "o ator possui esta competência"
    : item.match === "RELATED" ? `coberta por ${esc(tagName(item.actor_tag_id))} (${item.relation_type === "SYNONYM" ? "sinônimo" : "competência relacionada"}, peso ${esc(item.relation_weight)})`
    : "nenhuma evidência no perfil do ator";
  return `<li class="why-item"><div class="why-head"><strong>${esc(tagName(item.demand_tag_id))}</strong>${chip(item.match, classLabels[item.match] || item.match)}</div><div class="bar" role="img" aria-label="Cobertura ${pct(item.coverage)}"><i style="width:${pct(item.coverage)}"></i></div><small>Cobertura ${pct(item.coverage)} · ${evidence}</small></li>`;
}

function renderScorePanel(row) {
  const panel = $("score-panel");
  if (!row) { panel.hidden = true; return; }
  const sd = row.score_details || {};
  const details = sd.details || [];
  const required = details.filter((item) => item.tag_type === "REQUIRED");
  const desirable = details.filter((item) => item.tag_type === "DESIRABLE");
  panel.innerHTML = `<p class="eyebrow">Por que este score?</p><h3>${esc(row.actor_name)}</h3>
    <div class="why-score"><strong>${score3(row.score)}</strong>${chip(row.match_type, classLabels[row.match_type] || row.match_type)}</div>
    <dl class="why-parts"><div><dt>Obrigatórias</dt><dd>${pct(sd.required_score)}</dd></div><div><dt>Desejáveis</dt><dd>${desirable.length ? pct(sd.desirable_score) : "—"}</dd></div><div><dt>Faltando</dt><dd>${esc(row.required_missing_count || 0)}</dd></div></dl>
    ${required.length ? `<h4>Obrigatórias</h4><ul class="why-list">${required.map(detailItem).join("")}</ul>` : ""}
    ${desirable.length ? `<h4>Desejáveis</h4><ul class="why-list">${desirable.map(detailItem).join("")}</ul>` : ""}
    <p class="muted why-note">As obrigatórias formam a base do score; as desejáveis ajustam até 20% dela. O score só é comparável entre atores desta mesma demanda.</p>`;
  panel.hidden = false;
}

function selectRankingRow(index) {
  state.rankingIndex = index;
  $("ranking-results").querySelectorAll(".ranking-row").forEach((element, i) => {
    element.classList.toggle("selected", i === index);
    element.setAttribute("aria-pressed", String(i === index));
  });
  renderScorePanel(state.ranking[index]);
}

function renderRanking(rows) {
  state.ranking = rows;
  $("ranking-summary").textContent = rows.length ? `${rows.length} resultado(s) salvos. Selecione um ator para ver a explicação do score.` : "Ainda não há ranking salvo para esta demanda.";
  $("ranking-results").innerHTML = rows.map((row, index) => `<button type="button" class="ranking-row" data-rank="${index}" aria-pressed="false"><span class="rank-number">${index + 1}</span><span class="ranking-name"><strong>${esc(row.actor_name)}</strong><small>${esc(row.required_missing_count || 0)} obrigatória(s) não atendida(s)</small></span>${chip(row.match_type, classLabels[row.match_type] || row.match_type)}<strong class="rank-score">${score3(row.score)}</strong></button>`).join("");
  if (rows.length) selectRankingRow(0); else renderScorePanel(null);
}

async function loadRanking(id) {
  const rows = await api(`/demands/${id}/matches?limit=500`);
  renderRanking(rows);
  if (state.currentDemand?.id === id) renderDemandKpis(state.currentDemand, rows);
}

async function runRanking() {
  if (!state.currentDemand) return;
  const button = $("run-ranking");
  button.disabled = true;
  showMessage("ranking-message", "");
  try {
    await api(`/demands/${state.currentDemand.id}/match`, { method: "POST", body: JSON.stringify({ persist: true }) });
    await loadRanking(state.currentDemand.id);
    await loadDemands();
    notify("Ranking calculado e salvo.");
  } catch (error) { showMessage("ranking-message", error.message); }
  finally { button.disabled = false; }
}

async function initialize() {
  $("auth-form").addEventListener("submit", submitAuth);
  $("auth-mode").addEventListener("click", () => setAuthMode(state.mode === "login" ? "register" : "login"));
  $("logout").addEventListener("click", async () => { try { await api("/auth/logout", { method: "POST" }); } catch {} state.token = null; state.user = null; sessionStorage.removeItem("ariano_token"); showAuth(); });
  $("nav-overview").addEventListener("click", () => switchView("overview"));
  $("overview-new-demand").addEventListener("click", () => { switchView("demands"); startDemand(); });
  $("overview-all-demands").addEventListener("click", () => switchView("demands"));
  $("overview-demands").addEventListener("click", (event) => { const button = event.target.closest("button[data-demand]"); if (button) { switchView("demands"); openDemand(Number(button.dataset.demand)); } });
  document.querySelector(".quick-actions").addEventListener("click", quickAction);
  $("ranking-results").addEventListener("click", (event) => { const row = event.target.closest("button[data-rank]"); if (row) selectRankingRow(Number(row.dataset.rank)); });
  $("nav-demands").addEventListener("click", () => switchView("demands"));
  $("nav-actors").addEventListener("click", () => switchView("actors"));
  $("nav-users").addEventListener("click", () => switchView("users"));
  $("refresh-demands").addEventListener("click", () => loadDemands().catch((error) => notify(error.message)));
  $("demand-search").addEventListener("input", renderDemands);
  $("demand-rows").addEventListener("click", (event) => { const button = event.target.closest("button[data-demand]"); if (button) openDemand(Number(button.dataset.demand)); });
  $("new-demand").addEventListener("click", startDemand);
  $("back-from-create").addEventListener("click", () => { showDemandPanel("list"); loadDemands().catch((error) => notify(error.message)); });
  $("back-from-detail").addEventListener("click", () => { showDemandPanel("list"); loadDemands().catch((error) => notify(error.message)); });
  $("upload-document").addEventListener("click", uploadDocument);
  $("demand-pdf").addEventListener("change", () => { state.documentId = null; $("document-status").textContent = ""; $("document-review").hidden = true; });
  $("demand-form").addEventListener("submit", saveDemand);
  $("run-ranking").addEventListener("click", runRanking);
  $("refresh-actors").addEventListener("click", () => loadActors().catch((error) => notify(error.message)));
  $("actor-search").addEventListener("input", renderActors);
  $("new-actor").addEventListener("click", () => openActor());
  $("actor-type").addEventListener("change", updateProfileField);
  $("actor-form").addEventListener("submit", saveActor);
  $("close-dialog").addEventListener("click", () => $("actor-dialog").close());
  $("cancel-actor").addEventListener("click", () => $("actor-dialog").close());
  $("actor-rows").addEventListener("click", actorAction);
  $("user-rows").addEventListener("click", saveUser);
  if (state.token) {
    try { state.user = await api("/auth/me"); showApp(); return; }
    catch { state.token = null; sessionStorage.removeItem("ariano_token"); }
  }
  showAuth();
}

initialize();

