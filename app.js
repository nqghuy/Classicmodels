const API = {
  meta: "/api/meta",
  stats: "/api/stats",
  trend: "/api/revenue/trend",
  status: "/api/reports/status",
  products: "/api/reports/products",
  topCustomers: "/api/reports/top-customers",
  orders: "/api/orders",
  pivot: "/api/pivot",
  chat: "/api/chat"
};

const MONEY = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0
});
const NUMBER = new Intl.NumberFormat("en-US");
const CHART_COLORS = ["#1f6f54", "#d99a2b", "#bb5a38", "#3f6d82", "#6c7d47", "#8f5b33", "#234f63"];

let meta = null;
const chatHistory = [];

document.addEventListener("DOMContentLoaded", init);

async function init() {
  try {
    meta = await fetchJson(API.meta);
    hydrateControls(meta);
    bindEvents();
    await renderAll();
  } catch (error) {
    showError(error);
  }
}

async function renderAll() {
  await Promise.all([
    renderStats(),
    renderCharts(),
    renderReports(),
    renderSearch(),
    renderPivot()
  ]);
}

async function fetchJson(url, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "" && value !== "all") {
      query.set(key, value);
    }
  });
  const target = query.toString() ? `${url}?${query}` : url;
  const response = await fetch(target);
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.error || `Request failed: ${target}`);
  }
  return data;
}

async function postJson(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.error || `Request failed: ${url}`);
  }
  return data;
}

function hydrateControls(data) {
  fillSelect(document.querySelector("#trend-year"), data.years, "all");
  fillSelect(document.querySelector("#country-filter"), data.countries, "all");
  fillSelect(document.querySelector("#status-filter"), data.statuses, "all");
  addProductLineFilter(data.productLines);

  document.querySelector("#data-source").textContent = `${data.customers.length} customers via REST API`;
  document.querySelector("#data-range").textContent = `${data.dateRange.startDate} to ${data.dateRange.endDate}`;
}

function fillSelect(select, values, keepValue) {
  const existing = [...select.options].filter((option) => option.value === keepValue);
  select.replaceChildren(...existing);
  values.forEach((value) => select.append(new Option(value, value)));
}

function addProductLineFilter(productLines) {
  const controls = document.querySelector("#search .search-controls");
  if (document.querySelector("#productline-filter")) return;
  const select = document.createElement("select");
  select.id = "productline-filter";
  select.setAttribute("aria-label", "Filter by product line");
  select.append(new Option("All product lines", "all"));
  productLines.forEach((line) => select.append(new Option(line, line)));
  controls.append(select);
}

function currentFilters() {
  return {};
}

function searchFilters() {
  return {
    country: document.querySelector("#country-filter")?.value,
    status: document.querySelector("#status-filter")?.value,
    product_line: document.querySelector("#productline-filter")?.value,
    q: document.querySelector("#search-box")?.value.trim()
  };
}

async function renderStats() {
  const stats = await fetchJson(API.stats, currentFilters());
  const cards = [
    ["Order Revenue", MONEY.format(stats.revenue), "SUM(quantityOrdered x priceEach)"],
    ["Payments Collected", MONEY.format(stats.payments), "From payments table"],
    ["Customers", NUMBER.format(stats.customers), `${NUMBER.format(stats.products)} products in result`],
    ["Orders", NUMBER.format(stats.orders), `${MONEY.format(stats.averageOrder)} average order`]
  ];

  document.querySelector("#stat-cards").innerHTML = cards
    .map(([label, value, note]) => `<article class="stat-card"><span>${label}</span><strong>${value}</strong><small>${note}</small></article>`)
    .join("");
}

async function renderCharts() {
  const selectedYear = document.querySelector("#trend-year").value;
  const trendParams = { ...currentFilters() };
  if (selectedYear !== "all") {
    trendParams.start_date = `${selectedYear}-01-01`;
    trendParams.end_date = `${selectedYear}-12-31`;
  }

  const [trend, status, products] = await Promise.all([
    fetchJson(API.trend, trendParams),
    fetchJson(API.status, currentFilters()),
    fetchJson(API.products, currentFilters())
  ]);

  drawBarChart(document.querySelector("#revenue-chart"), trend.map((row) => row.period), trend.map((row) => row.revenue), {
    formatter: MONEY,
    color: "#1f6f54"
  });
  drawDoughnutChart(document.querySelector("#status-chart"), status.map((row) => row.status), status.map((row) => row.revenue), MONEY);
  drawHorizontalBars(document.querySelector("#productline-chart"), products.map((row) => row.productLine), products.map((row) => row.revenue), MONEY);
}

