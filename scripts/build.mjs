import { cp, copyFile, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

// Keep the runtime-proven ESM shape exactly; do not bundle or rewrite imports.
const source = new URL('../src/plugin.js', import.meta.url)
const target = new URL('../dist/plugin.js', import.meta.url)
const agentSource = new URL('../src/agent_plugin/', import.meta.url)
const agentTarget = new URL('../dist/agent-plugin/', import.meta.url)
const releaseRoot = fileURLToPath(new URL('../', import.meta.url))
const releaseDashboard = new URL('../dashboard/', import.meta.url)
const releaseDesktop = new URL('../desktop/', import.meta.url)
const root = fileURLToPath(new URL('../', import.meta.url))
execFileSync(process.execPath, ['--check', fileURLToPath(source)], { stdio: 'inherit' })
execFileSync(process.env.PYTHON || 'python', ['scripts/check-python.py'], { cwd: root, stdio: 'inherit' })
await mkdir(new URL('../dist/', import.meta.url), { recursive: true })
await copyFile(source, target)
await rm(agentTarget, { recursive: true, force: true })
await cp(agentSource, agentTarget, {
  recursive: true,
  filter: path => !path.includes('__pycache__') && !path.endsWith('.pyc')
})

// Mirror a unified Hermes plugin at the repository root for Install from Git.
const agentDirSource = fileURLToPath(agentSource)
for (const name of ['plugin.yaml', '__init__.py', 'tools.py', 'store.py']) {
  await copyFile(join(agentDirSource, name), join(releaseRoot, name))
}
await mkdir(releaseDashboard, { recursive: true })
for (const name of ['manifest.json', 'plugin_api.py']) {
  await copyFile(join(agentDirSource, 'dashboard', name), new URL(`../dashboard/${name}`, import.meta.url))
}
await mkdir(releaseDesktop, { recursive: true })
await copyFile(source, new URL('../desktop/plugin.js', import.meta.url))

const bytes = await readFile(target)
const manifest = { source: 'src/plugin.js', artifact: 'dist/plugin.js', bytes: bytes.length,
  sha256: createHash('sha256').update(bytes).digest('hex') }
await writeFile(new URL('../dist/build.json', import.meta.url), JSON.stringify(manifest, null, 2) + '\n')

async function packageFiles(directory, prefix = '') {
  const files = []
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (entry.name === '__pycache__' || entry.name.endsWith('.pyc')) continue
    const relative = prefix ? `${prefix}/${entry.name}` : entry.name
    const path = join(directory, entry.name)
    if (entry.isDirectory()) files.push(...await packageFiles(path, relative))
    else if (entry.isFile()) files.push(relative)
  }
  return files.sort()
}

const agentDir = fileURLToPath(agentTarget)
const files = []
for (const path of await packageFiles(agentDir)) {
  const data = await readFile(join(agentDir, path))
  files.push({ path, bytes: data.length, sha256: createHash('sha256').update(data).digest('hex') })
}
const agentManifest = { source: 'src/agent_plugin', artifact: 'dist/agent-plugin', files }
await writeFile(new URL('../dist/agent-plugin.build.json', import.meta.url), JSON.stringify(agentManifest, null, 2) + '\n')
console.log(JSON.stringify({ desktop: manifest, agentPlugin: agentManifest }, null, 2))
