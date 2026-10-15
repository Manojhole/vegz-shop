const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const state = { token: localStorage.getItem("vegzShopToken") || "", shop: null, products: [], orders: [], view: "overview", productFilter: "all", orderFilter: "all" };
const API = "";
const money = (value) => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const vegetables = {tomato:"🍅",potato:"🥔",onion:"🧅",carrot:"🥕",spinach:"🥬",cabbage:"🥬",broccoli:"🥦",cauliflower:"🥦",capsicum:"🫑",chilli:"🌶️",cucumber:"🥒",pumpkin:"🎃",peas:"🫛",corn:"🌽",lemon:"🍋",garlic:"🧄",ginger:"🫚",beetroot:"🫜"};
let toastTimer;
function toast(message, error = false) {
  const el = $("#toast"); el.textContent = message; el.className = "toast show" + (error ? " error" : "");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.className = "toast"; }, 2900);
}
async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers.Authorization = "Bearer " + state.token;
  let response;
  try { response = await fetch(API + path, { ...options, headers }); }
  catch { throw new Error("Cannot reach the Vegz Shop API. Check that the server is running."); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && state.token) signOut(false);
    throw new Error(data.detail || "Something went wrong. Please try again.");
  }
  return data;
}
function setBusy(button, busy, label = "Saving…") {
  if (!button) return;
  if (busy) { button.dataset.original = button.textContent; button.disabled = true; button.textContent = label; }
  else { button.disabled = false; button.textContent = button.dataset.original || "Save"; }
}
async function login(phone, code, shopType, city) {
  const result = await api("/api/auth/demo-login", { method: "POST", body: JSON.stringify({ phone, demo_code: code, shop_type: shopType, city }) });
  state.token = result.access_token; localStorage.setItem("vegzShopToken", state.token);
  state.shop = result.shop; $("#login-screen").classList.add("hidden"); $("#app-shell").classList.remove("hidden");
  await refreshAll(); showView("overview");
}
function signOut(showToast = true) {
  state.token = ""; state.shop = null; localStorage.removeItem("vegzShopToken");
  $("#app-shell").classList.add("hidden"); $("#login-screen").classList.remove("hidden");
  if (showToast) toast("You have signed out.");
}
async function refreshAll() {
  const [shop, products, orders] = await Promise.all([api("/api/shop"), api("/api/products"), api("/api/orders")]);
  state.shop = shop; state.products = products; state.orders = orders;
  renderAll();
}
function renderAll() {
  if (!state.shop) return;
  const shop = state.shop, products = state.products, orders = state.orders;
  $("#sidebar-shop-name").textContent = shop.name; $("#top-shop-name").textContent = shop.name;
  $("#nav-products-count").textContent = products.length;
  $("#nav-orders-count").textContent = orders.filter(o => o.status === "placed").length;
  $("#stat-products").textContent = products.length;
  $("#stat-in-stock").textContent = products.filter(p => p.stock_qty > 0 && p.is_available).length;
  $("#stat-new-orders").textContent = orders.filter(o => o.status === "placed").length;
  $("#stat-sales").textContent = money(orders.filter(o => o.status !== "cancelled" && o.created_at.slice(0,10) === new Date().toISOString().slice(0,10)).reduce((s,o) => s + Number(o.total_amount), 0));
  $("#tab-new-count").textContent = orders.filter(o => o.status === "placed").length;
  $("#shop-name").value = shop.name; $("#shop-address").value = shop.address || ""; $("#shop-type-setting").value = shop.shop_type === "grocery" ? "Grocery shop" : "Vegetable shop"; $("#shop-city-setting").value = shop.city || "Hubli";
  $("#shop-open-toggle").checked = shop.is_open; $("#accept-orders-toggle").checked = shop.accepts_orders;
  $("#availability-note").textContent = shop.is_open && shop.accepts_orders ? "✓ Your shop is open and accepting orders. Customers can place new orders." : !shop.is_open ? "Your shop is marked closed. Customers should not place new orders." : "Your shop is open, but new orders are paused.";
  $("#overview-orders").innerHTML = renderOrderRows(orders.filter(o => ["placed","accepted","preparing"].includes(o.status)).slice(0,4), true);
  if (!orders.some(o => ["placed","accepted","preparing"].includes(o.status))) $("#overview-orders").innerHTML = emptyInline("No pending orders", "Incoming orders will show here as soon as customers order.");
  renderInventoryPreview(); renderProducts(); renderOrders();
}
function emptyInline(title, desc) { return `<div class="empty-state"><div>🧺</div><h3>${esc(title)}</h3><p>${esc(desc)}</p></div>`; }
function statusPill(status) { return `<span class="status-pill status-${esc(status)}">${esc(status.replaceAll("_"," "))}</span>`; }
function statusActions(order, compact) {
  const actions = {
    placed: [["accepted","Accept order","primary"],["rejected","Reject order","danger"],["cancelled","Cancel","danger"]],
    accepted: [["preparing","Start preparing","primary"],["cancelled","Cancel","danger"]],
    preparing: [["ready","Mark ready","primary"],["cancelled","Cancel","danger"]],
    ready: [["out_for_delivery","Out for delivery","primary"]],
    out_for_delivery: [["delivered","Mark delivered","primary"]],
    delivered: [], rejected: [], cancelled: []
  }[order.status] || [];
  return actions.map(([next,label,kind]) => `<button class="btn ${kind === "danger" ? "danger" : "primary"} ${compact ? "small" : ""}" data-order-action="${next}" data-order-id="${order.id}">${label}</button>`).join("");
}
function renderOrderRows(orders, compact = false) {
  if (!orders.length) return "";
  return orders.map(o => `<article class="order-card">
    <div class="order-primary"><strong>Order #VGZ-${String(o.id).padStart(4,"0")}</strong><small>${esc(o.customer_name)} · ${esc(o.customer_phone || "Phone not shared")}</small><small>${esc(o.note || "Items from customer order")}</small><small>${new Date(o.created_at).toLocaleString("en-IN",{dateStyle:"medium",timeStyle:"short"})}</small></div>
    <div class="order-secondary">${statusPill(o.status)}<small>${esc(o.delivery_address || "Delivery address not set")}</small><strong>${money(o.total_amount)}</strong></div>
    <div class="order-actions">${statusActions(o, compact)}</div>
  </article>`).join("");
}
function renderInventoryPreview() {
  const chosen = [...state.products].sort((a,b) => {
    const aa = a.stock_qty <= 0 || !a.is_available ? 0 : a.stock_qty < 5 ? 1 : 2;
    const bb = b.stock_qty <= 0 || !b.is_available ? 0 : b.stock_qty < 5 ? 1 : 2;
    return aa - bb;
  }).slice(0,6);
  $("#inventory-preview").innerHTML = chosen.length ? chosen.map(p => {
    const status = p.stock_qty <= 0 || !p.is_available ? "Out of stock" : p.stock_qty < 5 ? "Low stock" : "In stock";
    const cls = p.stock_qty <= 0 || !p.is_available ? "stock-out" : p.stock_qty < 5 ? "stock-low" : "stock-ok";
    return `<div class="inventory-mini"><div class="veg-icon">${vegEmoji(p.name)}</div><div style="min-width:0"><strong>${esc(p.name)}</strong><small>${p.stock_qty} ${esc(p.unit)} · ${money(p.price)}/${esc(p.unit)}</small></div><span class="stock-label ${cls}">${status}</span></div>`;
  }).join("") : emptyInline("Catalog is empty","Add vegetables to see your inventory here.");
}
function vegEmoji(name) {
  const lower = String(name).toLowerCase();
  const found = Object.keys(vegetables).find(key => lower.includes(key));
  return found ? vegetables[found] : "🥗";
}
function renderProducts() {
  const term = ($("#product-search")?.value || "").trim().toLowerCase();
  const filter = $("#stock-filter")?.value || "all";
  const products = state.products.filter(p => p.name.toLowerCase().includes(term) || p.category.toLowerCase().includes(term))
    .filter(p => filter === "all" || (filter === "in" ? p.stock_qty > 0 && p.is_available : p.stock_qty <= 0 || !p.is_available));
  $("#catalog-summary-text").textContent = `${products.length} vegetable${products.length === 1 ? "" : "s"} shown`;
  $("#product-grid").innerHTML = products.map(p => {
    const inStock = p.stock_qty > 0 && p.is_available;
    const badge = p.stock_qty <= 0 ? '<span class="status-pill status-cancelled">Out of stock</span>' : !p.is_available ? '<span class="status-pill status-cancelled">Hidden</span>' : p.stock_qty < 5 ? '<span class="status-pill status-placed">Low stock</span>' : '<span class="status-pill status-delivered">In stock</span>';
    const imageUrl = (p.image_urls && p.image_urls.length ? p.image_urls[0] : p.image_url) || "";
    const image = imageUrl ? '<img src="' + esc(imageUrl) + '" alt="' + esc(p.name) + '" loading="lazy" onerror="this.remove();this.parentElement.querySelector(\'.product-fallback\').classList.remove(\'hidden\')">' : "";
    return `<article class="product-card"><div class="product-card-art">${image}<span class="product-fallback ${p.image_url ? "hidden" : ""}">${vegEmoji(p.name)}</span>${badge}</div><div class="product-content">
      <div class="product-category">${esc(p.category)}</div><h3>${esc(p.name)}</h3><div class="product-price">${money(p.price)} <span>/ ${esc(p.unit)}</span></div>
      <div class="product-stock-line"><span>Stock available</span><strong>${Number(p.stock_qty)} ${esc(p.unit)}</strong></div>
      <div class="product-card-actions"><button class="btn secondary small" data-edit-product="${p.id}">✎ Edit</button><button class="inline-toggle ${inStock ? "enabled" : ""}" data-toggle-product="${p.id}">${p.is_available ? "Visible ✓" : "Hidden"} </button></div>
      <div class="product-card-actions"><button class="inline-toggle" data-delete-product="${p.id}">Remove item</button><button class="inline-toggle" data-quick-stock="${p.id}">Update stock</button></div>
    </div></article>`;
  }).join("");
  $("#products-empty").classList.toggle("hidden", products.length > 0);
  $("#product-grid").classList.toggle("hidden", products.length === 0);
}
function renderOrders() {
  const orders = state.orderFilter === "all" ? state.orders : state.orders.filter(o => o.status === state.orderFilter);
  $("#orders-list").innerHTML = renderOrderRows(orders, true);
  $("#orders-empty").classList.toggle("hidden", orders.length > 0);
  $("#orders-list").classList.toggle("hidden", orders.length === 0);
}
function showView(view) {
  state.view = view;
  $$(".view").forEach(el => el.classList.add("hidden"));
  $("#view-" + view).classList.remove("hidden");
  $$(".nav-item").forEach(el => el.classList.toggle("active", el.dataset.view === view));
  const names = {overview:"Overview",products: state.shop?.shop_type === "grocery" ? "My groceries" : "My vegetables",orders:"Orders",settings:"Shop settings"};
  $("#breadcrumb-title").textContent = names[view]; $("#page-title").textContent = ({overview:"Good morning 👋",products: state.shop?.shop_type === "grocery" ? "Your groceries 🛒" : "Your vegetables 🥬",orders:"Manage orders 📦",settings:"Your shop settings ⚙"})[view];
  $("#page-subtitle").textContent = ({overview:"Here's what's happening with your shop today.",products:"Keep prices, stock and availability accurate.",orders:"Accept orders and keep customers updated.",settings:"Control your shop profile and order availability."})[view];
  if (view === "orders") renderOrders();
  window.scrollTo({top:0,behavior:"smooth"});
}
function openProduct(product = null) {
  $("#product-form").reset();
  $("#product-id").value = product?.id || "";
  $("#product-dialog-title").textContent = product ? "Edit vegetable" : "Add vegetable";
  $("#product-name").value = product?.name || "";
  const allowedCategories = (state.shop?.shop_type || "vegetable") === "grocery" ? ["Grocery", "Spices"] : ["Daily essentials", "Fresh picks", "Leafy greens", "Root vegetables", "Seasonal", "Vegetables"];
  $("#product-category").innerHTML = allowedCategories.map(category => `<option>${esc(category)}</option>`).join("");
  $("#product-category").value = allowedCategories.includes(product?.category) ? product.category : allowedCategories[0];
  $("#product-unit").value = product?.unit || "kg";
  $("#product-price").value = product?.price ?? "";
  $("#product-stock").value = product?.stock_qty ?? 0;
  $("#product-out-of-stock").checked = (product?.stock_qty ?? 0) <= 0;
  $("#product-images").value = "";
  const imageList = product?.image_urls?.length ? product.image_urls : (product?.image_url ? [product.image_url] : []);
  $("#existing-product-images").innerHTML = imageList.map(url => '<img src="' + esc(url) + '" alt="Current product photo">').join("");
  $("#product-description").value = product?.description || "";
  $("#product-available").checked = product?.is_available ?? true;
  $("#product-dialog").showModal();
}
async function withButton(button, task) {
  setBusy(button,true);
  try { await task(); }
  catch (error) { toast(error.message || "Something went wrong.",true); }
  finally { setBusy(button,false); }
}
async function changeOrderStatus(orderId, next, button) {
  const labels = {accepted:"Accept this order?",rejected:"Reject this order?",cancelled:"Cancel this order?",preparing:"Start preparing this order?",ready:"Mark this order ready?",out_for_delivery:"Mark this order out for delivery?",delivered:"Mark this order delivered?"};
  if (next === "cancelled" && !confirm("Cancel order #" + orderId + "? This action cannot be undone.")) return;
  const reason = next === "rejected" ? prompt("Why are you rejecting this order? This reason will be saved for customer support.") : "";
  if (next === "rejected" && !reason?.trim()) { toast("A rejection reason is required.", true); return; }
  await withButton(button, async () => {
    await api(`/api/orders/${orderId}/status`, {method:"PATCH",body:JSON.stringify({status:next,reason:reason||""})});
    await refreshAll(); toast(labels[next] ? "Order updated: " + next.replaceAll("_"," ") + "." : "Order updated.");
  });
}
async function updateShop(payload, button) {
  await withButton(button, async () => { state.shop = await api("/api/shop",{method:"PATCH",body:JSON.stringify(payload)}); renderAll(); toast("Shop settings saved."); });
}
$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const button = event.submitter; setBusy(button,true,"Signing in…");
  try { await login($("#phone").value.trim(),$("#demo-code").value.trim(),$("#shop-type").value,$("#shop-city").value); toast("Welcome to your shop!"); }
  catch (error) { toast(error.message,true); }
  finally { setBusy(button,false); }
});
$("#logout-btn").addEventListener("click", () => signOut());
$("#refresh-btn").addEventListener("click", async () => { try { await refreshAll(); toast("Shop data refreshed."); } catch(e){toast(e.message,true);} });
$("#orders-refresh").addEventListener("click", async () => { try { await refreshAll(); toast("Orders refreshed."); } catch(e){toast(e.message,true);} });
$("#nav").addEventListener("click", e => { const nav = e.target.closest("[data-view]"); if (nav) showView(nav.dataset.view); });
document.body.addEventListener("click", async e => {
  const goto = e.target.closest("[data-goto]"); if (goto) return showView(goto.dataset.goto);
  const edit = e.target.closest("[data-edit-product]"); if (edit) return openProduct(state.products.find(p => p.id === Number(edit.dataset.editProduct)));
  const toggle = e.target.closest("[data-toggle-product]"); if (toggle) {
    const p = state.products.find(p => p.id === Number(toggle.dataset.toggleProduct)); if (!p) return;
    try { await api(`/api/products/${p.id}`,{method:"PATCH",body:JSON.stringify({is_available:!p.is_available})}); await refreshAll(); toast(p.is_available?"Listing hidden from customers.":"Listing made visible."); } catch(err){toast(err.message,true);} return;
  }
  const del = e.target.closest("[data-delete-product]"); if (del) {
    const p = state.products.find(p => p.id === Number(del.dataset.deleteProduct)); if (!p || !confirm("Remove " + p.name + " from your catalog?")) return;
    try { await api(`/api/products/${p.id}`,{method:"DELETE"}); await refreshAll(); toast("Product removed."); } catch(err){toast(err.message,true);} return;
  }
  const quick = e.target.closest("[data-quick-stock]"); if (quick) {
    const p = state.products.find(p => p.id === Number(quick.dataset.quickStock)); if (!p) return;
    const answer = prompt(`Stock quantity for ${p.name} (${p.unit}):`,p.stock_qty);
    if (answer === null) return; const qty = Number(answer);
    if (!Number.isInteger(qty) || qty < 0) return toast("Enter a whole number of zero or more.",true);
    try { await api(`/api/products/${p.id}`,{method:"PATCH",body:JSON.stringify({stock_qty:qty})}); await refreshAll(); toast("Stock updated."); } catch(err){toast(err.message,true);} return;
  }
  const orderAction = e.target.closest("[data-order-action]"); if (orderAction) {
    e.preventDefault(); return changeOrderStatus(Number(orderAction.dataset.orderId),orderAction.dataset.orderAction,orderAction);
  }
});
$("#add-product-btn").addEventListener("click",() => openProduct());
$("#empty-add-btn").addEventListener("click",() => openProduct());
$("#close-product-dialog").addEventListener("click",() => $("#product-dialog").close());
$("#cancel-product").addEventListener("click",() => $("#product-dialog").close());
$("#product-form").addEventListener("submit",async e=>{
  e.preventDefault();
  const id = $("#product-id").value;
  const payload = {
    name:$("#product-name").value.trim(), category:$("#product-category").value, unit:$("#product-unit").value,
    price:Number($("#product-price").value), stock_qty:$("#product-out-of-stock").checked ? 0 : Number($("#product-stock").value),
    image_url:"", description:$("#product-description").value.trim(),
    is_available:$("#product-available").checked
  };
  if (!payload.name || !Number.isFinite(payload.price) || payload.price <= 0 || !Number.isInteger(payload.stock_qty) || payload.stock_qty < 0) return toast("Check the vegetable name, positive price, and whole-number stock.",true);
  const button = $("#save-product-btn"); setBusy(button,true,"Saving…");
  try {
    const saved = await api(id ? "/api/products/"+id : "/api/products",{method:id?"PATCH":"POST",body:JSON.stringify(payload)});
    const photos = Array.from($("#product-images").files || []);
    if (photos.length > 3) throw new Error("Choose no more than 3 photos.");
    if (photos.length) {
      const form = new FormData(); photos.forEach(file => form.append("files", file));
      const response = await fetch("/api/products/"+saved.id+"/images", {method:"POST",headers:{Authorization:"Bearer "+state.token},body:form});
      const data = await response.json().catch(()=>({}));
      if (!response.ok) throw new Error(data.detail || "Could not upload product photos.");
    }
    $("#product-dialog").close(); await refreshAll(); toast(id?"Product updated.":"Product added to your catalog.");
  }
  catch(err){toast(err.message,true);}
  finally{setBusy(button,false);}
});
$("#product-out-of-stock").addEventListener("change", e => { if (e.target.checked) $("#product-stock").value = "0"; });
$("#product-stock").addEventListener("input", e => { if (Number(e.target.value) > 0) $("#product-out-of-stock").checked = false; else if (e.target.value === "0") $("#product-out-of-stock").checked = true; });
$("#product-search").addEventListener("input",renderProducts);
$("#stock-filter").addEventListener("change",renderProducts);
$("#order-tabs").addEventListener("click", e => {
  const btn = e.target.closest("[data-filter]"); if (!btn) return;
  state.orderFilter = btn.dataset.filter;
  $$("#order-tabs .tab").forEach(el => el.classList.toggle("active",el === btn)); renderOrders();
});
$("#shop-form").addEventListener("submit",async e=>{
  e.preventDefault(); await updateShop({name:$("#shop-name").value.trim(),address:$("#shop-address").value.trim()},e.submitter);
});
$("#shop-open-toggle").addEventListener("change",async e=>{
  const input = e.target; input.disabled = true;
  try { await updateShop({is_open:input.checked}); } catch { input.checked = !input.checked; }
  finally { input.disabled = false; }
});
$("#accept-orders-toggle").addEventListener("change",async e=>{
  const input = e.target; input.disabled = true;
  try { await updateShop({accepts_orders:input.checked}); } catch { input.checked = !input.checked; }
  finally { input.disabled = false; }
});

(async function boot() {
  if (!state.token) return;
  $("#login-screen").classList.add("hidden"); $("#app-shell").classList.remove("hidden");
  try { await refreshAll(); showView("overview"); }
  catch (error) { signOut(false); toast(error.message || "Please sign in again.",true); }
})();