async function renderReports() {
  const [customers, orders] = await Promise.all([
    fetchJson(API.topCustomers, { ...currentFilters(), limit: 10 }),
    fetchJson(API.orders, { limit: 10 })
  ]);

  document.querySelector("#top-customers").innerHTML = customers
    .map((row) => `
      <tr>
        <td>${escapeHtml(row.customerName)}</td>
        <td>${escapeHtml(row.country)}</td>
        <td>${NUMBER.format(row.orders)}</td>
        <td>${MONEY.format(row.revenue)}</td>
      </tr>
    `)
    .join("");

  document.querySelector("#recent-orders").innerHTML = orders
    .map((order) => `
      <tr>
        <td>#${order.orderNumber}</td>
        <td>${order.orderDate}</td>
        <td>${escapeHtml(order.customerName)}</td>
        <td>${statusBadge(order.status)}</td>
        <td>${MONEY.format(order.revenue)}</td>
      </tr>
    `)
    .join("");
}

async function renderSearch() {
  const rows = await fetchJson(API.orders, { ...searchFilters(), limit: 150 });
  document.querySelector("#search-results").innerHTML = rows
    .map((order) => `
      <tr>
        <td>#${order.orderNumber}</td>
        <td>${order.orderDate}</td>
        <td>${escapeHtml(order.customerName)}</td>
        <td>${escapeHtml(`${order.city}, ${order.country}`)}</td>
        <td>${statusBadge(order.status)}</td>
        <td>${NUMBER.format(order.quantity)}</td>
        <td>${MONEY.format(order.revenue)}</td>
      </tr>
    `)
    .join("");

  document.querySelector("#search-count").textContent =
    `${NUMBER.format(rows.length)} matching orders returned from REST API`;
}

async function renderPivot() {
  const row = document.querySelector("#pivot-row").value;
  const col = document.querySelector("#pivot-col").value;
  const metric = document.querySelector("#pivot-metric").value;
  const data = await fetchJson(API.pivot, { ...currentFilters(), row, col, metric });
  const rows = [...new Set(data.rows.map((item) => item.rowKey))].sort(sortNatural);
  const cols = [...new Set(data.rows.map((item) => item.colKey))].sort(sortNatural);
  const values = new Map(data.rows.map((item) => [`${item.rowKey}|||${item.colKey}`, Number(item.value)]));
  const formatter = metric === "revenue" ? (value) => MONEY.format(value) : (value) => NUMBER.format(value);

  const rowTotals = new Map();
  const colTotals = new Map();
  data.rows.forEach((item) => {
    rowTotals.set(item.rowKey, (rowTotals.get(item.rowKey) || 0) + Number(item.value));
    colTotals.set(item.colKey, (colTotals.get(item.colKey) || 0) + Number(item.value));
  });
  const grandTotal = [...rowTotals.values()].reduce((total, value) => total + value, 0);

  const head = `<thead><tr><th>${labelFor(row)} / ${labelFor(col)}</th>${cols.map((item) => `<th>${escapeHtml(item)}</th>`).join("")}<th>Total</th></tr></thead>`;
  const body = rows.map((rowKey) => {
    const cells = cols.map((colKey) => formatter(values.get(`${rowKey}|||${colKey}`) || 0));
    return `<tr><th>${escapeHtml(rowKey)}</th>${cells.map((cell) => `<td>${cell}</td>`).join("")}<td>${formatter(rowTotals.get(rowKey) || 0)}</td></tr>`;
  }).join("");
  const foot = `<tfoot><tr><td>Total</td>${cols.map((colKey) => `<td>${formatter(colTotals.get(colKey) || 0)}</td>`).join("")}<td>${formatter(grandTotal)}</td></tr></tfoot>`;

  document.querySelector("#pivot-table").innerHTML = `<table>${head}<tbody>${body}</tbody>${foot}</table>`;
}

