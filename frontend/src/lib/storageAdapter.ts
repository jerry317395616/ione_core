/**
 * 存储适配器：统一封装 localStorage
 */

interface StorageAdapter {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
  clear(): void
  isAvailable(): boolean
}

// ===== 内存 polyfill（降级）=====
function createMemoryStorageAdapter(): StorageAdapter {
  const store = new Map<string, string>()
  return {
    getItem(key: string): string | null {
      return store.get(key) ?? null
    },
    setItem(key: string, value: string): void {
      store.set(key, value)
    },
    removeItem(key: string): void {
      store.delete(key)
    },
    clear(): void {
      store.clear()
    },
    isAvailable(): boolean {
      return true
    },
  }
}

// ===== 创建全局 storage adapter =====
function createDefaultAdapter(): StorageAdapter {
  // 1. 尝试 localStorage（H5 环境）
  try {
    const testKey = '__storage_test__'
    localStorage.setItem(testKey, '1')
    localStorage.getItem(testKey)
    localStorage.removeItem(testKey)
    return {
      getItem(key: string): string | null {
        try { return localStorage.getItem(key) } catch { return null }
      },
      setItem(key: string, value: string): void {
        try { localStorage.setItem(key, value) } catch { /* Storage full */ }
      },
      removeItem(key: string): void {
        try { localStorage.removeItem(key) } catch { /* ignore */ }
      },
      clear(): void {
        try { localStorage.clear() } catch { /* ignore */ }
      },
      isAvailable(): boolean { return true },
    }
  } catch {
    // localStorage not available
  }

  // 2. 降级到内存存储
  return createMemoryStorageAdapter()
}

export const storage = createDefaultAdapter()

/**
 * 安全获取 JSON 数据
 */
export function getItemJSON<T>(key: string): T | null {
  const raw = storage.getItem(key)
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

/**
 * 安全设置 JSON 数据
 */
export function setItemJSON(key: string, value: unknown): void {
  try {
    storage.setItem(key, JSON.stringify(value))
  } catch {
    // Storage full
  }
}

/**
 * 检测语音识别是否可用
 */
export function isVoiceSupported(): boolean {
  try {
    const speechGlobal = globalThis as typeof globalThis & {
      SpeechRecognition?: unknown
      webkitSpeechRecognition?: unknown
    }
    const SR = speechGlobal.SpeechRecognition || speechGlobal.webkitSpeechRecognition
    return !!SR
  } catch {
    return false
  }
}
