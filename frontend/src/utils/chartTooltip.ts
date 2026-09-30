type TooltipDevice = {
  code: string
  name: string
  risk_score: number
  failure_probability: number
  defects_90d: number
}

export function formatPredictiveTooltip(device: TooltipDevice): string {
  // ECharts HTML tooltip values must remain text even when a device name contains markup.
  const escape = (value: string | number) => String(value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;')
  return `${escape(device.code)} ${escape(device.name)}<br/>风险分 ${escape(device.risk_score)}<br/>失效概率=${escape((device.failure_probability * 100).toFixed(1))}%<br/>近 90 天缺陷 ${escape(device.defects_90d)}`
}