function bindEvents() {
  document.querySelector("#trend-year").addEventListener("change", renderCharts);
  document.querySelector("#search-box").addEventListener("input", debounce(renderSearch, 180));
  ["country-filter", "status-filter", "productline-filter"].forEach((id) => {
    document.querySelector(`#${id}`).addEventListener("change", debounce(renderSearch, 180));
  });
  ["pivot-row", "pivot-col", "pivot-metric"].forEach((id) => {
    document.querySelector(`#${id}`).addEventListener("change", renderPivot);
  });
  document.querySelector("#chat-form").addEventListener("submit", handleChatSubmit);
}

async function handleChatSubmit(event) {
  event.preventDefault();
  const input = document.querySelector("#chat-input");
  const message = input.value.trim();
  if (!message) return;

  input.value = "";
  input.disabled = true;
  appendChatMessage("user", message);
  const typing = appendChatMessage("assistant", "Thinking...");

  try {
    const data = await postJson(API.chat, {
      message,
      history: chatHistory.slice(-6)
    });
    typing.textContent = data.reply;
    chatHistory.push({ role: "user", content: message });
    chatHistory.push({ role: "assistant", content: data.reply });
  } catch (error) {
    typing.textContent = error.message;
    typing.classList.add("error-message");
  } finally {
    input.disabled = false;
    input.focus();
  }
}

function appendChatMessage(role, content) {
  const messages = document.querySelector("#chat-messages");
  const item = document.createElement("div");
  item.className = `chat-message ${role}`;
  item.textContent = content;
  messages.append(item);
  messages.scrollTop = messages.scrollHeight;
  return item;
}

function drawBarChart(canvas, labels, values, options = {}) {
  const ctx = setupCanvas(canvas);
  const width = canvas.width;
  const height = canvas.height;
  const pad = { top: 28, right: 18, bottom: 72, left: 86 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const max = Math.max(...values, 1);
  const barWidth = plotWidth / Math.max(values.length, 1) * 0.66;

  drawAxes(ctx, pad, width, height);
  values.forEach((value, index) => {
    const x = pad.left + index * (plotWidth / values.length) + (plotWidth / values.length - barWidth) / 2;
    const barHeight = value / max * plotHeight;
    ctx.fillStyle = options.color || CHART_COLORS[0];
    roundRect(ctx, x, pad.top + plotHeight - barHeight, barWidth, barHeight, 8);
    ctx.fill();
  });

  ctx.fillStyle = "#65736b";
  ctx.font = "16px Georgia";
  ctx.fillText(options.formatter?.format(max) || NUMBER.format(max), 10, pad.top + 12);
  drawRotatedLabels(ctx, labels, pad, plotWidth, height);
}

function drawHorizontalBars(canvas, labels, values, formatter) {
  const ctx = setupCanvas(canvas);
  const width = canvas.width;
  const height = canvas.height;
  const pad = { top: 10, right: 106, bottom: 18, left: 118 };
  const max = Math.max(...values, 1);
  const barGap = 10;
  const barHeight = (height - pad.top - pad.bottom - barGap * Math.max(values.length - 1, 0)) / Math.max(values.length, 1);

  labels.forEach((label, index) => {
    const y = pad.top + index * (barHeight + barGap);
    const barWidth = (width - pad.left - pad.right) * (values[index] / max);
    ctx.fillStyle = CHART_COLORS[index % CHART_COLORS.length];
    roundRect(ctx, pad.left, y, barWidth, barHeight, 8);
    ctx.fill();
    ctx.fillStyle = "#17211b";
    ctx.font = "15px Georgia";
    ctx.fillText(truncateText(ctx, label, pad.left - 18), 10, y + barHeight * 0.68);
    ctx.fillStyle = "#65736b";
    ctx.textAlign = "right";
    ctx.font = "14px Georgia";
    ctx.fillText(formatter.format(values[index]), width - 10, y + barHeight * 0.68);
    ctx.textAlign = "left";
  });
}

function drawDoughnutChart(canvas, labels, values, formatter) {
  const ctx = setupCanvas(canvas);
  const width = canvas.width;
  const height = canvas.height;
  const radius = Math.min(width, height) * 0.24;
  const centerX = width * 0.33;
  const centerY = height * 0.48;
  const total = values.reduce((a, b) => a + b, 0);
  let start = -Math.PI / 2;

  values.forEach((value, index) => {
    const slice = total ? (value / total) * Math.PI * 2 : 0;
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.arc(centerX, centerY, radius, start, start + slice);
    ctx.closePath();
    ctx.fillStyle = CHART_COLORS[index % CHART_COLORS.length];
    ctx.fill();
    start += slice;
  });

  ctx.globalCompositeOperation = "destination-out";
  ctx.beginPath();
  ctx.arc(centerX, centerY, radius * 0.58, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalCompositeOperation = "source-over";

  labels.forEach((label, index) => {
    const y = 34 + index * 30;
    ctx.fillStyle = CHART_COLORS[index % CHART_COLORS.length];
    ctx.fillRect(width * 0.68, y - 13, 14, 14);
    ctx.fillStyle = "#17211b";
    ctx.font = "20px Georgia";
    ctx.fillText(label, width * 0.68 + 22, y);
  });

  ctx.fillStyle = "#65736b";
  ctx.textAlign = "center";
  ctx.font = "15px Georgia";
  ctx.fillText(compactMoney(total), centerX, centerY + 6);
  ctx.textAlign = "left";
}

function setupCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(320, Math.floor(rect.width));
  canvas.height = Number(canvas.getAttribute("height"));
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  return ctx;
}

function drawAxes(ctx, pad, width, height) {
  ctx.strokeStyle = "#e3d4bb";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad.left, pad.top);
  ctx.lineTo(pad.left, height - pad.bottom);
  ctx.lineTo(width - pad.right, height - pad.bottom);
  ctx.stroke();
}

