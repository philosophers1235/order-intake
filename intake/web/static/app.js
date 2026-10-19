// Review screen. The server sends the checked order once; everything a
// person changes here stays in the page until they download the CSV.

const { order, names } = JSON.parse(document.getElementById("order-data").textContent);
const lines = order.lines;

const KIND = {
  unknown_item: "Not in catalog",
  code_typo: "Code",
  ambiguous_item: "Which item?",
  uncertain_match: "Match",
  discontinued: "Discontinued",
  missing_quantity: "Quantity",
  unit: "Unit",
  unusual_quantity: "Quantity",
  price: "Price",
  hard_to_read: "Legibility",
  unknown_customer: "Customer",
};

// Issues a person can only resolve in the ERP, not by accepting what was written.
const NO_KEEP = new Set(["unknown_item", "ambiguous_item", "missing_quantity", "discontinued"]);

const fmt = (n) => (n == null ? "?" : Number(n).toLocaleString("en", { maximumFractionDigits: 3 }));

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("data-")) node.setAttribute(key, value);
    else node[key] = value;
  }
  for (const child of children) if (child != null) node.append(child);
  return node;
}

function applyLabel(s) {
  if (s.code && s.quantity != null) return `Use ${s.code}, ${fmt(s.quantity)}`;
  if (s.code) return `Use ${s.code}`;
  return `Set ${fmt(s.quantity)}`;
}

function issueRow(line, issue, index) {
  const actions = el("span", { class: "actions" });
  if (issue.suggestion) {
    actions.append(el("button", {
      type: "button", class: "apply", textContent: applyLabel(issue.suggestion),
      title: issue.suggestion.reason, "data-line": line.number, "data-issue": index, "data-action": "apply",
    }));
  }
  if (!NO_KEEP.has(issue.kind) && line.code && line.quantity != null) {
    actions.append(el("button", {
      type: "button", class: "keep", textContent: "Keep as written",
      "data-line": line.number, "data-issue": index, "data-action": "keep",
    }));
  }
  return el("li", { class: "issue" },
    el("span", { class: "kind", textContent: KIND[issue.kind] || issue.kind }),
    el("span", { class: "message" },
      issue.message,
      issue.suggestion ? el("span", { class: "why", textContent: issue.suggestion.reason }) : null),
    actions);
}

function lineRow(line) {
  const ready = line.issues.length === 0;
  const item = line.code
    ? el("span", { class: "item" }, el("b", { textContent: line.code }), " ", line.name || "")
    : el("span", { class: "item none", textContent: "No match" });
  const row = el("li", { class: `line ${ready ? "ready" : "check"}${line.edited ? " edited" : ""}` },
    el("span", { class: "num", textContent: line.number }),
    el("q", { class: "raw", textContent: line.extracted.raw }),
    item,
    el("span", { class: "qty" }, fmt(line.quantity), line.unit ? el("small", { textContent: ` ${line.unit}` }) : null),
    el("span", { class: "status", textContent: ready ? (line.edited ? "Fixed" : "Ready") : "Check" }));
  if (!ready) row.append(el("ul", { class: "issues" }, ...line.issues.map((i, n) => issueRow(line, i, n))));
  return row;
}

function render() {
  document.getElementById("lines").replaceChildren(...lines.map(lineRow));

  const box = document.getElementById("order-issues");
  box.replaceChildren(...order.issues.map((i) =>
    el("p", { class: "order-issue" }, el("span", { class: "kind", textContent: KIND[i.kind] || i.kind }), i.message)));

  const ready = lines.filter((l) => l.issues.length === 0).length;
  document.getElementById("ready-count").textContent =
    `${ready} of ${lines.length} lines ready` + (ready === lines.length ? "" : `, ${lines.length - ready} to check`);
  document.getElementById("ready-bar").style.width = `${(100 * ready) / Math.max(lines.length, 1)}%`;
}

document.getElementById("lines").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const line = lines.find((l) => l.number === Number(button.dataset.line));
  const [issue] = line.issues.splice(Number(button.dataset.issue), 1);
  if (button.dataset.action === "apply") {
    const s = issue.suggestion;
    if (s.code) {
      line.code = s.code;
      line.name = names[s.code] || line.name;
      // A new item makes the old match warnings meaningless.
      line.issues = line.issues.filter((i) => !["code_typo", "uncertain_match", "discontinued"].includes(i.kind));
    }
    if (s.quantity != null) line.quantity = s.quantity;
  }
  line.edited = true;
  render();
});

function csvCell(value) {
  const text = value == null ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

document.getElementById("export").addEventListener("click", () => {
  const head = ["customer_id", "customer_reference", "line", "code", "description", "quantity", "unit", "status", "issues"];
  const rows = lines.map((l) => [
    order.customer_id, order.order.customer_reference, l.number, l.code,
    l.name || l.extracted.description, l.quantity, l.unit,
    l.issues.length ? "review" : "ok", l.issues.map((i) => i.message).join(" | "),
  ]);
  const csv = [head, ...rows].map((r) => r.map(csvCell).join(",")).join("\n") + "\n";
  const link = el("a", {
    href: URL.createObjectURL(new Blob([csv], { type: "text/csv" })),
    download: order.source.replace(/\.[^.]+$/, "") + ".csv",
  });
  link.click();
  URL.revokeObjectURL(link.href);
});

render();
