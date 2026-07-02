const SERVICE_TYPES = ['Wash & Iron', 'Wash Only', 'Iron Only', 'Dry Clean'];
const SERVICE_CATALOG = Object.fromEntries(SERVICE_TYPES.map(service => [service, []]));
const DEFAULT_SERVICE_ITEMS = '';

const state = {
  settings: { currency: 'PKR', tax_rate: '0', service_items: DEFAULT_SERVICE_ITEMS },
  items: [],
  currentPage: 'dashboard',
  paymentModal: { invoiceId: null, balance: 0 },
  confirmModal: { onConfirm: null, busy: false },
  editingInvoiceId: null,
  historyLimit: 300,
  customerLimit: 200,
  expenseLimit: 200,
  customerRows: new Map()
};

const $ = (id) => document.getElementById(id);
const today = () => new Date().toISOString().slice(0, 10);
const MoneyLogic = window.NovaBillMoney;
const rawWhole = MoneyLogic.rawWhole;
const whole = MoneyLogic.whole;

function money(v) {
  const amount = rawWhole(v || 0, 0);
  const currency = state.settings.currency || 'PKR';
  return `${currency} ${amount.toLocaleString()}`;
}

function toast(message, type = 'success') {
  const el = $('toast');
  el.textContent = message;
  el.className = `toast show ${type === 'error' ? 'error' : ''}`;
  setTimeout(() => el.className = 'toast', 3600);
}

let pywebviewReadyPromise = null;

function isPyWebViewReady() {
  return !!(window.pywebview && window.pywebview.api);
}

function waitForPywebviewApi(timeoutMs = 30000) {
  if (isPyWebViewReady()) return Promise.resolve(true);
  if (pywebviewReadyPromise) return pywebviewReadyPromise;

  pywebviewReadyPromise = new Promise((resolve) => {
    const startedAt = Date.now();
    let finished = false;

    function finish(value) {
      if (finished) return;
      finished = true;
      clearInterval(timer);
      resolve(value);
    }

    function check() {
      if (isPyWebViewReady()) finish(true);
      else if (Date.now() - startedAt > timeoutMs) finish(false);
    }

    window.addEventListener('pywebviewready', () => {
      setTimeout(check, 50);
      setTimeout(check, 250);
      setTimeout(check, 750);
      setTimeout(check, 1500);
    });

    const timer = setInterval(check, 120);
    check();
  });

  return pywebviewReadyPromise;
}

async function api(method, ...args) {
  const ready = await waitForPywebviewApi();
  if (!ready || !isPyWebViewReady()) {
    throw new Error('Backend not connected. Close this window and launch with run.bat. Do not open index.html directly.');
  }
  if (typeof window.pywebview.api[method] !== 'function') {
    throw new Error(`Backend method not found: ${method}`);
  }
  const res = await window.pywebview.api[method](...args);
  if (!res || !res.success) {
    console.error(res?.detail || res);
    throw new Error(res?.message || 'API error');
  }
  return res.data;
}