function drawRotatedLabels(ctx, labels, pad, plotWidth, height) {
  const step = Math.max(1, Math.ceil(labels.length / 7));
  ctx.fillStyle = "#65736b";
  ctx.font = "14px Georgia";
  labels.forEach((label, index) => {
    if (index % step !== 0) return;
    const x = pad.left + index * (plotWidth / labels.length) + 8;
    ctx.save();
    ctx.translate(x, height - 24);
    ctx.rotate(-Math.PI / 4);
    ctx.fillText(label, 0, 0);
    ctx.restore();
  });
}

function truncateText(ctx, text, maxWidth) {
  const value = String(text);
  if (ctx.measureText(value).width <= maxWidth) return value;
  let trimmed = value;
  while (trimmed.length > 3 && ctx.measureText(`${trimmed}...`).width > maxWidth) {
    trimmed = trimmed.slice(0, -1);
  }
  return `${trimmed}...`;
}

function compactMoney(value) {
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `$${Math.round(value / 1_000)}K`;
  return MONEY.format(value);
}

function roundRect(ctx, x, y, width, height, radius) {
  const safeRadius = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + safeRadius, y);
  ctx.arcTo(x + width, y, x + width, y + height, safeRadius);
  ctx.arcTo(x + width, y + height, x, y + height, safeRadius);
  ctx.arcTo(x, y + height, x, y, safeRadius);
  ctx.arcTo(x, y, x + width, y, safeRadius);
  ctx.closePath();
}

function statusBadge(status) {
  return `<span class="badge ${String(status).toLowerCase().replace(/\s+/g, "-")}">${escapeHtml(status)}</span>`;
}

function labelFor(key) {
  return {
    customer: "Customer",
    country: "Country",
    status: "Order Status",
    productLine: "Product Line",
    product: "Product",
    year: "Year",
    month: "Month"
  }[key] || key;
}

function sortNatural(a, b) {
  return String(a).localeCompare(String(b), undefined, { numeric: true });
}

function debounce(fn, wait) {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[char]));
}

function showError(error) {
  document.querySelector("main").insertAdjacentHTML("afterbegin", `
    <section class="section">
      <div class="error">
        <strong>Dashboard could not start.</strong>
        <p>${escapeHtml(error.message)}</p>
        <p>Run <code>python3 server.py</code> in this folder, then open <code>http://localhost:8000</code>.</p>
      </div>
    </section>
  `);
}
