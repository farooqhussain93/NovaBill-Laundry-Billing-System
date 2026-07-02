const assert = require('assert');
const MoneyLogic = require('../laundry_invoice_app/web/money_logic.js');

const { rawWhole, whole, invoiceTotals, validateTotals } = MoneyLogic;

const normal = invoiceTotals([{ quantity: 2, unit_price: 100 }], 0, 5, 50);
assert.deepStrictEqual(normal, { subtotal: 200, discount: 0, taxRate: 5, tax: 10, grand: 210, paid: 50, balance: 160 });
assert.strictEqual(validateTotals(normal), 'ok');

const fractionalTax = invoiceTotals([{ quantity: 1, unit_price: 100 }], 0, 8.25, 108);
assert.strictEqual(fractionalTax.tax, 8);
assert.strictEqual(fractionalTax.grand, 108);
assert.strictEqual(fractionalTax.balance, 0);
assert.strictEqual(validateTotals(fractionalTax), 'ok');

assert.strictEqual(validateTotals(invoiceTotals([{ quantity: 1, unit_price: 100 }], 999, 0, 0)), 'discount-too-high');
assert.strictEqual(validateTotals(invoiceTotals([{ quantity: 1, unit_price: 100 }], 0, 0, 999)), 'paid-too-high');
assert.strictEqual(validateTotals(invoiceTotals([{ quantity: 1, unit_price: 100 }], -1, 0, 0)), 'discount-negative');
assert.strictEqual(validateTotals(invoiceTotals([{ quantity: 1, unit_price: 100 }], 0, 0, -1)), 'paid-negative');
assert.strictEqual(rawWhole(-100, 0), -100);
assert.strictEqual(whole(-100, 0), 0);

console.log('Frontend money tests passed against shared money_logic.js.');