function escapeHtml(str) {
  return String(str || '').replace(/[&<>"']/g, s => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[s]));
}

function hasValidPhone(value) {
  return String(value || '').replace(/\D+/g, '').length >= 7;
}

function logoUrlFromSettings() {
  const raw = String((state.settings && state.settings.logo_path) || '').replace(/\\/g, '/');
  const match = raw.match(/(?:^|\/)assets\/([^\/]+)$/);
  return match ? `/assets/${encodeURIComponent(match[1])}` : '/assets/default_logo.png';
}

function updateBrandLogo() {
  const img = $('brandLogo');
  if (!img) return;
  img.src = logoUrlFromSettings();
  img.onerror = () => {
    img.onerror = null;
    img.src = '/assets/default_logo.png';
  };
}


function emptyServiceCatalog() {
  return Object.fromEntries(Object.keys(SERVICE_CATALOG).map(service => [service, []]));
}

function activeServiceCatalog() {
  const catalog = emptyServiceCatalog();
  const source = String((state.settings && state.settings.service_items) || DEFAULT_SERVICE_ITEMS);
  source.split(/\r?\n/).forEach(line => {
    const clean = line.trim();
    if (!clean) return;
    const parts = clean.split('=');
    const label = (parts.shift() || '').trim();
    const price = whole((parts.join('=') || '0').replace(/[^0-9.-]/g, ''), 0);
    const service = Object.keys(SERVICE_CATALOG).find(name => label.endsWith(` - ${name}`));
    if (!service) return;
    const itemName = label.slice(0, label.length - (` - ${service}`).length).trim();
    if (itemName) catalog[service].push({ name: itemName, price });
  });

  return catalog;
}

function statusBadge(status) {
  const s = (status || 'Unpaid').toLowerCase();
  return `<span class="badge ${s}">${status || 'Unpaid'}</span>`;
}

function setPage(page) {
  state.currentPage = page;
  document.querySelectorAll('.nav').forEach(b => b.classList.toggle('active', b.dataset.page === page));
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  $(`${page}Page`).classList.add('active');
  const titles = {
    dashboard: ['Dashboard', 'Welcome back, Admin! Here’s what’s happening with your laundry business today.'],
    invoice: ['Create New Invoice', 'Add customer details, laundry items, and payment information'],
    history: ['Invoice History', 'Search, open, print and delete old invoices'],
    customers: ['Customers', 'Manage customer records and invoice history'],
    expenses: ['Expenses', 'Track business expenses and profit'],
    settings: ['Settings & Backup', 'Business profile, logo, currency, backup and restore']
  };
  $('pageTitle').textContent = titles[page][0];
  $('pageSubtitle').textContent = titles[page][1];
  if (page === 'dashboard') loadDashboard();
  if (page === 'history') loadInvoices();
  if (page === 'customers') loadCustomers();
  if (page === 'expenses') loadExpenses();
  if (page === 'settings') fillSettings();
  if (page === 'invoice' && !state.editingInvoiceId) refreshInvoiceNo();
}

function serviceTypeOptions(selectedService) {
  const options = ['<option value="">Select Service</option>'];
  Object.keys(SERVICE_CATALOG).forEach(service => {
    options.push(`<option value="${escapeHtml(service)}" ${service === selectedService ? 'selected' : ''}>${escapeHtml(service)}</option>`);
  });
  return options.join('');
}

function itemOptions(serviceType, selectedItem) {
  const options = ['<option value="">Select Item</option>'];
  const catalog = activeServiceCatalog();
  if (serviceType && catalog[serviceType]) {
    catalog[serviceType].forEach(item => {
      const selected = item.name === selectedItem ? 'selected' : '';
      options.push(`<option value="${escapeHtml(item.name)}" ${selected}>${escapeHtml(item.name)} - ${money(item.price)}</option>`);
    });
    options.push(`<option value="__custom__" ${selectedItem === '__custom__' ? 'selected' : ''}>Other / Custom Item</option>`);
  }
  return options.join('');
}

function itemDescription(serviceType, itemName, customName = '') {
  if (!serviceType) return '';
  const cleanName = itemName === '__custom__' ? String(customName || '').trim() : String(itemName || '').trim();
  if (!cleanName) return '';
  return `${cleanName} - ${serviceType}`;
}

function findCatalogItem(serviceType, itemName) {
  return (activeServiceCatalog()[serviceType] || []).find(item => item.name === itemName);
}

function makeDefaultItem() {
  return { service_type: '', item_name: '', custom_name: '', description: '', quantity: 1, unit_price: 0 };
}

function itemTemplate(item, idx) {
  const serviceType = item.service_type || '';
  const itemName = item.item_name || '';
  const isCustom = itemName === '__custom__';
  const qty = whole(item.quantity || 1, 1);
  const price = rawWhole(item.unit_price || 0, 0);
  const itemDisabled = serviceType ? '' : 'disabled';
  return `<div class="item-row" data-index="${idx}">
    <select class="item-service-type">${serviceTypeOptions(serviceType)}</select>
    <div class="item-box">
      <select class="item-name" ${itemDisabled}>${itemOptions(serviceType, itemName)}</select>
      <input type="text" class="item-custom ${isCustom ? '' : 'hidden'}" placeholder="Write custom item" value="${escapeHtml(item.custom_name || '')}">
    </div>
    <div class="stepper qty-stepper" aria-label="Quantity control">
      <button type="button" class="step-btn" data-field=".item-qty" data-step="-1" aria-label="Decrease quantity">−</button>
      <input type="number" class="item-qty" min="1" step="1" inputmode="numeric" value="${qty}">
      <button type="button" class="step-btn" data-field=".item-qty" data-step="1" aria-label="Increase quantity">+</button>
    </div>
    <div class="stepper price-stepper" aria-label="Unit price control">
      <button type="button" class="step-btn" data-field=".item-price" data-step="-1" aria-label="Decrease price">−</button>
      <input type="number" class="item-price" min="0" step="1" inputmode="numeric" value="${price}">
      <button type="button" class="step-btn" data-field=".item-price" data-step="1" aria-label="Increase price">+</button>
    </div>
    <div class="item-total">${money(qty * Math.max(price, 0))}</div>
    <button type="button" class="icon-btn remove-item" aria-label="Remove item">×</button>
  </div>`;
}

function renderItems() {
  $('itemsList').innerHTML = state.items.map(itemTemplate).join('');
  $('itemsList').querySelectorAll('.item-row').forEach(row => {
    const idx = Number(row.dataset.index);
    row.querySelector('.item-service-type').addEventListener('change', () => handleServiceTypeChange(row, idx));
    row.querySelector('.item-name').addEventListener('change', () => handleItemChange(row, idx));
    row.querySelector('.item-custom').addEventListener('input', () => updateItemFromRow(row, idx));
    row.querySelector('.item-qty').addEventListener('input', () => updateItemFromRow(row, idx));
    row.querySelector('.item-price').addEventListener('input', () => updateItemFromRow(row, idx));
    row.querySelector('.item-qty').addEventListener('blur', () => normalizeRowNumbers(row, idx));
    row.querySelector('.item-price').addEventListener('blur', () => normalizeRowNumbers(row, idx));
    row.querySelectorAll('.step-btn').forEach(btn => {
      btn.addEventListener('click', () => stepItemNumber(row, idx, btn.dataset.field, Number(btn.dataset.step || 0)));
    });
    row.querySelector('.remove-item').addEventListener('click', () => {
      if (state.items.length <= 1) return toast('At least one item is required.', 'error');
      state.items.splice(idx, 1);
      renderItems();
      calculateTotals();
    });
  });
  calculateTotals();
}

function handleServiceTypeChange(row, idx) {
  const serviceType = row.querySelector('.item-service-type').value;
  state.items[idx] = { service_type: serviceType, item_name: '', custom_name: '', description: '', quantity: 1, unit_price: 0 };
  renderItems();
}

function handleItemChange(row, idx) {
  const serviceType = row.querySelector('.item-service-type').value;
  const itemName = row.querySelector('.item-name').value;
  const custom = row.querySelector('.item-custom');
  const priceInput = row.querySelector('.item-price');

  state.items[idx].service_type = serviceType;
  state.items[idx].item_name = itemName;
  state.items[idx].custom_name = '';

  if (itemName === '__custom__') {
    custom.classList.remove('hidden');
    custom.focus();
    state.items[idx].unit_price = 0;
    priceInput.value = 0;
  } else {
    custom.classList.add('hidden');
    custom.value = '';
    const catalogItem = findCatalogItem(serviceType, itemName);
    state.items[idx].unit_price = catalogItem ? catalogItem.price : 0;
    priceInput.value = state.items[idx].unit_price;
  }

  updateItemFromRow(row, idx);
}

function updateItemFromRow(row, idx) {
  const serviceType = row.querySelector('.item-service-type').value;
  const itemName = row.querySelector('.item-name').value;
  const customName = row.querySelector('.item-custom').value.trim();
  const qtyRaw = rawWhole(row.querySelector('.item-qty').value, 1);
  const priceRaw = rawWhole(row.querySelector('.item-price').value, 0);
  const qty = Math.max(qtyRaw, 1);
  const priceForTotal = Math.max(priceRaw, 0);
  const description = itemDescription(serviceType, itemName, customName);

  row.querySelector('.item-qty').classList.toggle('input-error', qtyRaw < 1);
  row.querySelector('.item-price').classList.toggle('input-error', priceRaw < 0);

  state.items[idx] = {
    service_type: serviceType,
    item_name: itemName,
    custom_name: itemName === '__custom__' ? customName : '',
    description,
    quantity: qtyRaw,
    unit_price: priceRaw
  };

  row.querySelector('.item-total').textContent = money(qty * priceForTotal);
  calculateTotals();
}

function normalizeRowNumbers(row, idx) {
  updateItemFromRow(row, idx);
  row.querySelector('.item-qty').value = Math.max(rawWhole(state.items[idx].quantity, 1), 1);
  row.querySelector('.item-price').value = rawWhole(state.items[idx].unit_price, 0);
}

function stepItemNumber(row, idx, selector, direction) {
  const input = row.querySelector(selector);
  if (!input || !direction) return;
  const min = Number(input.min || 0);
  const step = Number(input.step || 1);
  const current = Number(input.value || 0);
  const next = Math.max(min, current + direction * step);
  input.value = Math.round(next);
  updateItemFromRow(row, idx);
}

function getInvoiceTotals() {
  return MoneyLogic.invoiceTotals(state.items, $('discount').value || 0, $('taxRate').value || 0, $('paidAmount').value || 0);
}

function calculateTotals() {
  const totals = getInvoiceTotals();
  $('subtotalText').textContent = money(totals.subtotal);
  $('grandTotalText').textContent = money(totals.grand);
  $('balanceText').textContent = money(totals.balance);
  $('discount').classList.toggle('input-error', totals.discount < 0 || totals.discount > totals.subtotal);
  $('paidAmount').classList.toggle('input-error', totals.paid < 0 || totals.paid > totals.grand);
  $('taxRate').classList.toggle('input-error', Number($('taxRate').value || 0) < 0);
  return totals;
}

function validateInvoiceMoney() {
  const totals = calculateTotals();
  if (totals.discount < 0) {
    $('discount').focus();
    toast('Discount cannot be negative.', 'error');
    return false;
  }
  if (totals.discount > totals.subtotal) {
    $('discount').focus();
    toast('Discount cannot be greater than subtotal.', 'error');
    return false;
  }
  if (Number($('taxRate').value || 0) < 0) {
    $('taxRate').focus();
    toast('Tax rate cannot be negative.', 'error');
    return false;
  }
  if (totals.paid < 0) {
    $('paidAmount').focus();
    toast('Paid amount cannot be negative.', 'error');
    return false;
  }
  if (totals.paid > totals.grand) {
    $('paidAmount').focus();
    toast('Paid amount cannot be greater than invoice total.', 'error');
    return false;
  }
  return true;
}

function setInvoiceEditMode(invoiceId = null) {
  state.editingInvoiceId = invoiceId;
  const badge = $('invoiceNoPreview');
  const saveBtn = $('saveInvoiceBtn');
  const cancelBtn = $('cancelEditBtn');
  if (saveBtn) saveBtn.textContent = invoiceId ? 'Update Invoice & Regenerate PDF' : 'Save Invoice & Generate PDF';
  if (cancelBtn) cancelBtn.classList.toggle('hidden', !invoiceId);
  if (badge && invoiceId) badge.classList.add('edit-mode');
  if (badge && !invoiceId) badge.classList.remove('edit-mode');
}

async function loadSettings() {
  try {
    state.settings = await api('get_settings');
    if (!state.settings.service_items) state.settings.service_items = DEFAULT_SERVICE_ITEMS;
    $('connectionStatus').textContent = 'Connected • SQLite ready';
    $('taxRate').value = state.settings.tax_rate || 0;
    updateBrandLogo();
    fillSettings();
  } catch (e) {
    $('connectionStatus').textContent = 'API not connected';
    toast(e.message, 'error');
  }
}

function fillSettings() {
  if (!$('shopName')) return;
  $('shopName').value = state.settings.shop_name || '';
  $('shopTagline').value = state.settings.shop_tagline || '';
  $('shopAddress').value = state.settings.shop_address || '';
  $('shopPhone').value = state.settings.shop_phone || '';
  $('shopEmail').value = state.settings.shop_email || '';
  $('currency').value = state.settings.currency || 'PKR';
  $('invoicePrefix').value = state.settings.invoice_prefix || 'INV';
  $('defaultTaxRate').value = state.settings.tax_rate || 0;
  $('serviceItems').value = state.settings.service_items || DEFAULT_SERVICE_ITEMS;
  $('footerNote').value = state.settings.footer_note || '';
  $('termsNote').value = state.settings.terms_note || '';
}

async function refreshInvoiceNo() {
  try {
    const no = await api('get_next_invoice_no', $('invoiceDate').value || today());
    $('invoiceNoPreview').textContent = no;
  } catch (e) { $('invoiceNoPreview').textContent = 'INV'; }
}

function setInvoiceSaving(isSaving) {
  const btn = $('saveInvoiceBtn');
  if (!btn) return;
  if (isSaving) {
    btn.dataset.originalText = btn.textContent || 'Save Invoice & Generate PDF';
    btn.textContent = state.editingInvoiceId ? 'Updating...' : 'Saving...';
    btn.disabled = true;
    btn.classList.add('is-loading');
  } else {
    btn.disabled = false;
    btn.classList.remove('is-loading');
    btn.textContent = state.editingInvoiceId ? 'Update Invoice & Regenerate PDF' : 'Save Invoice & Generate PDF';
    delete btn.dataset.originalText;
  }
}

async function saveInvoice(e) {
  e.preventDefault();
  const customerPhone = $('customerPhone').value.trim();
  if (!$('customerName').value.trim()) {
    $('customerName').focus();
    toast('Customer name is required.', 'error');
    return;
  }
  if (!customerPhone) {
    $('customerPhone').focus();
    toast('Customer phone number is required.', 'error');
    return;
  }
  if (!hasValidPhone(customerPhone)) {
    $('customerPhone').focus();
    toast('Please enter a valid customer phone number.', 'error');
    return;
  }
  const enteredItems = state.items.filter(item => String(item.description || '').trim());
  if (!enteredItems.length) {
    toast('At least one invoice item is required.', 'error');
    return;
  }
  const badQty = enteredItems.find(item => rawWhole(item.quantity || 0, 0) < 1);
  if (badQty) { toast('Quantity must be at least 1.', 'error'); return; }
  const badPrice = enteredItems.find(item => rawWhole(item.unit_price || 0, 0) < 0);
  if (badPrice) { toast('Unit price cannot be negative.', 'error'); return; }
  const validItems = enteredItems;
  if (!validateInvoiceMoney()) return;

  const payload = {
    invoice_date: $('invoiceDate').value,
    due_date: $('dueDate').value,
    customer_name: $('customerName').value,
    customer_phone: customerPhone,
    customer_email: $('customerEmail').value,
    customer_address: $('customerAddress').value,
    payment_method: $('paymentMethod').value,
    notes: $('invoiceNotes').value,
    discount: whole($('discount').value || 0, 0),
    tax_rate: Number($('taxRate').value || 0),
    paid_amount: whole($('paidAmount').value || 0, 0),
    open_after_save: $('openAfterSave').checked,
    items: validItems.map(item => ({
      description: item.description,
      quantity: whole(item.quantity || 1, 1),
      unit_price: rawWhole(item.unit_price || 0, 0)
    }))
  };
  try {
    setInvoiceSaving(true);
    const method = state.editingInvoiceId ? 'update_invoice' : 'create_invoice';
    const args = state.editingInvoiceId ? [state.editingInvoiceId, payload] : [payload];
    const data = await api(method, ...args);
    toast(state.editingInvoiceId ? `Invoice ${data.invoice.invoice_no} updated.` : `Invoice ${data.invoice.invoice_no} saved.`);
    resetInvoiceForm();
    await loadDashboard();
    if (state.currentPage === 'history') await loadInvoices();
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    setInvoiceSaving(false);
  }
}

function resetInvoiceForm() {
  setInvoiceEditMode(null);
  $('invoiceForm').reset();
  $('invoiceDate').value = today();
  $('expenseDate').value = today();
  $('taxRate').value = state.settings.tax_rate || 0;
  $('discount').value = 0;
  $('paidAmount').value = 0;
  $('openAfterSave').checked = true;
  state.items = [makeDefaultItem()];
  renderItems();
  refreshInvoiceNo();
}

async function loadDashboard() {
  try {
    const d = await api('get_dashboard');
    $('todaySales').textContent = money(d.today_sales.v);
    $('todayInvoices').textContent = `${d.today_sales.c} invoices`;
    $('monthSales').textContent = money(d.month_sales.v);
    $('monthInvoices').textContent = `${d.month_sales.c} invoices`;
    $('monthExpenses').textContent = money(d.month_expenses.v);
    $('expenseCount').textContent = `${d.month_expenses.c} entries`;
    $('monthlyProfit').textContent = money(d.monthly_profit);
    $('outstanding').textContent = `Outstanding: ${money(d.outstanding.v)}`;
    $('recentInvoicesBody').innerHTML = (d.recent_invoices || []).map(inv => `<tr><td>${inv.invoice_no}</td><td>${escapeHtml(inv.customer_name)}</td><td>${inv.invoice_date}</td><td>${money(inv.total)}</td><td>${statusBadge(inv.payment_status)}</td></tr>`).join('') || emptyRow(5);
    $('topCustomersBody').innerHTML = (d.top_customers || []).map(c => `<tr><td>${escapeHtml(c.customer_name)}</td><td>${c.invoice_count}</td><td>${money(c.total_spent)}</td></tr>`).join('') || emptyRow(3);
    loadMonthlyReport();
  } catch (e) { toast(e.message, 'error'); }
}

async function loadMonthlyReport() {
  try {
    const rows = await api('get_monthly_report', new Date().getFullYear());
    $('monthlyReportBody').innerHTML = rows.map(r => `<tr><td>${r.month}</td><td>${money(r.sales)}</td><td>${r.invoices}</td><td>${money(r.expenses)}</td><td><strong>${money(r.profit)}</strong></td></tr>`).join('') || emptyRow(5);
  } catch (e) { toast(e.message, 'error'); }
}

async function loadInvoices() {
  try {
    const rows = await api('list_invoices', {
      search: $('historySearch').value,
      start_date: $('historyStart').value,
      end_date: $('historyEnd').value,
      status: $('historyStatus').value,
      limit: state.historyLimit
    });
    $('invoiceHistoryBody').innerHTML = rows.map(inv => {
      const pdfMissing = !inv.pdf_path;
      return `<tr>
        <td><strong>${escapeHtml(inv.invoice_no)}</strong>${pdfMissing ? '<br><small class="warn-text">PDF missing</small>' : ''}</td>
        <td>${escapeHtml(inv.invoice_date)}</td>
        <td>${escapeHtml(inv.customer_name)}<br><small>${escapeHtml(inv.customer_phone || '')}</small></td>
        <td>${money(inv.total)}</td><td>${money(inv.paid_amount)}</td><td>${money(inv.balance)}</td><td>${statusBadge(inv.payment_status)}</td>
        <td><div class="row-actions">
          <button class="btn small secondary" data-action="edit-invoice" data-id="${inv.id}">Edit</button>
          ${Number(inv.balance || 0) > 0 ? `<button class="btn small secondary" data-action="update-payment" data-id="${inv.id}" data-balance="${Number(inv.balance || 0)}">Update Payment</button>` : ''}
          <button class="btn small secondary" data-action="open-invoice" data-id="${inv.id}">${pdfMissing ? 'Regenerate/Open' : 'Open'}</button>
          <button class="btn small secondary" data-action="print-invoice" data-id="${inv.id}">Print</button>
          ${pdfMissing ? `<button class="btn small secondary" data-action="regenerate-invoice" data-id="${inv.id}">Regenerate PDF</button>` : ''}
          <button class="btn small danger" data-action="delete-invoice" data-id="${inv.id}">Delete</button>
        </div></td>
      </tr>`;
    }).join('') || emptyRow(8);
    const loadMore = $('loadMoreInvoicesBtn');
    if (loadMore) loadMore.classList.toggle('hidden', rows.length < state.historyLimit);
  } catch (e) { toast(e.message, 'error'); }
}

async function editInvoice(id) {
  try {
    const data = await api('get_invoice', id);
    if (!data || !data.invoice) return toast('Invoice not found.', 'error');
    const inv = data.invoice;
    state.editingInvoiceId = id;
    setPage('invoice');
    setInvoiceEditMode(id);
    $('invoiceDate').value = inv.invoice_date || today();
    $('dueDate').value = inv.due_date || '';
    $('customerName').value = inv.customer_name || '';
    $('customerPhone').value = inv.customer_phone || '';
    $('customerEmail').value = inv.customer_email || '';
    $('customerAddress').value = inv.customer_address || '';
    $('paymentMethod').value = inv.payment_method || 'Cash';
    $('invoiceNotes').value = inv.notes || '';
    $('discount').value = whole(inv.discount || 0, 0);
    $('taxRate').value = inv.tax_rate || 0;
    $('paidAmount').value = whole(inv.paid_amount || 0, 0);
    $('invoiceNoPreview').textContent = inv.invoice_no || 'Editing';
    state.items = (data.items || []).map(item => itemFromDescription(item.description, item.quantity, item.unit_price));
    if (!state.items.length) state.items = [makeDefaultItem()];
    renderItems();
    toast(`Editing invoice ${inv.invoice_no}.`);
  } catch (e) { toast(e.message, 'error'); }
}

function itemFromDescription(description, quantity, unitPrice) {
  const text = String(description || '').trim();
  const catalog = activeServiceCatalog();
  const service = Object.keys(catalog).find(name => text.endsWith(` - ${name}`));
  const base = service ? text.slice(0, text.length - (` - ${service}`).length).trim() : text;
  if (service) {
    const found = (catalog[service] || []).find(item => item.name === base);
    if (found) return { service_type: service, item_name: found.name, custom_name: '', description: text, quantity, unit_price: unitPrice };
    return { service_type: service, item_name: '__custom__', custom_name: base, description: text, quantity, unit_price: unitPrice };
  }
  return { service_type: '', item_name: '__custom__', custom_name: text, description: text, quantity, unit_price: unitPrice };
}

function updatePayment(id, balance) {
  const remaining = whole(balance || 0, 0);
  if (remaining <= 0) {
    toast('This invoice is already fully paid.');
    return;
  }
  state.paymentModal = { invoiceId: id, balance: remaining };
  $('paymentModalText').textContent = `Remaining balance: ${money(remaining)}. Enter received amount now.`;
  $('paymentModalAmount').value = remaining;
  $('paymentModal').classList.remove('hidden');
  $('paymentModal').setAttribute('aria-hidden', 'false');
  setTimeout(() => $('paymentModalAmount').focus(), 50);
}

function closePaymentModal() {
  state.paymentModal = { invoiceId: null, balance: 0 };
  $('paymentModal').classList.add('hidden');
  $('paymentModal').setAttribute('aria-hidden', 'true');
  $('paymentModalAmount').value = '';
}

async function confirmPaymentUpdate() {
  const id = state.paymentModal.invoiceId;
  const remaining = whole(state.paymentModal.balance || 0, 0);
  if (!id || remaining <= 0) return closePaymentModal();

  const amount = whole(String($('paymentModalAmount').value || '').replace(/,/g, ''), 0);
  if (amount <= 0) {
    toast('Payment amount must be greater than 0.', 'error');
    $('paymentModalAmount').focus();
    return;
  }
  if (amount > remaining) {
    toast(`Payment cannot be greater than remaining balance ${money(remaining)}.`, 'error');
    $('paymentModalAmount').value = remaining;
    $('paymentModalAmount').focus();
    return;
  }
  try {
    const data = await api('update_invoice_payment', id, amount);
    toast(`Payment updated. New balance: ${money(data.invoice.balance)}`);
    closePaymentModal();
    await loadInvoices();
    await loadDashboard();
  } catch (e) { toast(e.message, 'error'); }
}

function openConfirmModal({ title, message, confirmText, onConfirm }) {
  state.confirmModal = { onConfirm, busy: false };
  $('confirmModalTitle').textContent = title || 'Confirm Action';
  $('confirmModalText').textContent = message || 'Are you sure?';
  $('confirmActionBtn').textContent = confirmText || 'Confirm';
  $('confirmActionBtn').disabled = false;
  $('confirmModal').classList.remove('hidden');
  $('confirmModal').setAttribute('aria-hidden', 'false');
  setTimeout(() => $('confirmActionBtn').focus(), 50);
}

function closeConfirmModal() {
  if (state.confirmModal.busy) return;
  state.confirmModal = { onConfirm: null, busy: false };
  $('confirmModal').classList.add('hidden');
  $('confirmModal').setAttribute('aria-hidden', 'true');
}

async function confirmModalAction() {
  const action = state.confirmModal.onConfirm;
  if (!action || state.confirmModal.busy) return;
  state.confirmModal.busy = true;
  $('confirmActionBtn').disabled = true;
  try {
    await action();
    state.confirmModal.busy = false;
    closeConfirmModal();
  } catch (e) {
    state.confirmModal.busy = false;
    $('confirmActionBtn').disabled = false;
    toast(e.message, 'error');
  }
}

async function openInvoice(id) { try { const r = await api('open_invoice_pdf', id); toast(r.message, r.success ? 'success' : 'error'); await loadInvoices(); } catch (e) { toast(e.message, 'error'); } }
async function printInvoice(id) { try { const r = await api('print_invoice_pdf', id); toast(r.message, r.success ? 'success' : 'error'); await loadInvoices(); } catch (e) { toast(e.message, 'error'); } }
async function regenerateInvoice(id) { try { const r = await api('regenerate_invoice_pdf', id); toast(`PDF regenerated for ${r.invoice.invoice_no}.`); await loadInvoices(); } catch (e) { toast(e.message, 'error'); } }
function deleteInvoice(id) {
  openConfirmModal({
    title: 'Delete Invoice',
    message: 'This will permanently delete this invoice and its PDF. This action cannot be undone.',
    confirmText: 'Delete Invoice',
    onConfirm: async () => {
      await api('delete_invoice', id);
      toast('Invoice deleted.');
      await loadInvoices();
      await loadDashboard();
    }
  });
}

async function loadCustomers() {
  try {
    const rows = await api('list_customers', { search: $('customerSearch').value || '', limit: state.customerLimit });
    state.customerRows = new Map(rows.map(c => [String(c.id), c]));
    $('customersBody').innerHTML = rows.map(c => `<tr>
      <td><strong>${escapeHtml(c.name)}</strong></td><td>${escapeHtml(c.phone || '')}</td><td>${escapeHtml(c.email || '')}</td><td>${c.invoice_count || 0}</td><td>${money(c.lifetime_value || 0)}</td><td>${c.last_invoice_date || '-'}</td>
      <td><div class="row-actions"><button class="btn small secondary" data-action="use-customer" data-id="${c.id}">Use</button><button class="btn small danger" data-action="delete-customer" data-id="${c.id}">Delete</button></div></td>
    </tr>`).join('') || emptyRow(7);
    const loadMore = $('loadMoreCustomersBtn');
    if (loadMore) loadMore.classList.toggle('hidden', rows.length < state.customerLimit);
  } catch (e) { toast(e.message, 'error'); }
}

function useCustomer(c) {
  if (typeof c !== 'object') c = state.customerRows.get(String(c));
  if (!c) return toast('Customer not found.', 'error');
  setPage('invoice');
  $('customerName').value = c.name || '';
  $('customerPhone').value = c.phone || '';
  $('customerEmail').value = c.email || '';
  $('customerAddress').value = c.address || '';
  toast('Customer loaded into new invoice.');
}
function deleteCustomer(id) {
  openConfirmModal({
    title: 'Delete Customer',
    message: 'This customer record will be deleted. Saved invoices will remain available.',
    confirmText: 'Delete Customer',
    onConfirm: async () => {
      await api('delete_customer', id);
      toast('Customer deleted.');
      await loadCustomers();
      await loadDashboard();
    }
  });
}

async function saveExpense(e) {
  e.preventDefault();
  const amount = Number($('expenseAmount').value || 0);
  if (amount < 0) { $('expenseAmount').focus(); toast('Expense amount cannot be negative.', 'error'); return; }
  try {
    await api('add_expense', {
      expense_date: $('expenseDate').value,
      category: $('expenseCategory').value,
      description: $('expenseDescription').value,
      amount,
      payment_method: $('expensePayment').value,
      notes: $('expenseNotes').value
    });
    $('expenseForm').reset(); $('expenseDate').value = today();
    toast('Expense saved.'); loadExpenses(); loadDashboard();
  } catch (e) { toast(e.message, 'error'); }
}

async function loadExpenses() {
  try {
    const rows = await api('list_expenses', { search: $('expenseSearch').value || '', limit: state.expenseLimit });
    $('expensesBody').innerHTML = rows.map(x => `<tr><td>${x.expense_date}</td><td>${escapeHtml(x.category)}</td><td>${escapeHtml(x.description || '')}</td><td>${money(x.amount)}</td><td><button class="btn small danger" data-action="delete-expense" data-id="${x.id}">Delete</button></td></tr>`).join('') || emptyRow(5);
    const loadMore = $('loadMoreExpensesBtn');
    if (loadMore) loadMore.classList.toggle('hidden', rows.length < state.expenseLimit);
  } catch (e) { toast(e.message, 'error'); }
}

function deleteExpense(id) {
  openConfirmModal({
    title: 'Delete Expense',
    message: 'This expense record will be permanently deleted.',
    confirmText: 'Delete Expense',
    onConfirm: async () => {
      await api('delete_expense', id);
      toast('Expense deleted.');
      await loadExpenses();
      await loadDashboard();
    }
  });
}

async function saveSettings(e) {
  e.preventDefault();
  try {
    state.settings = await api('save_settings', {
      shop_name: $('shopName').value,
      shop_tagline: $('shopTagline').value,
      shop_address: $('shopAddress').value,
      shop_phone: $('shopPhone').value,
      shop_email: $('shopEmail').value,
      currency: $('currency').value || 'PKR',
      invoice_prefix: $('invoicePrefix').value || 'INV',
      tax_rate: $('defaultTaxRate').value || '0',
      service_items: $('serviceItems').value || DEFAULT_SERVICE_ITEMS,
      footer_note: $('footerNote').value,
      terms_note: $('termsNote').value
    });
    $('taxRate').value = state.settings.tax_rate || 0;
    toast('Settings saved.');
    renderItems();
    refreshInvoiceNo();
  } catch (e) { toast(e.message, 'error'); }
}

async function selectLogo() { try { const r = await api('select_logo_file'); if (r.selected) { state.settings = r.settings; updateBrandLogo(); fillSettings(); toast('Logo updated.'); } else toast('No logo selected.', 'error'); } catch (e) { toast(e.message, 'error'); } }
async function createBackup() { try { const path = await api('create_backup'); toast(`Backup created: ${path}`); } catch (e) { toast(e.message, 'error'); } }
async function restoreBackup() {
  openConfirmModal({
    title: 'Restore Backup',
    message: 'This will validate the selected ZIP first. Your current data will not be replaced unless the backup passes safety checks.',
    confirmText: 'Restore Backup',
    onConfirm: async () => {
      const result = await api('restore_backup', '');
      toast(`Backup restored. Safety backup created: ${result.safety_backup}`);
      await loadSettings();
      await loadDashboard();
      if (state.currentPage === 'history') await loadInvoices();
    }
  });
}

function emptyRow(cols) { return `<tr><td colspan="${cols}" class="muted"><div class="empty-state"><strong>No records yet</strong><span>Your activity will appear here automatically.</span></div></td></tr>`; }

function bindEvents() {
  document.querySelectorAll('.nav').forEach(btn => btn.addEventListener('click', () => setPage(btn.dataset.page)));
  document.querySelectorAll('[data-page-jump]').forEach(btn => btn.addEventListener('click', () => setPage(btn.dataset.pageJump)));
  $('refreshBtn').addEventListener('click', () => setPage(state.currentPage));
  $('addItemBtn').addEventListener('click', () => { state.items.push(makeDefaultItem()); renderItems(); });
  $('invoiceForm').addEventListener('submit', saveInvoice);
  $('resetInvoiceBtn').addEventListener('click', resetInvoiceForm);
  $('cancelEditBtn')?.addEventListener('click', resetInvoiceForm);
  ['discount', 'paidAmount'].forEach(id => $(id).addEventListener('blur', () => { $(id).value = rawWhole($(id).value, 0); calculateTotals(); }));
  ['discount', 'taxRate', 'paidAmount'].forEach(id => $(id).addEventListener('input', calculateTotals));
  $('invoiceDate').addEventListener('change', refreshInvoiceNo);
  $('reloadInvoicesBtn').addEventListener('click', () => { state.historyLimit = 300; loadInvoices(); });
  $('searchInvoicesBtn').addEventListener('click', () => { state.historyLimit = 300; loadInvoices(); });
  $('loadMoreInvoicesBtn')?.addEventListener('click', () => { state.historyLimit += 300; loadInvoices(); });
  $('reloadCustomersBtn').addEventListener('click', () => { state.customerLimit = 200; loadCustomers(); });
  $('searchCustomersBtn').addEventListener('click', () => { state.customerLimit = 200; loadCustomers(); });
  $('loadMoreCustomersBtn')?.addEventListener('click', () => { state.customerLimit += 200; loadCustomers(); });
  $('expenseForm').addEventListener('submit', saveExpense);
  $('reloadExpensesBtn').addEventListener('click', () => { state.expenseLimit = 200; loadExpenses(); });
  $('searchExpensesBtn').addEventListener('click', () => { state.expenseLimit = 200; loadExpenses(); });
  $('loadMoreExpensesBtn')?.addEventListener('click', () => { state.expenseLimit += 200; loadExpenses(); });
  $('settingsForm').addEventListener('submit', saveSettings);
  $('selectLogoBtn').addEventListener('click', selectLogo);
  $('backupBtn').addEventListener('click', createBackup);
  $('restoreBtn').addEventListener('click', restoreBackup);
  $('loadReportBtn').addEventListener('click', loadMonthlyReport);
  $('cancelPaymentBtn').addEventListener('click', closePaymentModal);
  $('confirmPaymentBtn').addEventListener('click', confirmPaymentUpdate);
  $('paymentModal').addEventListener('click', (e) => { if (e.target.id === 'paymentModal') closePaymentModal(); });
  $('paymentModalAmount').addEventListener('keydown', (e) => { if (e.key === 'Enter') confirmPaymentUpdate(); if (e.key === 'Escape') closePaymentModal(); });
  $('cancelConfirmBtn').addEventListener('click', closeConfirmModal);
  $('confirmActionBtn').addEventListener('click', confirmModalAction);
  $('confirmModal').addEventListener('click', (e) => { if (e.target.id === 'confirmModal') closeConfirmModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('confirmModal').classList.contains('hidden')) closeConfirmModal(); });

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const id = Number(btn.dataset.id || 0);
    const action = btn.dataset.action;
    if (action === 'edit-invoice') editInvoice(id);
    if (action === 'update-payment') updatePayment(id, Number(btn.dataset.balance || 0));
    if (action === 'open-invoice') openInvoice(id);
    if (action === 'print-invoice') printInvoice(id);
    if (action === 'regenerate-invoice') regenerateInvoice(id);
    if (action === 'delete-invoice') deleteInvoice(id);
    if (action === 'use-customer') useCustomer(id);
    if (action === 'delete-customer') deleteCustomer(id);
    if (action === 'delete-expense') deleteExpense(id);
  });

}


async function bootApp() {
  $('invoiceDate').value = today();
  $('expenseDate').value = today();
  bindEvents();

  $('connectionStatus').textContent = 'Connecting to Python backend...';
  const ready = await waitForPywebviewApi();
  if (!ready) {
    $('connectionStatus').textContent = 'Backend not connected';
    toast('Backend not connected. Close this window and run run.bat again. Do not open index.html directly.', 'error');
    state.items = [makeDefaultItem()];
    renderItems();
    return;
  }

  $('connectionStatus').textContent = 'Connected • SQLite ready';
  await loadSettings();
  state.items = [makeDefaultItem()];
  renderItems();
  await refreshInvoiceNo();
  await loadDashboard();
}

document.addEventListener('DOMContentLoaded', bootApp);
