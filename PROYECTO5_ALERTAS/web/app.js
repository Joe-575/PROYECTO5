/* ==========================================================================
   SOC Bayesiano - Cliente JS Vanilla optimizado
   ========================================================================== */

(() => {
  "use strict";

  const NOMBRES_CORTOS = {
    I: "Intrusión Externa",
    C: "Error Config.",
    M: "Mantenimiento",
    T: "Tráfico Anómalo",
    A: "Alerta IDS/SIEM",
    L: "Fallos de Login",
  };

  // Posiciones del grafo DAG (ancho 820 x alto 410)
  const POSICIONES_DAG = {
    I: { x: 145, y: 112, capa: "causa" },
    C: { x: 410, y: 112, capa: "causa" },
    M: { x: 675, y: 112, capa: "causa" },
    T: { x: 145, y: 310, capa: "efecto" },
    A: { x: 410, y: 310, capa: "efecto" },
    L: { x: 675, y: 310, capa: "efecto" },
  };

  const NODO_W = 200;
  const NODO_H = 104;

  const state = {
    meta: null,
    evidencia: {},
    variableConsulta: "I",
    posteriores: {},
    escenariosCache: null,
    toastTimer: null,
  };

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  async function api(url, options = {}) {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.error || `Error HTTP ${res.status}`);
    }
    return data;
  }

  function mostrarToast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
  }

  function pct(val, decimales = 2) {
    return `${(val * 100).toFixed(decimales)}%`;
  }

  function clasificarRiesgo(p) {
    if (p >= 0.70) return { texto: "Crítico", clase: "risk-critico" };
    if (p >= 0.40) return { texto: "Alto", clase: "risk-alto" };
    if (p >= 0.15) return { texto: "Moderado", clase: "risk-moderado" };
    return { texto: "Bajo", clase: "risk-bajo" };
  }

  function colorProbabilidad(p) {
    if (p >= 0.70) return "var(--accent-danger)";
    if (p >= 0.40) return "var(--accent-warn)";
    if (p >= 0.15) return "var(--accent-primary)";
    return "var(--accent-ok)";
  }

  /* ------------------------------------------------------------------------
     Navegación y Tema
     ------------------------------------------------------------------------ */
  function initNavegacion() {
    $$(".nav-tab").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.tab;
        $$(".nav-tab").forEach((b) => {
          b.classList.toggle("active", b === btn);
          b.setAttribute("aria-selected", String(b === btn));
        });
        $$(".view").forEach((v) => {
          const active = v.id === `view-${tab}`;
          v.hidden = !active;
          v.classList.toggle("active", active);
        });
        if (tab === "escenarios") cargarEscenarios();
        if (tab === "previas") cargarComparacionPrevias();
        if (tab === "cpt") renderEditorCPT();
      });
    });

    const temaGuardado = localStorage.getItem("soc-tema") || "dark";
    document.documentElement.setAttribute("data-theme", temaGuardado);
    $("#btn-tema").addEventListener("click", () => {
      const actual = document.documentElement.getAttribute("data-theme");
      const nuevo = actual === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", nuevo);
      localStorage.setItem("soc-tema", nuevo);
    });
  }

  /* ------------------------------------------------------------------------
     Renderizado del Grafo DAG SVG
     ------------------------------------------------------------------------ */
  function construirDAG() {
    const svgNS = "http://www.w3.org/2000/svg";
    const layerLabels = $("#dag-layer-labels");
    const edgesGroup = $("#dag-edges");
    const nodesGroup = $("#dag-nodes");
    layerLabels.innerHTML = "";
    edgesGroup.innerHTML = "";
    nodesGroup.innerHTML = "";

    // Etiquetas de capas
    const etiquetas = [
      { y: 34, texto: "CAUSAS RAÍZ (VARIABLES OCULTAS)" },
      { y: 232, texto: "EVIDENCIA / SEÑALES OBSERVABLES" },
    ];
    for (const et of etiquetas) {
      const t = document.createElementNS(svgNS, "text");
      t.setAttribute("x", "410");
      t.setAttribute("y", String(et.y));
      t.setAttribute("text-anchor", "middle");
      t.setAttribute("class", "dag-layer-title");
      t.textContent = et.texto;
      layerLabels.appendChild(t);
    }

    // Aristas dirigidas
    for (const [hijo, info] of Object.entries(state.meta.nodos)) {
      const dest = POSICIONES_DAG[hijo];
      for (const padre of info.padres) {
        const orig = POSICIONES_DAG[padre];
        const x1 = orig.x;
        const y1 = orig.y + NODO_H / 2 + 2;
        const x2 = dest.x;
        const y2 = dest.y - NODO_H / 2 - 4;
        const midY = (y1 + y2) / 2;

        const path = document.createElementNS(svgNS, "path");
        path.setAttribute("d", `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`);
        path.setAttribute("class", "dag-edge");
        path.setAttribute("data-from", padre);
        path.setAttribute("data-to", hijo);
        path.setAttribute("marker-end", "url(#arrow)");
        edgesGroup.appendChild(path);
      }
    }

    // Nodos
    for (const varId of state.meta.orden_topologico) {
      const pos = POSICIONES_DAG[varId];
      const g = document.createElementNS(svgNS, "g");
      g.setAttribute("class", "dag-node");
      g.setAttribute("data-var", varId);
      g.setAttribute("transform", `translate(${pos.x - NODO_W / 2}, ${pos.y - NODO_H / 2})`);
      g.setAttribute("role", "button");
      g.setAttribute("tabindex", "0");

      const rect = document.createElementNS(svgNS, "rect");
      rect.setAttribute("width", String(NODO_W));
      rect.setAttribute("height", String(NODO_H));
      rect.setAttribute("rx", "13");
      rect.setAttribute("class", "dag-node-bg");

      const code = document.createElementNS(svgNS, "text");
      code.setAttribute("x", "14");
      code.setAttribute("y", "28");
      code.setAttribute("class", "dag-node-code");
      code.textContent = varId;

      const title = document.createElementNS(svgNS, "text");
      title.setAttribute("x", "36");
      title.setAttribute("y", "27");
      title.setAttribute("class", "dag-node-title");
      title.textContent = NOMBRES_CORTOS[varId] || varId;

      const stateTxt = document.createElementNS(svgNS, "text");
      stateTxt.setAttribute("x", String(NODO_W - 14));
      stateTxt.setAttribute("y", "26");
      stateTxt.setAttribute("text-anchor", "end");
      stateTxt.setAttribute("class", "dag-node-state");
      stateTxt.setAttribute("id", `dag-state-${varId}`);

      const probTxt = document.createElementNS(svgNS, "text");
      probTxt.setAttribute("x", "14");
      probTxt.setAttribute("y", "64");
      probTxt.setAttribute("class", "dag-node-prob");
      probTxt.setAttribute("id", `dag-prob-${varId}`);
      probTxt.textContent = "0.00%";

      const subTxt = document.createElementNS(svgNS, "text");
      subTxt.setAttribute("x", String(NODO_W - 14));
      subTxt.setAttribute("y", "63");
      subTxt.setAttribute("text-anchor", "end");
      subTxt.setAttribute("class", "dag-node-title");
      subTxt.textContent = "P(True)";

      const barBg = document.createElementNS(svgNS, "rect");
      barBg.setAttribute("x", "14");
      barBg.setAttribute("y", "78");
      barBg.setAttribute("width", String(NODO_W - 28));
      barBg.setAttribute("height", "9");
      barBg.setAttribute("rx", "4.5");
      barBg.setAttribute("class", "dag-bar-bg");

      const barFill = document.createElementNS(svgNS, "rect");
      barFill.setAttribute("x", "14");
      barFill.setAttribute("y", "78");
      barFill.setAttribute("width", "0");
      barFill.setAttribute("height", "9");
      barFill.setAttribute("rx", "4.5");
      barFill.setAttribute("class", "dag-bar-fill");
      barFill.setAttribute("id", `dag-bar-${varId}`);

      g.append(rect, code, title, stateTxt, probTxt, subTxt, barBg, barFill);

      const alternar = () => ciclarEvidencia(varId);
      g.addEventListener("click", alternar);
      g.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          alternar();
        }
      });

      nodesGroup.appendChild(g);
    }
  }

  function ciclarEvidencia(varId) {
    if (!(varId in state.evidencia)) {
      state.evidencia[varId] = true;
    } else if (state.evidencia[varId] === true) {
      state.evidencia[varId] = false;
    } else {
      delete state.evidencia[varId];
    }
    sincronizarControlesEvidencia();
    ejecutarInferencia();
  }

  function fijarEvidencia(varId, valor) {
    if (valor === null) {
      delete state.evidencia[varId];
    } else {
      state.evidencia[varId] = valor;
    }
    sincronizarControlesEvidencia();
    ejecutarInferencia();
  }

  /* ------------------------------------------------------------------------
     Controles laterales de evidencia y consulta
     ------------------------------------------------------------------------ */
  function construirControlesEvidencia() {
    const cont = $("#lista-controles-evidencia");
    const select = $("#select-consulta");
    cont.innerHTML = "";
    select.innerHTML = "";

    for (const varId of state.meta.orden_topologico) {
      const desc = state.meta.variables[varId];

      const row = document.createElement("div");
      row.className = "evidence-row";
      row.innerHTML = `
        <div class="evidence-info">
          <div class="evidence-title">
            <span class="var-tag">${varId}</span>
            <span>${NOMBRES_CORTOS[varId] || varId}</span>
          </div>
          <div class="evidence-desc" title="${desc}">${desc}</div>
        </div>
        <div class="tri-toggle" data-var="${varId}">
          <button type="button" class="tri-btn" data-val="none">?</button>
          <button type="button" class="tri-btn" data-val="true">T</button>
          <button type="button" class="tri-btn" data-val="false">F</button>
        </div>
      `;
      row.querySelectorAll(".tri-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const val = btn.dataset.val;
          fijarEvidencia(varId, val === "none" ? null : val === "true");
        });
      });
      cont.appendChild(row);

      const opt = document.createElement("option");
      opt.value = varId;
      opt.textContent = `${varId} · ${NOMBRES_CORTOS[varId] || varId}`;
      select.appendChild(opt);
    }

    select.value = state.variableConsulta;
    select.addEventListener("change", () => {
      state.variableConsulta = select.value;
      ejecutarInferencia();
    });

    $("#btn-limpiar-evidencia").addEventListener("click", () => {
      state.evidencia = {};
      sincronizarControlesEvidencia();
      ejecutarInferencia();
    });

    $$(".chip-btn[data-preset]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = Number(btn.dataset.preset);
        cargarEscenarioEnRed(id);
      });
    });

    sincronizarControlesEvidencia();
  }

  function sincronizarControlesEvidencia() {
    $$(".tri-toggle").forEach((group) => {
      const varId = group.dataset.var;
      const actual = varId in state.evidencia ? String(state.evidencia[varId]) : "none";
      group.querySelectorAll(".tri-btn").forEach((btn) => {
        btn.classList.remove("active-none", "active-true", "active-false");
        if (btn.dataset.val === actual) {
          btn.classList.add(`active-${actual}`);
        }
      });
    });
  }

  function cargarEscenarioEnRed(id) {
    const esc = state.meta.escenarios.escenarios.find((e) => e.id === id);
    if (!esc) return;
    state.evidencia = { ...esc.evidencia };
    sincronizarControlesEvidencia();
    ejecutarInferencia();
    mostrarToast(`Cargado: ${esc.nombre}`);
  }

  /* ------------------------------------------------------------------------
     Ejecución de Inferencia en Vivo
     ------------------------------------------------------------------------ */
  async function ejecutarInferencia() {
    try {
      const data = await api("/api/inferencia", {
        method: "POST",
        body: JSON.stringify({
          evidencia: state.evidencia,
          variable_consulta: state.variableConsulta,
          verificar_pgmpy: true,
        }),
      });
      state.posteriores = data.posteriores;
      actualizarVistaPanel(data);
    } catch (err) {
      mostrarToast(`Error de inferencia: ${err.message}`);
    }
  }

  function actualizarVistaPanel(data) {
    const post = data.posteriores;

    // 1. KPIs de causas
    for (const c of ["I", "C", "M"]) {
      const p = post[c].true;
      $(`#kpi-${c}`).textContent = pct(p);
      $(`#bar-${c}`).style.width = `${(p * 100).toFixed(2)}%`;
    }

    const riesgo = clasificarRiesgo(post.I.true);
    const badgeRiesgo = $("#badge-riesgo-I");
    badgeRiesgo.textContent = riesgo.texto;
    badgeRiesgo.className = `risk-badge ${riesgo.clase}`;

    $("#kpi-latencia").textContent = `${data.tiempo_propio_ms.toFixed(2)} ms`;

    // Diagnóstico dominante
    const causas = [
      { id: "I", nombre: "Intrusión Externa", p: post.I.true },
      { id: "C", nombre: "Error de Configuración", p: post.C.true },
      { id: "M", nombre: "Mantenimiento Legítimo", p: post.M.true },
    ].sort((a, b) => b.p - a.p);

    const top = causas[0];
    $("#kpi-diagnostico").textContent =
      top.p >= 0.25 ? `${top.nombre} (${pct(top.p, 1)})` : "Sin causa crítica dominante";

    const evEntries = Object.entries(state.evidencia);
    $("#kpi-evidencia-resumen").textContent = evEntries.length
      ? `Evidencia: ${evEntries.map(([k, v]) => `${k}=${v ? "T" : "F"}`).join(", ")}`
      : "Sin evidencia observada (distribución previa)";

    // 2. Actualizar nodos y aristas del DAG
    for (const varId of state.meta.orden_topologico) {
      const p = post[varId].true;
      const g = $(`.dag-node[data-var="${varId}"]`);
      const probEl = $(`#dag-prob-${varId}`);
      const barEl = $(`#dag-bar-${varId}`);
      const stateEl = $(`#dag-state-${varId}`);

      g.classList.remove("ev-true", "ev-false");
      if (varId in state.evidencia) {
        const val = state.evidencia[varId];
        g.classList.add(val ? "ev-true" : "ev-false");
        stateEl.textContent = val ? "OBS: TRUE" : "OBS: FALSE";
        stateEl.setAttribute("fill", val ? "var(--accent-ok)" : "var(--accent-danger)");
      } else {
        stateEl.textContent = "INFERIDO";
        stateEl.setAttribute("fill", "var(--text-muted)");
      }

      probEl.textContent = pct(p);
      barEl.setAttribute("width", String(((NODO_W - 28) * p).toFixed(1)));
      barEl.setAttribute("fill", colorProbabilidad(p));
    }

    $$(".dag-edge").forEach((edge) => {
      const from = edge.dataset.from;
      const to = edge.dataset.to;
      const activa = from in state.evidencia || to in state.evidencia;
      edge.classList.toggle("active", activa);
      edge.setAttribute("marker-end", activa ? "url(#arrow-active)" : "url(#arrow)");
    });

    // 3. Resultado de consulta puntual
    const qVar = state.variableConsulta;
    const qRes = post[qVar];
    const verif = data.verificacion_pgmpy;
    let verifHtml = "";

    if (verif && verif.disponible && verif.resultados[qVar]) {
      const rLib = verif.resultados[qVar];
      verifHtml = `
        <div class="query-row">
          <div>
            <div class="query-meta">Verificación <code class="mono">pgmpy</code></div>
            <div class="query-meta">Diff abs: <span class="mono">${rLib.diff_abs.toExponential(2)}</span></div>
          </div>
          <div class="tabular" style="text-align:right">
            <strong>${pct(rLib.true, 4)}</strong>
            <div class="query-meta">False: ${pct(rLib.false, 4)}</div>
          </div>
        </div>
      `;
    } else {
      verifHtml = `
        <div class="query-row">
          <div class="query-meta">Verificación <code class="mono">pgmpy</code> no disponible en este entorno Python.</div>
        </div>
      `;
    }

    $("#resultado-consulta").innerHTML = `
      <div class="query-row">
        <div>
          <div class="query-meta">Algoritmo propio · <code class="mono">P(${qVar} | e)</code></div>
          <div class="query-meta">Exacto por enumeración (${data.tiempo_propio_ms.toFixed(2)} ms)</div>
        </div>
        <div class="tabular" style="text-align:right">
          <strong style="color:var(--accent-primary)">${pct(qRes.true, 4)}</strong>
          <div class="query-meta">False: ${pct(qRes.false, 4)}</div>
        </div>
      </div>
      ${verifHtml}
    `;
  }

  /* ------------------------------------------------------------------------
     Vista 2: 4 Escenarios
     ------------------------------------------------------------------------ */
  async function cargarEscenarios() {
    const grid = $("#grid-escenarios");
    grid.innerHTML = `<div class="card">Calculando escenarios...</div>`;
    try {
      const data = await api("/api/escenarios");
      state.escenariosCache = data;
      renderEscenarios(data);
    } catch (err) {
      grid.innerHTML = `<div class="card">Error: ${err.message}</div>`;
    }
  }

  function renderEscenarios(data) {
    const grid = $("#grid-escenarios");
    grid.innerHTML = "";

    for (const esc of data.escenarios) {
      const card = document.createElement("article");
      card.className = "card scenario-card";

      const chips = Object.entries(esc.evidencia)
        .map(
          ([k, v]) =>
            `<span class="ev-chip ${v ? "ev-chip-true" : "ev-chip-false"}">${k}=${v ? "True" : "False"}</span>`
        )
        .join("");

      const filas = esc.resultados
        .map((r) => {
          const pgmpyTxt = r.p_pgmpy !== null ? r.p_pgmpy.toFixed(6) : "N/D";
          const diffTxt = r.diff_abs !== null ? r.diff_abs.toExponential(2) : "—";
          return `
            <tr>
              <td><span class="var-tag">${r.causa}</span> ${NOMBRES_CORTOS[r.causa] || r.causa}</td>
              <td class="num-col tabular">
                <span class="mini-bar"><span style="width:${(r.p_propio * 100).toFixed(1)}%;background:${colorProbabilidad(r.p_propio)}"></span></span>
                <strong>${r.p_propio.toFixed(6)}</strong>
              </td>
              <td class="num-col tabular">${pgmpyTxt}</td>
              <td class="num-col mono">${diffTxt}</td>
            </tr>
          `;
        })
        .join("");

      card.innerHTML = `
        <div class="scenario-head">
          <div>
            <h3>${esc.nombre}</h3>
            <p class="card-subtitle">${esc.descripcion}</p>
          </div>
          <button class="btn btn-secondary btn-sm btn-cargar-esc" data-id="${esc.id}">Cargar en Red</button>
        </div>
        <div class="ev-chips">${chips}</div>
        <table class="data-table">
          <thead>
            <tr>
              <th>Causa</th>
              <th class="num-col">P(True) Propio</th>
              <th class="num-col">P(True) pgmpy</th>
              <th class="num-col">Diff Abs</th>
            </tr>
          </thead>
          <tbody>${filas}</tbody>
        </table>
      `;

      card.querySelector(".btn-cargar-esc").addEventListener("click", () => {
        cargarEscenarioEnRed(esc.id);
        $$('.nav-tab[data-tab="panel"]')[0].click();
      });

      grid.appendChild(card);
    }
  }

  /* ------------------------------------------------------------------------
     Vista 3: Comparación de Previas & Curva de Sensibilidad
     ------------------------------------------------------------------------ */
  function initControlesPrevias() {
    const sel = $("#select-escenario-previa");
    sel.innerHTML = "";
    for (const esc of state.meta.escenarios.escenarios) {
      const opt = document.createElement("option");
      opt.value = esc.id;
      opt.textContent = esc.nombre;
      sel.appendChild(opt);
    }
    const comp = state.meta.escenarios.comparacion_previa;
    sel.value = comp.escenario_id;
    $("#range-previa-base").value = comp.previa_base;
    $("#range-previa-alta").value = comp.previa_alta;
    $("#lbl-previa-base").textContent = pct(comp.previa_base, 1);
    $("#lbl-previa-alta").textContent = pct(comp.previa_alta, 1);
    $("#previas-justificacion").textContent = comp.justificacion;

    let debounce;
    const onChange = () => {
      $("#lbl-previa-base").textContent = pct(Number($("#range-previa-base").value), 1);
      $("#lbl-previa-alta").textContent = pct(Number($("#range-previa-alta").value), 1);
      clearTimeout(debounce);
      debounce = setTimeout(cargarComparacionPrevias, 70);
    };

    sel.addEventListener("change", cargarComparacionPrevias);
    $("#range-previa-base").addEventListener("input", onChange);
    $("#range-previa-alta").addEventListener("input", onChange);
  }

  async function cargarComparacionPrevias() {
    try {
      const data = await api("/api/comparacion_previas", {
        method: "POST",
        body: JSON.stringify({
          escenario_id: Number($("#select-escenario-previa").value),
          previa_base: Number($("#range-previa-base").value),
          previa_alta: Number($("#range-previa-alta").value),
        }),
      });
      renderComparacionPrevias(data);
    } catch (err) {
      mostrarToast(`Error: ${err.message}`);
    }
  }

  function renderComparacionPrevias(data) {
    const b = data.base;
    const a = data.alta;
    const factor = b.posterior_true > 0 ? a.posterior_true / b.posterior_true : 0;
    const diffPts = (a.posterior_true - b.posterior_true) * 100;

    $("#card-previa-comparacion").innerHTML = `
      <div class="card-header">
        <div>
          <h2>Resultados Comparativos · <span class="mono">P(I=True | e)</span></h2>
          <p class="card-subtitle">${data.escenario.nombre}</p>
        </div>
      </div>
      <div class="prior-compare-cards">
        <div class="prior-box">
          <div class="prior-box-title">${b.etiqueta}</div>
          <div class="prior-box-val tabular" style="color:var(--accent-primary)">${pct(b.posterior_true)}</div>
          <div class="query-meta">Previa P(I): <strong>${pct(b.previa, 1)}</strong> · P(I=F|e): ${pct(b.posterior_false)}</div>
        </div>
        <div class="prior-box">
          <div class="prior-box-title">${a.etiqueta}</div>
          <div class="prior-box-val tabular" style="color:var(--accent-danger)">${pct(a.posterior_true)}</div>
          <div class="query-meta">Previa P(I): <strong>${pct(a.previa, 1)}</strong> · P(I=F|e): ${pct(a.posterior_false)}</div>
        </div>
      </div>
      <div class="prior-lift">
        Bajo exactamente la misma evidencia, elevar la previa de <strong>${pct(b.previa, 1)}</strong> a <strong>${pct(a.previa, 1)}</strong>
        desplaza la probabilidad posterior en <strong>${diffPts >= 0 ? "+" : ""}${diffPts.toFixed(2)} pp</strong>
        (factor <strong>${factor.toFixed(2)}×</strong>).
      </div>
    `;

    renderCurvaSensibilidad(data.curva_sensibilidad, b, a);
  }

  function renderCurvaSensibilidad(puntos, base, alta) {
    const svg = $("#svg-sensibilidad");
    const W = 560, H = 270;
    const pad = { l: 52, r: 22, t: 20, b: 42 };
    const iw = W - pad.l - pad.r;
    const ih = H - pad.t - pad.b;

    const mapX = (prior) => pad.l + (prior / 0.5) * iw;
    const mapY = (post) => pad.t + (1 - post) * ih;

    let grid = "";
    for (let i = 0; i <= 4; i++) {
      const y = pad.t + (ih * i) / 4;
      const lbl = `${100 - i * 25}%`;
      grid += `<line x1="${pad.l}" y1="${y}" x2="${W - pad.r}" y2="${y}" stroke="var(--border-subtle)" stroke-dasharray="3 3"/>`;
      grid += `<text x="${pad.l - 8}" y="${y + 4}" text-anchor="end" fill="var(--text-muted)" font-size="11">${lbl}</text>`;
    }
    for (const p of [0, 0.1, 0.2, 0.3, 0.4, 0.5]) {
      const x = mapX(p);
      grid += `<text x="${x}" y="${H - 18}" text-anchor="middle" fill="var(--text-muted)" font-size="11">${Math.round(p * 100)}%</text>`;
    }

    const d = puntos
      .map((pt, i) => `${i === 0 ? "M" : "L"} ${mapX(pt.previa).toFixed(1)} ${mapY(pt.posterior).toFixed(1)}`)
      .join(" ");

    const area = `${d} L ${mapX(puntos[puntos.length - 1].previa).toFixed(1)} ${mapY(0)} L ${mapX(puntos[0].previa).toFixed(1)} ${mapY(0)} Z`;

    const marcador = (pt, color, label) => {
      if (pt.previa > 0.5) return "";
      const cx = mapX(pt.previa);
      const cy = mapY(pt.posterior_true);
      return `
        <circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="5.5" fill="${color}" stroke="var(--bg-surface)" stroke-width="2"/>
        <text x="${(cx + 8).toFixed(1)}" y="${(cy - 6).toFixed(1)}" fill="${color}" font-size="11" font-weight="700">${label}: ${pct(pt.posterior_true, 1)}</text>
      `;
    };

    svg.innerHTML = `
      ${grid}
      <path d="${area}" fill="var(--accent-primary-soft)"/>
      <path d="${d}" fill="none" stroke="var(--accent-primary)" stroke-width="2.6" stroke-linejoin="round"/>
      ${marcador(base, "var(--accent-primary)", "Normal")}
      ${marcador(alta, "var(--accent-danger)", "Alerta")}
      <text x="${pad.l + iw / 2}" y="${H - 3}" text-anchor="middle" fill="var(--text-secondary)" font-size="11" font-weight="600">Probabilidad Previa P(I = True)</text>
    `;
  }

  /* ------------------------------------------------------------------------
     Vista 4: Editor CPT en vivo
     ------------------------------------------------------------------------ */
  function renderEditorCPT() {
    const grid = $("#grid-cpt");
    grid.innerHTML = "";

    for (const varId of state.meta.orden_topologico) {
      const nodo = state.meta.nodos[varId];
      const padres = nodo.padres;
      const card = document.createElement("article");
      card.className = "card cpt-card";

      const subtitulo = padres.length
        ? `Padres: ${padres.join(", ")}`
        : "Nodo raíz (probabilidad previa)";

      card.innerHTML = `
        <div class="card-header" style="margin-bottom:4px">
          <div>
            <h2><span class="var-tag" style="margin-right:6px">${varId}</span>${NOMBRES_CORTOS[varId] || varId}</h2>
            <p class="card-subtitle">${subtitulo}</p>
          </div>
        </div>
      `;

      for (const [clave, valor] of Object.entries(nodo.cpt)) {
        const condTexto = padres.length
          ? padres
              .map((p, idx) => `${p}=${clave.split(",")[idx] === "true" ? "T" : "F"}`)
              .join(", ")
          : "Sin padres";

        const row = document.createElement("div");
        row.className = "cpt-row";
        row.innerHTML = `
          <span class="cpt-cond">P(${varId}=T | ${condTexto})</span>
          <input type="number" class="cpt-num tabular" min="0" max="1" step="0.01" value="${Number(valor).toFixed(2)}" />
          <input type="range" class="cpt-slider" min="0" max="1" step="0.01" value="${Number(valor)}" />
        `;

        const numInput = row.querySelector(".cpt-num");
        const slider = row.querySelector(".cpt-slider");
        let timer;

        const enviarCambio = (nuevoVal) => {
          const clamped = Math.max(0, Math.min(1, Number(nuevoVal)));
          if (Number.isNaN(clamped)) return;
          numInput.value = clamped.toFixed(2);
          slider.value = String(clamped);
          clearTimeout(timer);
          timer = setTimeout(async () => {
            try {
              const res = await api("/api/cpt", {
                method: "POST",
                body: JSON.stringify({ variable: varId, clave, valor: clamped }),
              });
              state.meta.nodos[varId].cpt[clave] = res.valor;
              actualizarEstadoModificado(res.modificado);
              ejecutarInferencia();
            } catch (err) {
              mostrarToast(`Error al actualizar CPT: ${err.message}`);
            }
          }, 80);
        };

        slider.addEventListener("input", (e) => enviarCambio(e.target.value));
        numInput.addEventListener("change", (e) => enviarCambio(e.target.value));

        card.appendChild(row);
      }

      grid.appendChild(card);
    }
  }

  function actualizarEstadoModificado(modificado) {
    $("#btn-reset-global").hidden = !modificado;
  }

  async function reiniciarCPT() {
    try {
      const res = await api("/api/reset", { method: "POST", body: "{}" });
      state.meta.nodos = res.nodos;
      actualizarEstadoModificado(false);
      renderEditorCPT();
      ejecutarInferencia();
      if (!$("#view-escenarios").hidden) cargarEscenarios();
      if (!$("#view-previas").hidden) cargarComparacionPrevias();
      mostrarToast("Parámetros CPT restaurados a los valores originales");
    } catch (err) {
      mostrarToast(`Error al restaurar: ${err.message}`);
    }
  }

  /* ------------------------------------------------------------------------
     Inicialización
     ------------------------------------------------------------------------ */
  async function init() {
    initNavegacion();

    try {
      state.meta = await api("/api/estado");
    } catch (err) {
      mostrarToast(`No se pudo conectar al servidor: ${err.message}`);
      return;
    }

    const badgePgmpy = $("#badge-pgmpy");
    if (state.meta.pgmpy_disponible) {
      badgePgmpy.className = "pill pill-ok";
      badgePgmpy.innerHTML = `<span class="dot"></span>pgmpy Verificado`;
    } else {
      badgePgmpy.className = "pill pill-warn";
      badgePgmpy.innerHTML = `<span class="dot"></span>pgmpy N/D`;
    }

    actualizarEstadoModificado(state.meta.modificado);
    construirDAG();
    construirControlesEvidencia();
    initControlesPrevias();

    $("#btn-refrescar-escenarios").addEventListener("click", cargarEscenarios);
    $("#btn-reset-cpt").addEventListener("click", reiniciarCPT);
    $("#btn-reset-global").addEventListener("click", reiniciarCPT);

    await ejecutarInferencia();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
