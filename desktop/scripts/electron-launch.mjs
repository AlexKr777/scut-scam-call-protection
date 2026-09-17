import { spawnSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import electronPath from 'electron'

const scriptDirectory = dirname(fileURLToPath(import.meta.url))
const desktopRoot = resolve(scriptDirectory, '..')
const environment = { ...process.env }
delete environment.ELECTRON_RUN_AS_NODE

const result = spawnSync(electronPath, [desktopRoot, ...process.argv.slice(2)], {
  env: environment,
  stdio: 'inherit',
  windowsHide: false,
})

if (result.error) throw result.error
process.exit(result.status ?? 1)
