// Objective gate for the sum-bug case. stdlib node:test — no new dependency.
const { test } = require('node:test');
const assert = require('node:assert');
const { sum } = require('./solution');

test('adds two positives', () => assert.strictEqual(sum(2, 2), 4));
test('adds negatives', () => assert.strictEqual(sum(-3, -4), -7));
test('adds with zero', () => assert.strictEqual(sum(5, 0), 5));
