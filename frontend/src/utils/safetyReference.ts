/** Match the sender's Python str.strip, code-point length and control rules. */
export function validSafetyReference(value: unknown): value is string {
  return typeof value === 'string'
    && /[^\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/u.test(value)
    && [...value].length <= 50
    && !/[\u0000-\u001f]/u.test(value)
}
