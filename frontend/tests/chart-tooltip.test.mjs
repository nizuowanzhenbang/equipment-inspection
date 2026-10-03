import assert from 'node:assert/strict'
import test from 'node:test'
import { formatPredictiveTooltip } from '../src/utils/chartTooltip.ts'

test('predictive tooltip escapes device content without removing intended line breaks', () => {
  const result = formatPredictiveTooltip({
    code: 'EQ<&"\'', name: '<img src=x onerror="alert(1)">',
    risk_score: 25, failure_probability: 0.125, defects_90d: 3,
  })
  assert.equal(result, 'EQ&lt;&amp;&quot;&#39; &lt;img src=x onerror=&quot;alert(1)&quot;&gt;<br/>风险分 25<br/>失效概率=12.5%<br/>近 90 天缺陷 3')
  assert.equal(result.includes('<img'), false)
})

test('ordinary device names and zero risk retain their display values', () => {
  assert.equal(formatPredictiveTooltip({
    code: 'EQ-01', name: '给水泵', risk_score: 0, failure_probability: 0, defects_90d: 0,
  }), 'EQ-01 给水泵<br/>风险分 0<br/>失效概率=0.0%<br/>近 90 天缺陷 0')
})
