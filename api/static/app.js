const $ = (id) => document.getElementById(id);
const state = { token: sessionStorage.getItem("ariano_token"), user: null, actors: [], tags: [], editing: null, mode: "login" };
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
const actorTypes = { SOLVER: "Solucionador", STARTUP: "Startup", ORGANIZATION: "Organização", GOVERNMENT_AGENCY: "Órgão público" };
const actorStatuses = { ACTIVE: "Ativo", INACTIVE: "Inativo", SUSPENDED: "Suspenso" };
const userRoles = { ADMIN: "Administrador", EDITOR: "Editor", VIEWER: "Leitor" };

async function api(path, options = {}) {
  const headers = { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) };
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(path, { ...options, headers });
  if (response.status === 204) return null;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof body.detail === "string" ? body.detail : `Erro HTTP ${response.status}`;
    if (response.status === 401 && state.user) { state.token = null; state.user = null; sessionStorage.removeItem("ariano_token"); showAuth(); }
    throw new Error(message);
  }
  return body;
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
  $("nav-users").hidden = state.user.role !== "ADMIN";
  document.title = "ARIANO | Atores";
  switchView("actors");
}

function switchView(view) {
  $("actors-section").hidden = view !== "actors";
  $("users-section").hidden = view !== "users";
  $("nav-actors").classList.toggle("active", view === "actors");
  $("nav-users").classList.toggle("active", view === "users");
  $("page-label").textContent = view === "actors" ? "Atores" : "Usuários";
  if (view === "actors") loadActors().catch((error) => notify(error.message));
  else loadUsers().catch((error) => notify(error.message));
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

async function initialize() {
  $("auth-form").addEventListener("submit", submitAuth);
  $("auth-mode").addEventListener("click", () => setAuthMode(state.mode === "login" ? "register" : "login"));
  $("logout").addEventListener("click", async () => { try { await api("/auth/logout", { method: "POST" }); } catch {} state.token = null; state.user = null; sessionStorage.removeItem("ariano_token"); showAuth(); });
  $("nav-actors").addEventListener("click", () => switchView("actors"));
  $("nav-users").addEventListener("click", () => switchView("users"));
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

