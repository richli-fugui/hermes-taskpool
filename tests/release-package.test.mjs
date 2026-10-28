import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = dirname(fileURLToPath(import.meta.url)).replace(/[\\/]tests$/, '')

test('Git-installable unified plugin package mirrors canonical sources', () => {
  const copies = [
    ['plugin.yaml', 'src/agent_plugin/plugin.yaml'],
    ['__init__.py', 'src/agent_plugin/__init__.py'],
    ['tools.py', 'src/agent_plugin/tools.py'],
    ['store.py', 'src/agent_plugin/store.py'],
    ['dashboard/manifest.json', 'src/agent_plugin/dashboard/manifest.json'],
    ['dashboard/plugin_api.py', 'src/agent_plugin/dashboard/plugin_api.py'],
    ['desktop/plugin.js', 'src/plugin.js'],
  ]

  for (const [releasePath, sourcePath] of copies) {
    assert.equal(
      readFileSync(join(root, releasePath), 'utf8'),
      readFileSync(join(root, sourcePath), 'utf8'),
      `${releasePath} must match ${sourcePath}`,
    )
  }
})
