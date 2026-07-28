type FrappeEnvelope<T> = {
  message?: T
  exception?: string
  exc_type?: string
  _server_messages?: string
}

let csrfToken = ''

function decodeServerMessage(raw?: string): string {
  if (!raw) return ''
  try {
    const messages = JSON.parse(raw) as string[]
    const first = messages[0]
    if (!first) return ''
    const parsed = JSON.parse(first) as { message?: string }
    return parsed.message || first
  } catch {
    return ''
  }
}

function serializeValue(value: unknown): string {
  if (value === undefined || value === null) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  if (typeof value === 'boolean') return value ? '1' : '0'
  return String(value)
}

export function setCsrfToken(token?: string | null) {
  csrfToken = token || ''
}

export function getCsrfToken() {
  return csrfToken
}

export async function frappeCall<T>(
  method: string,
  args: Record<string, unknown> = {},
  httpMethod: 'GET' | 'POST' = 'GET',
): Promise<T> {
  const endpoint = `/api/method/${method}`
  const query = new URLSearchParams()
  let url = endpoint
  let body: string | undefined

  if (httpMethod === 'GET') {
    Object.entries(args).forEach(([key, value]) => {
      if (value !== undefined) query.set(key, serializeValue(value))
    })
    const queryString = query.toString()
    if (queryString) url = `${endpoint}?${queryString}`
  } else {
    body = JSON.stringify(args)
  }

  const response = await fetch(url, {
    method: httpMethod,
    credentials: 'include',
    cache: 'no-store',
    headers: {
      Accept: 'application/json',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(csrfToken ? { 'X-Frappe-CSRF-Token': csrfToken } : {}),
    },
    body,
  })
  const payload = await response.json().catch(() => ({})) as FrappeEnvelope<T>
  if (!response.ok) {
    throw new Error(
      decodeServerMessage(payload._server_messages)
      || (typeof payload.message === 'string' ? payload.message : '')
      || payload.exception
      || `Frappe 请求失败（HTTP ${response.status}）`,
    )
  }
  return payload.message as T
}

export interface FrappeSessionUser {
  username: string
  fullName: string
}

export async function loginToFrappe(username: string, password: string): Promise<FrappeSessionUser> {
  const form = new URLSearchParams({ usr: username, pwd: password })
  const response = await fetch('/api/method/login', {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    },
    body: form,
  })
  const payload = await response.json().catch(() => ({})) as FrappeEnvelope<string> & {
    full_name?: string
    home_page?: string
  }
  if (!response.ok) {
    throw new Error(
      decodeServerMessage(payload._server_messages)
      || payload.exception
      || '账号或密码不正确',
    )
  }
  return {
    username,
    fullName: payload.full_name || username,
  }
}

export async function logoutFromFrappe() {
  try {
    await frappeCall('logout', {}, 'POST')
  } finally {
    setCsrfToken('')
  }
}
