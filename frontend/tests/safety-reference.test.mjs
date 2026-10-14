import test from 'node:test'
import assert from 'node:assert/strict'
import { validSafetyReference } from '../src/utils/safetyReference.ts'

test('invalid historical references remain unconfirmed and eligible for retry', () => {
  for (const value of [null, undefined, '', ' ', '\t', '\n', 'bad\tref', 'bad\u0000ref', 'x'.repeat(51), '\u0085', '\u3000']) {
    assert.equal(validSafetyReference(value), false, JSON.stringify(value))
  }
})

test('valid historical references retain confirmation, including Unicode code points', () => {
  for (const value of ['YH-20261014-0001', ' YH-OLD ', '隐患引用', '🔥'.repeat(50), '\ufeff']) {
    assert.equal(validSafetyReference(value), true, JSON.stringify(value))
  }
  assert.equal(validSafetyReference('🔥'.repeat(51)), false)
})
