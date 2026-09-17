// @vitest-environment node
import { describe, expect, it } from 'vitest'
import {
  ensureBackend,
  pythonCandidates,
  stopOwnedBackend,
  type BackendRuntime,
  type ManagedChild,
} from '../electron/backend-process'

function child(): ManagedChild & { killCalls: number } {
  return {
    pid: 42,
    killed: false,
    killCalls: 0,
    kill() {
      this.killed = true
      this.killCalls += 1
      return true
    },
  }
}

describe('pythonCandidates', () => {
  it('uses an explicitly configured production runtime without machine fallbacks', () => {
    expect(
      pythonCandidates('C:\\SCUT', { SCUT_PYTHON_PATH: 'C:\\Python312\\python.exe' }, 'win32'),
    ).toEqual([
      { label: 'SCUT_PYTHON_PATH', command: 'C:\\Python312\\python.exe', prefixArgs: [] },
    ])
  })

  it('retains development fallbacks only when no runtime is configured', () => {
    expect(pythonCandidates('C:\\SCUT', {}, 'win32')).toEqual([
      {
        label: 'project venv',
        command: 'C:\\SCUT\\.local\\venv\\Scripts\\python.exe',
        prefixArgs: [],
      },
      { label: 'Python launcher 3.12', command: 'py', prefixArgs: ['-3.12'] },
      { label: 'PATH python', command: 'python', prefixArgs: [] },
    ])
  })
})

describe('ensureBackend', () => {
  it('attaches to an existing healthy backend without taking ownership', async () => {
    const runtime: BackendRuntime = {
      probeHealth: async () => true,
      launch: () => {
        throw new Error('launch must not be called')
      },
      waitForHealth: async () => true,
    }

    const handle = await ensureBackend({ projectRoot: 'C:\\SCUT', port: 8765, runtime })

    expect(handle.ownsProcess).toBe(false)
    expect(handle.child).toBeUndefined()
    expect(handle.baseUrl).toBe('http://127.0.0.1:8765')
  })

  it('stops a stale candidate and continues until a healthy Python runtime starts', async () => {
    const stale = child()
    const healthy = child()
    const launched: string[] = []
    const runtime: BackendRuntime = {
      probeHealth: async () => false,
      launch(candidate) {
        launched.push(candidate.label)
        return candidate.label === 'project venv' ? stale : healthy
      },
      waitForHealth: async (_baseUrl, _timeout, candidate) => candidate.label === 'Python launcher 3.12',
    }

    const handle = await ensureBackend({ projectRoot: 'C:\\SCUT', port: 8765, runtime })

    expect(launched).toEqual(['project venv', 'Python launcher 3.12'])
    expect(stale.killCalls).toBe(1)
    expect(handle.ownsProcess).toBe(true)
    expect(handle.child).toBe(healthy)
    expect(handle.runtimeLabel).toBe('Python launcher 3.12')
  })
})

describe('stopOwnedBackend', () => {
  it('terminates only a child process owned by this shell', () => {
    const owned = child()
    const external = child()

    stopOwnedBackend({ baseUrl: 'http://127.0.0.1:8765', port: 8765, ownsProcess: true, child: owned })
    stopOwnedBackend({ baseUrl: 'http://127.0.0.1:8765', port: 8765, ownsProcess: false, child: external })

    expect(owned.killCalls).toBe(1)
    expect(external.killCalls).toBe(0)
  })
})
