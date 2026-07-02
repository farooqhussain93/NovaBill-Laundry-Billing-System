(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.NovaBillMoney = factory();
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function rawWhole(value, fallback = 0) {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return Math.round(n);
  }

  function whole(value, fallback = 0) {
    const n = rawWhole(value, fallback);
    return Math.max(n, fallback === 1 ? 1 : 0);
  }

  function invoiceTotals(items, discountInput, taxRateInput, paidInput) {
    const subtotal = (items || []).reduce((sum, item) => {
      const qty = Math.max(rawWhole(item.quantity || 0, 0), 0);
      const price = Math.max(rawWhole(item.unit_price || 0, 0), 0);
      return sum + qty * price;
    }, 0);
    const discount = rawWhole(discountInput || 0, 0);
    const taxRate = Math.max(Number(taxRateInput || 0), 0);
    const taxable = Math.max(subtotal - Math.max(discount, 0), 0);
    const tax = Math.max(rawWhole(taxable * taxRate / 100, 0), 0);
    const grand = rawWhole(taxable + tax, 0);
    const paid = rawWhole(paidInput || 0, 0);
    const balance = Math.max(rawWhole(grand - Math.max(paid, 0), 0), 0);
    return { subtotal, discount, taxRate, tax, grand, paid, balance };
  }

  function validateTotals(totals) {
    if (totals.discount < 0) return 'discount-negative';
    if (totals.discount > totals.subtotal) return 'discount-too-high';
    if (totals.paid < 0) return 'paid-negative';
    if (totals.paid > totals.grand) return 'paid-too-high';
    return 'ok';
  }

  return { rawWhole, whole, invoiceTotals, validateTotals };
}));
