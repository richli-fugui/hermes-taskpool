import { Button, host, PALETTE_AREA, ROUTES_AREA, TITLEBAR_AREAS, useValue } from '@hermes/plugin-sdk'
import { useEffect, useMemo, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

// Hermes-tasktable: single-file desktop plugin (no JSX compilation).
const ID = 'pp-pane'
const TITLE = '任务池'
const STATUSES = [['todo', '待办'], ['doing', '进行中'], ['blocked', '阻塞'], ['review', '待验收'], ['done', '已完成']]
const LABEL = { todo: '待办', doing: '进行中', blocked: '阻塞', review: '待验收', done: '已完成' }

function keyFor(connection, profile, projectId) {
  return 'board.v1.' + JSON.stringify([connection, profile, projectId])
}

// Keep the installed plugin ID and old board.v1 keys as read-only migration sources.

function readBoard(storage, key) {
  if (!key) throw new Error('项目身份未确认，拒绝写入')
  // SDK get() returns the same fallback for missing and malformed JSON. Inspect
  // its backing key read-only so corrupt JSON cannot masquerade as an empty board.
  // This guard is the only version-coupled storage detail; all writes use the SDK.
  const encoded = window.localStorage.getItem('hermes.plugin.' + ID + '.' + key)
  if (encoded !== null) {
    try { JSON.parse(encoded) }
    catch { throw new Error('任务数据格式异常，未覆盖原数据') }
  }
  const raw = storage.get(key, null)
  if (raw === null) return []
  if (!raw || raw.version !== 1) throw new Error('任务数据格式异常，未覆盖原数据')
  return validateTasks(raw.tasks)
}

function validateTasks(tasks) {
  const ids = new Set()
  if (!Array.isArray(tasks) || tasks.some(function (task) {
    if (!task || typeof task.id !== 'string' || !task.id || ids.has(task.id) ||
        typeof task.title !== 'string' || !task.title.trim() ||
        (task.notes !== undefined && typeof task.notes !== 'string') ||
        !Object.hasOwn(LABEL, task.status)) return true
    ids.add(task.id)
    return false
  })) throw new Error('任务数据格式异常，未覆盖原数据')
  return tasks
}

function normalize(value) {
  const path = String(value || '').replaceAll('\\', '/').replace(/\/+$/, '') || (value === '/' ? '/' : '')
  // Windows drive/UNC paths are case-insensitive; POSIX paths are not.
  return /^[a-z]:\//i.test(path) || path.startsWith('//') ? path.toLowerCase() : path
}

function resolveProject(projects, cwd) {
  const path = normalize(cwd)
  if (!path) return null
  const hits = []
  for (const project of projects || []) {
    if (project.archived) continue
    const roots = [project.primary_path]
    for (const folder of project.folders || []) roots.push(folder.path)
    let best = -1
    for (const root of roots) {
      const value = normalize(root)
      if (value && (path === value || path.startsWith(value + '/'))) best = Math.max(best, value.length)
    }
    if (best >= 0) hits.push({ project: project, length: best })
  }
  hits.sort(function (a, b) { return b.length - a.length })
  return hits.length ? hits[0].project : null
}

function apiTasksPath(projectId, cwd) {
  return '/projects/' + encodeURIComponent(projectId) + '/tasks?cwd=' + encodeURIComponent(cwd || '')
}

function localClientId(storage) {
  const key = 'client.v1.id'
  const existing = storage.get(key, null)
  if (typeof existing === 'string' && existing) return existing
  const id = crypto.randomUUID()
  storage.set(key, id)
  if (storage.get(key, null) !== id) throw new Error('本机迁移标识保存失败，旧卡未导入')
  return id
}

const s = {
  root: { height: '100%', minHeight: 0, display: 'flex', flexDirection: 'column', fontSize: '13px', color: 'var(--ui-text-primary)' },
  head: { padding: '16px 18px 12px', borderBottom: '1px solid var(--ui-stroke-secondary)' },
  eyebrow: { fontSize: '10px', letterSpacing: '0.12em', color: 'var(--ui-text-tertiary)' },
  name: { fontSize: '16px', fontWeight: 600, margin: '8px 0 4px' },
  path: { fontSize: '10px', color: 'var(--ui-text-tertiary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  row: { display: 'flex', alignItems: 'center', gap: '6px' },
  bar: { padding: '10px 18px', display: 'flex', flexDirection: 'column', gap: '8px' },
  input: { width: '100%', padding: '7px 9px', border: '1px solid var(--ui-stroke-secondary)', borderRadius: '6px', background: 'transparent', color: 'inherit', outline: 'none' },
  btn: { padding: '6px 10px', border: '1px solid var(--ui-stroke-secondary)', borderRadius: '6px', background: 'transparent', color: 'inherit', cursor: 'pointer', whiteSpace: 'nowrap' },
  btnPrimary: { padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--ui-accent)', background: 'color-mix(in srgb, var(--ui-accent) 15%, transparent)', color: 'inherit', cursor: 'pointer', whiteSpace: 'nowrap' },
  tabs: { display: 'flex', gap: '4px', flexWrap: 'wrap' },
  tab: { border: 0, background: 'transparent', color: 'var(--ui-text-tertiary)', fontSize: '11px', padding: '3px 7px', borderRadius: '5px', cursor: 'pointer' },
  tabOn: { border: 0, background: 'color-mix(in srgb, var(--ui-accent) 12%, transparent)', color: 'var(--ui-text-primary)', fontSize: '11px', padding: '3px 7px', borderRadius: '5px', cursor: 'pointer' },
  scroll: { flex: 1, minHeight: 0, overflow: 'auto', padding: '0 18px 16px' },
  card: { border: '1px solid var(--ui-stroke-secondary)', borderRadius: '8px', padding: '11px', marginBottom: '8px' },
  cardTitle: { border: 0, background: 'transparent', color: 'inherit', textAlign: 'left', padding: 0, width: '100%', fontSize: '13px', cursor: 'pointer', lineHeight: 1.6 },
  note: { fontSize: '11px', color: 'var(--ui-text-tertiary)', marginTop: '6px', whiteSpace: 'pre-wrap' },
  meta: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '6px', marginTop: '10px', fontSize: '10px', color: 'var(--ui-text-tertiary)' },
  empty: { padding: '34px 8px', textAlign: 'center', color: 'var(--ui-text-tertiary)', lineHeight: 1.8 },
  foot: { borderTop: '1px solid var(--ui-stroke-secondary)', padding: '8px 18px', fontSize: '10px', color: 'var(--ui-text-tertiary)', display: 'flex', justifyContent: 'space-between', gap: '8px' },
  label: { fontSize: '11px', color: 'var(--ui-text-tertiary)', margin: '12px 0 5px' },
  area: { padding: '12px 18px', overflow: 'auto', flex: 1, minHeight: 0 }
}

function Pool(props) {
  const workspaceCwd = useValue(host.state.cwd)
  const focusedSessionId = useValue(host.state.focusedSessionId)
  const focusedSessionProfile = useValue(host.state.focusedSessionProfile)
  const gatewayProfile = useValue(host.state.profile)
  const profile = focusedSessionProfile || gatewayProfile
  const connection = useValue(host.state.connectionId) || 'local'
  const gateway = useValue(host.state.gateway)
  const identity = JSON.stringify([connection, profile, gateway])
  const [focusedSession, setFocusedSession] = useState(null)
  const [sessionError, setSessionError] = useState('')
  const [catalog, setCatalog] = useState(null)

  useEffect(function () {
    let alive = true
    if (!focusedSessionId) {
      setFocusedSession(null)
      setSessionError('')
      return function () { alive = false }
    }
    setFocusedSession(null)
    setSessionError('')
    host.request('session.info', { session_id: focusedSessionId }).then(function (info) {
      if (!alive) return
      if (!info || typeof info.cwd !== 'string') throw new Error('当前对话没有返回工作目录')
      setFocusedSession({ id: focusedSessionId, cwd: info.cwd })
    }).catch(function (err) {
      if (alive) setSessionError('读取当前对话工作目录失败：' + String((err && err.message) || err))
    })
    return function () { alive = false }
  }, [focusedSessionId, focusedSessionProfile, connection, workspaceCwd])

  const cwd = focusedSessionId
    ? (focusedSession && focusedSession.id === focusedSessionId ? focusedSession.cwd : '')
    : workspaceCwd

  useEffect(function () {
    let alive = true
    host.request('projects.list', { profile: profile }).then(function (payload) {
      if (alive) setCatalog({ identity: identity, projects: (payload && payload.projects) || [] })
    }).catch(function (err) {
      if (alive) setCatalog({ identity: identity, projects: [], error: '读取项目失败：' + String((err && err.message) || err) })
    })
    return function () { alive = false }
  }, [profile, connection, gateway, cwd, focusedSessionId])

  const projects = catalog && catalog.identity === identity ? catalog.projects : []
  const project = useMemo(function () { return resolveProject(projects, cwd) }, [projects, cwd])
  const boardKey = project && profile ? keyFor(connection, profile, project.id) : ''
  const loadError = sessionError || (catalog && catalog.identity === identity ? catalog.error : '')
  // Remount state synchronously when the owning project/profile/connection changes.
  return jsx(TaskBoard, { ctx: props.ctx, cwd: cwd, profile: profile, connection: connection,
    project: project, boardKey: boardKey, loadError: loadError }, boardKey || identity)
}

function TaskBoard(props) {
  const { ctx, cwd, profile, connection, project, boardKey } = props
  const storage = ctx.storage
  const [tasks, setTasks] = useState([])
  const [filter, setFilter] = useState('active')
  const [search, setSearch] = useState('')
  const [draft, setDraft] = useState('')
  const [editor, setEditor] = useState(null)
  const [error, setError] = useState('')
  const [migrationWarning, setMigrationWarning] = useState('')
  const [saved, setSaved] = useState('')
  const errorKind = useRef('')
  const addRequestKey = useRef(null)
  const migration = useRef({ state: 'pending', warning: '' })
  const mounted = useRef(false)

  async function refreshBoard() {
    if (!project || !boardKey) return
    let warning = migration.current.warning
    if (migration.current.state === 'pending') {
      const migrationKey = 'migration.v1.' + boardKey
      if (storage.get(migrationKey, false) === true) {
        migration.current = { state: 'done', warning: warning }
      } else {
        try {
          const legacy = readBoard(storage, boardKey)
          if (legacy.length) {
            const clientId = localClientId(storage)
            const result = await ctx.rest(
              '/projects/' + encodeURIComponent(project.id) + '/legacy-import',
              { method: 'POST', body: { cwd: cwd, source_key: clientId + ':' + boardKey, tasks: legacy } }
            )
            if (result && result.conflicts) warning = '旧卡有 ' + result.conflicts + ' 个冲突版本，已保留且未覆盖现有任务。'
          }
          storage.set(migrationKey, true)
          migration.current = { state: 'done', warning: warning }
        } catch (err) {
          const text = String((err && err.message) || err)
          if (text.includes('任务数据格式异常') || text.includes('未覆盖原数据') || text.includes('迁移标识保存失败')) {
            warning = text
            migration.current = { state: 'blocked', warning: warning }
          } else {
            warning = '旧任务迁移未确认：' + text
          }
        }
      }
    }
    try {
      const board = await ctx.rest(apiTasksPath(project.id, cwd))
      if (!board || !Array.isArray(board.tasks)) throw new Error('任务池数据格式异常，未覆盖原数据')
      validateTasks(board.tasks)
      if (mounted.current) {
        setTasks(board.tasks)
        if (errorKind.current === 'load') {
          errorKind.current = ''
          setError('')
        }
        setMigrationWarning(warning || migration.current.warning || '')
      }
    } catch (err) {
      if (mounted.current) {
        errorKind.current = 'load'
        setError(String((err && err.message) || err))
      }
    }
  }

  useEffect(function () {
    mounted.current = true
    const refresh = function () { refreshBoard() }
    const onFocus = function () { refreshBoard() }
    refresh()
    const disposeTimer = ctx.setInterval
      ? ctx.setInterval(refresh, 5000)
      : (() => { const id = window.setInterval(refresh, 5000); return function () { window.clearInterval(id) } })()
    window.addEventListener('focus', onFocus)
    return function () {
      mounted.current = false
      disposeTimer()
      window.removeEventListener('focus', onFocus)
    }
  }, [ctx, storage, boardKey, cwd, project && project.id])

  async function add() {
    const title = draft.trim()
    if (!title || !boardKey) return
    try {
      errorKind.current = ''
      setError('')
      if (!addRequestKey.current) addRequestKey.current = crypto.randomUUID()
      const result = await ctx.rest(apiTasksPath(project.id, cwd).split('?')[0], {
        method: 'POST',
        body: { cwd: cwd, task: { title: title, notes: '', status: 'todo' }, request_key: addRequestKey.current }
      })
      if (!result || !result.task) throw new Error('保存失败，服务端未确认任务卡')
      setTasks(function (latest) { return [result.task].concat(latest.filter(function (task) { return task.id !== result.task.id })) })
      setDraft('')
      addRequestKey.current = null
      setSaved('已保存到共享任务池')
      errorKind.current = ''
      setError('')
    } catch (err) {
      setSaved('')
      errorKind.current = 'write'
      setError(String((err && err.message) || err))
    }
  }

  async function saveEditor() {
    if (!editor) return
    const title = String(editor.title || '').trim()
    if (!title) return
    const current = tasks.find(function (task) { return task.id === editor.id })
    if (!current || JSON.stringify(current) !== editor.original) {
      errorKind.current = 'conflict'
      setError('任务已变化，请返回列表后重新打开，未覆盖其他修改')
      return
    }
    try {
      errorKind.current = ''
      setError('')
      const result = await ctx.rest(
        '/projects/' + encodeURIComponent(project.id) + '/tasks/' + encodeURIComponent(editor.id),
        { method: 'PATCH', body: { cwd: cwd, expected_revision: current.revision,
          title: title, notes: String(editor.notes || '').trim(), status: editor.status } }
      )
      if (!result || !result.task) throw new Error('保存失败，服务端未确认任务卡')
      setTasks(function (latest) { return latest.map(function (task) { return task.id === editor.id ? result.task : task }) })
      setSaved('已保存到共享任务池')
      errorKind.current = ''
      setEditor(null)
    } catch (err) {
      setSaved('')
      errorKind.current = 'write'
      setError(String((err && err.message) || err))
    }
  }

  function reference(task) {
    const lines = [
      '[项目任务引用 · 不自动执行]',
      '项目：' + project.name,
      '项目ID：' + project.id,
      '任务ID：' + task.id,
      '标题：' + task.title,
      '状态：' + (LABEL[task.status] || task.status),
      '说明：' + (task.notes || '无'),
      '请结合这张任务卡与我接下来的要求讨论；不要仅因引用卡片就开始执行。'
    ]
    host.composer.insertText(null, lines.join('\n'), { mode: 'block' }).then(function (ok) {
      if (ok) host.notify({ kind: 'info', message: '任务引用已放入输入框，尚未发送' })
      else setError('当前输入框不可用，请改用复制引用')
    }).catch(function (err) { setError(String((err && err.message) || err)) })
  }

  const visible = tasks.filter(function (task) {
    const done = task.status === 'done'
    if (filter === 'active' && done) return false
    if (filter === 'done' && !done) return false
    return (task.title + ' ' + (task.notes || '')).toLowerCase().includes(search.toLowerCase())
  })
  const open = tasks.filter(function (task) { return task.status !== 'done' }).length
  const finished = tasks.length - open

  const message = error || migrationWarning || props.loadError
  const alert = message ? jsx('div', { role: 'alert', style: { margin: '10px 18px 0', padding: '8px', border: '1px solid var(--ui-stroke-secondary)', borderRadius: '6px', fontSize: '11px' }, children: message }) : null
  const header = jsxs('div', { style: s.head, children: [
    jsx('div', { style: s.eyebrow, children: 'PROJECT TASK POOL' }),
    jsx('div', { style: s.name, children: project ? project.name : '未识别项目' }),
    jsx('div', { style: s.path, children: project ? (project.primary_path || cwd || '') : (cwd || '请先打开一个项目目录') }),
    jsxs('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '10px', gap: '6px' }, children: [
      jsx('span', { style: { fontSize: '11px', color: 'var(--ui-text-tertiary)' }, children: open + ' 项待推进 · ' + finished + ' 项已完成' }),
      jsx('span', { style: { fontSize: '10px', color: 'var(--ui-text-tertiary)' }, children: connection + ' · ' + profile })
    ] })
  ] })

  if (!project) {
    return jsxs('div', { style: s.root, children: [header, alert, jsx('div', { style: s.empty, children: '当前工作目录不属于任何 Hermes 项目。切到一个项目目录后，这里只显示该项目的任务。' })] })
  }

  if (editor) {
    return jsxs('div', { style: s.root, children: [header, alert, jsxs('div', { style: s.area, children: [
      jsxs('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' }, children: [
        jsx('strong', { children: '任务详情' }),
        jsx('button', { type: 'button', style: s.tab, onClick: function () { setEditor(null) }, children: '返回列表' })
      ] }),
      jsx('div', { style: s.label, children: '标题' }),
      jsx('input', { style: s.input, value: editor.title, onChange: function (e) { setEditor(Object.assign({}, editor, { title: e.target.value })) } }),
      jsx('div', { style: s.label, children: '状态' }),
      jsx('select', { style: s.input, value: editor.status, onChange: function (e) { setEditor(Object.assign({}, editor, { status: e.target.value })) }, children: STATUSES.map(function (p) { return jsx('option', { value: p[0], children: p[1] }, p[0]) }) }),
      jsx('div', { style: s.label, children: '说明 / 下一步 / 验收' }),
      jsx('textarea', { style: Object.assign({}, s.input, { minHeight: '120px', resize: 'vertical' }), value: editor.notes, onChange: function (e) { setEditor(Object.assign({}, editor, { notes: e.target.value })) } }),
      jsxs('div', { style: { display: 'flex', gap: '6px', marginTop: '14px' }, children: [
        jsx('button', { type: 'button', style: s.btnPrimary, onClick: saveEditor, children: '保存修改' }),
        jsx('button', { type: 'button', style: s.btn, onClick: function () { reference(editor) }, children: '引用到对话' })
      ] }),
      jsx('div', { style: { fontSize: '10px', color: 'var(--ui-text-tertiary)', marginTop: '10px', wordBreak: 'break-all' }, children: '稳定 ID · ' + editor.id })
    ] })] })
  }

  return jsxs('div', { style: s.root, children: [
    header,
    alert,
    jsxs('div', { style: s.bar, children: [
      jsxs('div', { style: s.row, children: [
        jsx('input', {
          style: s.input,
          value: draft,
          placeholder: '这个项目的下一步…',
          onChange: function (e) { if (e.target.value !== draft) addRequestKey.current = null; setDraft(e.target.value) },
          onKeyDown: function (e) { if (e.key === 'Enter' && !e.nativeEvent.isComposing && e.nativeEvent.keyCode !== 229) add() }
        }),
        jsx('button', { type: 'button', style: s.btnPrimary, onClick: add, children: '添加' })
      ] }),
      jsx('input', { style: s.input, value: search, placeholder: '搜索这个项目的任务…', onChange: function (e) { setSearch(e.target.value) } }),
      jsx('div', { style: s.tabs, children: [['active', '待推进'], ['done', '已完成'], ['all', '全部']].map(function (p) {
        return jsx('button', { type: 'button', style: filter === p[0] ? s.tabOn : s.tab, onClick: function () { setFilter(p[0]) }, children: p[1] }, p[0])
      }) })
    ] }),
    jsx('div', { style: s.scroll, children: visible.length === 0
      ? jsx('div', { style: s.empty, children: filter === 'done' ? '已完成的任务会留在这里。' : '还没有任务。上面写一条，按回车。' })
      : STATUSES.map(function (p) {
          const group = visible.filter(function (task) { return task.status === p[0] })
          if (group.length === 0) return null
          return jsxs('div', { children: [
            jsx('div', { style: { fontSize: '10px', color: 'var(--ui-text-tertiary)', margin: '12px 0 6px' }, children: p[1] + ' · ' + group.length }),
            group.map(function (task) {
              return jsxs('div', { style: s.card, children: [
                jsx('button', { type: 'button', style: s.cardTitle, onClick: function () { setError(''); setEditor(Object.assign({}, task, { original: JSON.stringify(task) })) }, children: task.title }),
                task.notes ? jsx('div', { style: s.note, children: task.notes }) : null,
                jsxs('div', { style: s.meta, children: [
                  jsx('span', { children: LABEL[task.status] || task.status }),
                  jsx('span', { style: { fontFamily: 'monospace' }, children: task.id.slice(0, 8) }),
                  jsx('button', { type: 'button', style: s.tab, onClick: function () { reference(task) }, children: '引用 ↗' })
                ] })
              ] }, task.id)
            })
          ] }, p[0])
        })
    }),
    jsxs('div', { style: s.foot, children: [
      jsx('span', { children: saved || '共享服务端保存 · Agent可读写 · 不自动执行' }),
      jsx('span', { children: tasks.length + ' 张卡' })
    ] })
  ] })
}

