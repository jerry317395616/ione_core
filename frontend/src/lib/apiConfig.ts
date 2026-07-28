const TOTAL_KEY = 'ione_mobile_token_usage'

interface UsageData {
  total: number
  calls: number
}

export function recordTokenUsage(tokens: number): void {
  try {
    const raw = localStorage.getItem(TOTAL_KEY)
    const data: UsageData = raw ? JSON.parse(raw) : { total: 0, calls: 0 }
    data.total += Math.max(0, Number(tokens) || 0)
    data.calls += 1
    localStorage.setItem(TOTAL_KEY, JSON.stringify(data))
    const today = new Date().toISOString().split('T')[0]
    const key = `ione_mobile_token_session_${today}`
    const previous = Number.parseInt(localStorage.getItem(key) || '0', 10)
    localStorage.setItem(key, String(previous + Math.max(0, Number(tokens) || 0)))
  } catch {
    // Usage counters are optional and must never interrupt business actions.
  }
}

export function getUsageStats(): { session: number; total: number; calls: number } {
  try {
    const raw = localStorage.getItem(TOTAL_KEY)
    const data: UsageData = raw ? JSON.parse(raw) : { total: 0, calls: 0 }
    const today = new Date().toISOString().split('T')[0]
    const session = Number.parseInt(localStorage.getItem(`ione_mobile_token_session_${today}`) || '0', 10)
    return { session, total: data.total, calls: data.calls }
  } catch {
    return { session: 0, total: 0, calls: 0 }
  }
}

export function clearUsageStats(): void {
  try {
    localStorage.removeItem(TOTAL_KEY)
    const today = new Date().toISOString().split('T')[0]
    localStorage.removeItem(`ione_mobile_token_session_${today}`)
  } catch {
    // Local usage statistics are best-effort only.
  }
}