export default {
  id: ID,
  name: '项目任务池原型',
  description: '当前 Hermes 项目的共享任务卡池：桌面与 Agent 共用，不派发、不迁移 DSH。',
  register(ctx) {
    const toggle = function () { ctx.runAction('view.toggleRightSidebar') }
    ctx.register({ id: 'page', area: ROUTES_AREA, data: { path: '/task-pool' }, render: () => jsx(Pool, { ctx: ctx }) })
    ctx.register({ id: 'pool', area: 'panes', title: TITLE, data: { placement: 'right' }, render: () => jsx(Pool, { ctx: ctx }) })
    ctx.register({
      id: 'icon',
      area: TITLEBAR_AREAS.right,
      order: 60,
      render: () => jsx(Button, {
        'aria-label': '任务池',
        title: '任务池（显示/隐藏右栏）',
        className: 'bg-transparent select-none',
        size: 'icon-titlebar',
        variant: 'ghost',
        onClick: toggle,
        children: jsx('svg', {
          width: '16', height: '16', viewBox: '0 0 16 16', fill: 'none',
          stroke: 'currentColor', strokeWidth: '1.3', strokeLinecap: 'round', strokeLinejoin: 'round',
          'aria-hidden': 'true',
          children: [
            jsx('rect', { x: '1.6', y: '1.6', width: '12.8', height: '12.8', rx: '2.4' }, 'frame'),
            jsx('path', { d: 'M4.6 8.2l2.1 2.1 4.4-4.4' }, 'check')
          ]
        })
      })
    })
    ctx.register({
      id: 'cmd',
      area: PALETTE_AREA,
      data: {
        id: 'pp-pane.toggle',
        label: '任务池：显示/隐藏右栏',
        keywords: ['task', 'pool', '任务池'],
        run: toggle
      }
    })
  }
}
