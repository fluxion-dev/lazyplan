const FEEDBACK_KEY = 'lpui-ux-review:feedback:v1'
const DRAFT_KEY = 'lpui-ux-review:drafts:v1'
const REVIEWER_KEY = 'lpui-ux-review:reviewer'
const VERDICTS = ['approve', 'concern', 'idea', 'question']
const SEVERITIES = ['low', 'medium', 'high', 'blocker']
const TAGS = [
  'hierarchy',
  'density',
  'copy',
  'keys',
  'color',
  'empty-state',
  'flow',
  'accessibility',
  'consistency',
  'performance'
]
const STATUS_GLYPH = {
  unreviewed: '○',
  approved: '✓',
  concern: '!',
  idea: '+',
  question: '?'
}
const STATUS_LABEL = {
  unreviewed: 'Not reviewed',
  approved: 'Approved',
  concern: 'Has concerns',
  idea: 'Has ideas',
  question: 'Has questions'
}

const state = {
  manifest: null,
  feedback: [],
  drafts: {},
  backend: 'local',
  dataPath: '',
  sceneId: null,
  editingEntry: null,
  reporter: '',
  filters: { q: '', status: 'all', group: 'all' },
  planText: '',
  planCommand: '',
  planDoc: null
}

const $ = (selector) => document.querySelector(selector)

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag)
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue
    if (key === 'class') node.className = value
    else if (key === 'text') node.textContent = value
    else if (key === 'html') node.innerHTML = value
    else if (key === 'dataset') Object.assign(node.dataset, value)
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value)
    } else node.setAttribute(key, value === true ? '' : String(value))
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue
    node.append(child instanceof Node ? child : document.createTextNode(String(child)))
  }
  return node
}


function formatDate(iso) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return 'unknown time'
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

function plural(count, singular, pluralForm = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralForm}`
}

function newId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `fb-${crypto.randomUUID()}`
  }
  return `fb-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function truncate(text, length = 160) {
  const clean = String(text || '').replace(/\s+/g, ' ').trim()
  if (!clean) return ''
  return clean.length > length ? `${clean.slice(0, length - 1)}…` : clean
}

function currentScene() {
  if (!state.manifest) return null
  return state.manifest.scenes.find((scene) => scene.id === state.sceneId) || null
}

function groupFor(id) {
  return state.manifest?.groups.find((group) => group.id === id) || { title: id, blurb: '' }
}

function entriesFor(sceneId) {
  return state.feedback
    .filter((entry) => entry.scene === sceneId)
    .sort((a, b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')))
}

function statusFor(sceneId) {
  const entries = entriesFor(sceneId)
  if (!entries.length) return 'unreviewed'
  const latest = entries[0]
  if (latest.verdict === 'approve') return 'approved'
  return ['concern', 'idea', 'question'].includes(latest.verdict) ? latest.verdict : 'approved'
}

function actionableEntries() {
  return state.feedback.filter((entry) => ['concern', 'idea', 'question'].includes(entry.verdict))
}

function persistLocalFeedback() {
  localStorage.setItem(FEEDBACK_KEY, JSON.stringify(state.feedback))
}

function loadLocalFeedback() {
  try {
    const raw = JSON.parse(localStorage.getItem(FEEDBACK_KEY) || '[]')
    return Array.isArray(raw) ? raw.filter(isEntry) : []
  } catch {
    return []
  }
}

function loadDrafts() {
  try {
    const raw = JSON.parse(localStorage.getItem(DRAFT_KEY) || '{}')
    return raw && typeof raw === 'object' ? raw : {}
  } catch {
    return {}
  }
}

function persistDrafts() {
  localStorage.setItem(DRAFT_KEY, JSON.stringify(state.drafts))
}

function isEntry(value) {
  return (
    value &&
    typeof value === 'object' &&
    typeof value.id === 'string' &&
    typeof value.scene === 'string' &&
    VERDICTS.includes(value.verdict)
  )
}

function normalizeEntry(raw) {
  if (!isEntry(raw)) return null
  return {
    id: raw.id,
    scene: raw.scene,
    verdict: VERDICTS.includes(raw.verdict) ? raw.verdict : 'concern',
    severity: SEVERITIES.includes(raw.severity) ? raw.severity : 'medium',
    tags: Array.isArray(raw.tags) ? raw.tags.filter((tag) => TAGS.includes(tag)) : [],
    text: String(raw.text || '').slice(0, 8000),
    reviewer: String(raw.reviewer || '').slice(0, 80),
    createdAt: String(raw.createdAt || new Date().toISOString()),
    updatedAt: String(raw.updatedAt || raw.createdAt || new Date().toISOString())
  }
}

function upsertEntry(entry) {
  const index = state.feedback.findIndex((item) => item.id === entry.id)
  if (index >= 0) state.feedback[index] = entry
  else state.feedback.push(entry)
}

async function detectBackend() {
  state.backend = 'local'
  state.feedback = loadLocalFeedback()
  try {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 1600)
    const response = await fetch('./api/health', {
      cache: 'no-store',
      signal: controller.signal
    })
    clearTimeout(timer)
    if (!response.ok) return
    const payload = await response.json()
    if (payload.service !== 'lpui-ux-review') return
    state.backend = 'server'
    state.dataPath = payload.data || '.agents/ux-review/feedback.json'
    const loaded = await fetch('./api/feedback', { cache: 'no-store' })
    if (!loaded.ok) throw new Error(`feedback read failed: ${loaded.status}`)
    const body = await loaded.json()
    state.feedback = Array.isArray(body.feedback) ? body.feedback.map(normalizeEntry).filter(Boolean) : []
  } catch {
    state.backend = 'local'
    state.feedback = loadLocalFeedback()
  }
}

async function persistEntry(entry) {
  if (state.backend === 'server') {
    const exists = state.feedback.some((item) => item.id === entry.id)
    const url = exists ? `./api/feedback/${encodeURIComponent(entry.id)}` : './api/feedback'
    const response = await fetch(url, {
      method: exists ? 'PATCH' : 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(entry)
    })
    if (!response.ok) throw new Error(`save failed: ${response.status}`)
    const body = await response.json()
    upsertEntry(normalizeEntry(body.entry || entry))
  } else {
    upsertEntry(entry)
    persistLocalFeedback()
  }
}

async function removeEntry(id) {
  if (state.backend === 'server') {
    const response = await fetch(`./api/feedback/${encodeURIComponent(id)}`, { method: 'DELETE' })
    if (!response.ok && response.status !== 404) throw new Error(`delete failed: ${response.status}`)
  }
  state.feedback = state.feedback.filter((entry) => entry.id !== id)
  if (state.backend === 'local') persistLocalFeedback()
}

function toast(message, tone = 'ok') {
  const node = $('#toast')
  node.textContent = message
  node.style.borderColor = tone === 'error' ? 'rgb(248 113 113 / 0.5)' : ''
  node.style.color = tone === 'error' ? 'var(--red)' : ''
  node.classList.add('is-visible')
  clearTimeout(toast.timer)
  toast.timer = setTimeout(() => node.classList.remove('is-visible'), 3200)
}

function progress() {
  const scenes = state.manifest?.scenes || []
  const reviewed = scenes.filter((scene) => statusFor(scene.id) !== 'unreviewed').length
  const concerns = scenes.filter((scene) => statusFor(scene.id) === 'concern').length
  const actionable = actionableEntries().length
  return { total: scenes.length, reviewed, concerns, actionable }
}

function renderProgress() {
  const { total, reviewed, concerns, actionable } = progress()
  const percent = total ? Math.round((reviewed / total) * 100) : 0
  $('#progress-fill').style.width = `${percent}%`
  $('#progress-label').textContent = `${reviewed}/${total} screens reviewed · ${plural(concerns, 'concern')} · ${plural(actionable, 'actionable entry', 'actionable entries')}`
}

function renderStorageChip() {
  const chip = $('#storage-chip')
  if (state.backend === 'server') {
    chip.textContent = 'saved to file'
    chip.className = 'chip chip-approved'
    chip.title = `Feedback is written to ${state.dataPath}`
  } else {
    chip.textContent = 'saved in browser'
    chip.className = 'chip chip-quiet'
    chip.title = 'Feedback is stored in this browser. Use Export to move it, or run tools/ux-review-server.py to save to a file.'
  }
}

function filteredScenes() {
  const query = state.filters.q.trim().toLowerCase()
  return (state.manifest?.scenes || []).filter((scene) => {
    if (state.filters.group !== 'all' && scene.group !== state.filters.group) return false
    const status = statusFor(scene.id)
    if (state.filters.status !== 'all' && status !== state.filters.status) return false
    if (!query) return true
    const group = groupFor(scene.group)
    return [scene.id, scene.title, scene.state, scene.description, group.title, scene.keys]
      .join(' ')
      .toLowerCase()
      .includes(query)
  })
}

function renderGroupOptions() {
  const select = $('#group-filter')
  const previous = state.filters.group
  select.replaceChildren(
    el('option', { value: 'all' }, `All groups (${state.manifest.scenes.length})`),
    ...state.manifest.groups.map((group) =>
      el('option', { value: group.id }, `${group.title} (${group.count})`)
    )
  )
  select.value = previous
}

function renderNav() {
  const nav = $('#scene-nav')
  const scenes = filteredScenes()
  nav.replaceChildren()
  if (!scenes.length) {
    nav.append(
      el(
        'p',
        { class: 'feedback-empty', style: 'margin:0.5rem;' },
        'No screens match these filters.'
      )
    )
    return
  }
  let currentGroup = ''
  for (const scene of scenes) {
    if (scene.group !== currentGroup) {
      currentGroup = scene.group
      const group = groupFor(scene.group)
      const inGroup = scenes.filter((item) => item.group === scene.group)
      nav.append(
        el(
          'div',
          { class: 'nav-group' },
          el(
            'p',
            { class: 'nav-group-title' },
            el('span', {}, group.title),
            el('span', {}, String(inGroup.length))
          )
        )
      )
    }
    const status = statusFor(scene.id)
    const count = entriesFor(scene.id).length
    nav.append(
      el(
        'button',
        {
          class: `nav-item${scene.id === state.sceneId ? ' is-current' : ''}`,
          type: 'button',
          'data-action': 'select-scene',
          'data-scene': scene.id,
          title: scene.title
        },
        el('span', { class: 'nav-dot', dataset: { status }, 'aria-hidden': 'true' }, STATUS_GLYPH[status]),
        el('span', { class: 'nav-label' }, scene.title),
        count ? el('span', { class: 'nav-count' }, String(count)) : null
      )
    )
  }
}

function verdictChip(verdict) {
  return el('span', { class: `chip chip-${verdict}` }, verdict)
}

function renderScene() {
  const scene = currentScene()
  const view = $('#review-view')
  view.hidden = false
  $('#plan-view').hidden = true
  if (!scene) {
    view.replaceChildren(
      el(
        'div',
        { class: 'empty-big' },
        el('div', {}, el('h1', {}, 'Choose a screen'), el('p', {}, 'Pick a screen from the list to review it.'))
      )
    )
    return
  }
  const group = groupFor(scene.group)
  const entries = entriesFor(scene.id)
  const status = statusFor(scene.id)
  const form = ensureComposer(scene)

  const article = el('article', { class: 'screen' })
  article.append(
    el(
      'header',
      { class: 'screen-head' },
      el(
        'div',
        {},
        el(
          'p',
          { class: 'eyebrow' },
          el('span', {}, group.title),
          el('span', { class: 'sep' }, '/'),
          el('span', {}, scene.id)
        ),
        el('h1', {}, scene.title),
        el('p', { class: 'screen-state' }, scene.state)
      ),
      el(
        'div',
        { class: 'head-actions' },
        el('span', { class: `chip chip-${status === 'unreviewed' ? 'quiet' : status}` }, STATUS_LABEL[status]),
        el(
          'button',
          {
            class: 'btn btn-quiet',
            type: 'button',
            'data-action': 'approve-current',
            title: 'Add an approval entry without opening the form'
          },
          'Approve screen'
        ),
        el(
          'button',
          {
            class: 'btn btn-quiet',
            type: 'button',
            'data-action': 'copy-scene-link',
            title: 'Copy a direct link to this screen'
          },
          'Copy link'
        )
      )
    )
  )

  const shot = el(
    'figure',
    { class: 'figure-card' },
    el(
      'div',
      { class: 'figure-bar' },
      el('p', {}, `${scene.width} × ${scene.height} · captured from the real TUI`),
      el(
        'button',
        { class: 'btn btn-small btn-quiet', type: 'button', 'data-action': 'zoom' },
        'Open full size'
      )
    ),
    el(
      'button',
      {
        class: 'shot-button',
        type: 'button',
        'data-action': 'zoom',
        'aria-label': `Open the ${scene.title} screenshot full size`
      },
      el(
        'picture',
        {},
        el('source', { srcset: `./${scene.webp}`, type: 'image/webp' }),
        el('img', {
          src: `./${scene.image}`,
          alt: `${scene.title}: ${scene.description}`,
          width: String(scene.width),
          height: String(scene.height),
          decoding: 'async',
          loading: 'eager'
        })
      )
    )
  )

  const side = el(
    'div',
    { class: 'side-stack' },
    el(
      'section',
      { class: 'panel' },
      el('h2', {}, 'What this screen is'),
      el('p', {}, scene.description)
    ),
    el(
      'section',
      { class: 'panel' },
      el('h2', {}, 'What to look for'),
      el('ul', {}, ...scene.lookFor.map((item) => el('li', {}, item)))
    ),
    el(
      'section',
      { class: 'panel' },
      el('h2', {}, 'Keys on this screen'),
      el('p', { class: 'keys-line' }, scene.keys)
    ),
    el(
      'section',
      { class: 'panel' },
      el('h2', {}, 'Review state'),
      el('div', { class: 'status-line' }, el('span', {}, 'Verdict'), el('span', { class: `chip chip-${status === 'unreviewed' ? 'quiet' : status}` }, STATUS_LABEL[status])),
      el('div', { class: 'status-line' }, el('span', {}, 'Entries'), el('span', {}, String(entries.length))),
      el('div', { class: 'status-line' }, el('span', {}, 'Group'), el('span', {}, group.title))
    )
  )

  article.append(el('div', { class: 'screen-grid' }, shot, side))

  const composer = el(
    'section',
    { class: 'composer', id: 'composer' },
    el('h2', {}, state.editingEntry ? 'Edit feedback' : 'Leave feedback'),
    el(
      'p',
      { class: 'composer-hint' },
      'One focused note per screen works best. Concerns get a severity; every entry can carry tags.'
    ),
    el(
      'form',
      { id: 'feedback-form', novalidate: true },
      el(
        'div',
        { class: 'verdict-row', role: 'group', 'aria-label': 'Verdict' },
        ...VERDICTS.map((verdict) =>
          el(
            'button',
            {
              class: `verdict${form.verdict === verdict ? ' is-selected' : ''}`,
              type: 'button',
              'data-action': 'pick-verdict',
              'data-verdict': verdict,
              'aria-pressed': form.verdict === verdict ? 'true' : 'false'
            },
            verdict
          )
        )
      ),
      el(
        'div',
        { class: 'form-grid' },
        el(
          'label',
          { class: 'field' },
          el('span', { class: 'field-label' }, 'Severity'),
          el(
            'select',
            { id: 'severity', name: 'severity' },
            ...SEVERITIES.map((severity) =>
              el('option', { value: severity, selected: form.severity === severity ? true : undefined }, severity)
            )
          )
        ),
        el(
          'label',
          { class: 'field' },
          el('span', { class: 'field-label' }, 'Reviewer'),
          el('input', {
            id: 'entry-reviewer',
            name: 'reviewer',
            type: 'text',
            value: form.reviewer,
            placeholder: 'your name',
            autocomplete: 'off'
          })
        )
      ),
      el(
        'div',
        {},
        el('span', { class: 'field-label' }, 'Tags'),
        el(
          'div',
          { class: 'tag-row' },
          ...TAGS.map((tag) =>
            el(
              'button',
              {
                class: `tag${form.tags.includes(tag) ? ' is-selected' : ''}`,
                type: 'button',
                'data-action': 'pick-tag',
                'data-tag': tag,
                'aria-pressed': form.tags.includes(tag) ? 'true' : 'false'
              },
              tag
            )
          )
        )
      ),
      el(
        'label',
        { class: 'field' },
        el('span', { class: 'field-label' }, 'What did you notice?'),
        el('textarea', {
          id: 'feedback-text',
          name: 'text',
          placeholder: 'Where does this screen work, and where does it get in the way?',
          maxlength: '8000'
        }, form.text)
      ),
      el(
        'div',
        { class: 'composer-actions' },
        el('button', { class: 'btn btn-gold', type: 'submit', id: 'save-feedback' }, state.editingEntry ? 'Update feedback' : 'Save feedback'),
        el(
          'button',
          { class: 'btn btn-quiet', type: 'button', 'data-action': 'clear-composer' },
          state.editingEntry ? 'Cancel edit' : 'Clear'
        ),
        el('span', { class: 'draft-note', id: 'draft-note' }, form.saved ? 'Draft saved locally' : ''),
        el('span', { class: 'spacer' }),
        el('span', { class: 'draft-note' }, 'Ctrl + Enter saves')
      )
    )
  )

  const list = el(
    'section',
    { class: 'panel' },
    el('h2', {}, `Feedback on this screen (${entries.length})`),
    entries.length
      ? el('div', { class: 'feedback-list' }, ...entries.map(renderEntry))
      : el('div', { class: 'feedback-empty' }, 'No feedback yet. Approve it, or leave the first note.')
  )

  article.append(el('div', { class: 'feedback-wrap' }, composer, list))
  view.replaceChildren(article)
  bindComposer(scene)
  renderProgress()
  renderNav()
}

function composerState(scene) {
  const draft = state.drafts[scene.id]
  const reviewer = state.reviewer || ''
  return {
    verdict: draft?.verdict || 'concern',
    severity: draft?.severity || 'medium',
    tags: Array.isArray(draft?.tags) ? draft.tags : [],
    text: draft?.text || '',
    reviewer: draft?.reviewer || reviewer,
    saved: Boolean(draft?.savedAt)
  }
}

function renderEntry(entry) {
  const scene = state.manifest.scenes.find((item) => item.id === entry.scene)
  const tags = (entry.tags || []).map((tag) => el('span', { class: 'chip chip-quiet' }, tag))
  return el(
    'article',
    { class: 'entry', dataset: { verdict: entry.verdict } },
    el(
      'div',
      { class: 'entry-head' },
      verdictChip(entry.verdict),
      el('span', { class: 'severity', dataset: { severity: entry.severity } }, entry.severity),
      ...tags,
      el(
        'div',
        { class: 'entry-actions' },
        el(
          'button',
          {
            class: 'btn btn-quiet',
            type: 'button',
            'data-action': 'edit-entry',
            'data-entry': entry.id
          },
          'Edit'
        ),
        el(
          'button',
          {
            class: 'btn btn-danger',
            type: 'button',
            'data-action': 'delete-entry',
            'data-entry': entry.id
          },
          'Delete'
        )
      )
    ),
    el('p', { class: 'entry-text' }, entry.text || 'Approved without a note.'),
    el(
      'div',
      { class: 'entry-meta' },
      el('span', {}, entry.reviewer ? `@${entry.reviewer}` : '@anonymous'),
      el('span', {}, '·'),
      el('span', {}, formatDate(entry.createdAt)),
      scene ? el('span', {}, '·') : null,
      scene ? el('span', {}, scene.title) : null
    )
  )
}

function bindComposer(scene) {
  const form = $('#feedback-form')
  if (!form) return
  const saveDraft = () => {
    snapshotComposer(scene)
    const note = $('#draft-note')
    if (note) note.textContent = 'Draft saved locally'
  }
  $('#feedback-text')?.addEventListener('input', saveDraft)
  $('#severity')?.addEventListener('change', saveDraft)
  $('#entry-reviewer')?.addEventListener('input', saveDraft)
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    await submitFeedback(scene)
  })
}

function ensureComposer(scene) {
  if (!state.composer || state.composer.scene !== scene.id) {
    state.composer = { scene: scene.id, ...composerState(scene) }
  }
  return state.composer
}

function snapshotComposer(scene) {
  const composer = ensureComposer(scene)
  composer.text = $('#feedback-text')?.value ?? composer.text ?? ''
  composer.severity = $('#severity')?.value ?? composer.severity ?? 'medium'
  composer.reviewer = $('#entry-reviewer')?.value ?? composer.reviewer ?? ''
  state.drafts[scene.id] = {
    verdict: composer.verdict,
    severity: composer.severity,
    tags: [...(composer.tags || [])],
    text: composer.text,
    reviewer: composer.reviewer,
    savedAt: new Date().toISOString()
  }
  persistDrafts()
  return composer
}

async function submitFeedback(scene) {
  const composer = ensureComposer(scene)
  const text = $('#feedback-text')?.value.trim() || ''
  const reviewer = $('#entry-reviewer')?.value.trim() || state.reviewer || 'anonymous'
  const severity = $('#severity')?.value || 'medium'
  const now = new Date().toISOString()
  if (composer.verdict !== 'approve' && !text) {
    toast('Add a note before saving that verdict.', 'error')
    $('#feedback-text')?.focus()
    return
  }
  const existing = state.editingEntry
    ? state.feedback.find((entry) => entry.id === state.editingEntry)
    : null
  const entry = normalizeEntry({
    id: existing?.id || newId(),
    scene: scene.id,
    verdict: composer.verdict,
    severity,
    tags: composer.tags,
    text,
    reviewer,
    createdAt: existing?.createdAt || now,
    updatedAt: now
  })
  try {
    await persistEntry(entry)
  } catch (error) {
    toast(error.message || 'Could not save feedback', 'error')
    return
  }
  delete state.drafts[scene.id]
  persistDrafts()
  state.editingEntry = null
  state.composer = null
  toast(existing ? 'Feedback updated.' : 'Feedback saved.')
  renderScene()
}

async function approveCurrent() {
  const scene = currentScene()
  if (!scene) return
  const now = new Date().toISOString()
  const entry = normalizeEntry({
    id: newId(),
    scene: scene.id,
    verdict: 'approve',
    severity: 'low',
    tags: [],
    text: 'Approved during the screen review.',
    reviewer: state.reviewer || 'anonymous',
    createdAt: now,
    updatedAt: now
  })
  try {
    await persistEntry(entry)
    toast(`${scene.title} approved.`)
    renderScene()
  } catch (error) {
    toast(error.message || 'Could not save approval', 'error')
  }
}

function startEditEntry(id) {
  const entry = state.feedback.find((item) => item.id === id)
  const scene = entry ? state.manifest.scenes.find((item) => item.id === entry.scene) : null
  if (!entry || !scene) return
  state.editingEntry = entry.id
  state.composer = {
    scene: scene.id,
    verdict: entry.verdict,
    severity: entry.severity,
    tags: [...(entry.tags || [])],
    text: entry.text || '',
    reviewer: entry.reviewer || ''
  }
  if (state.sceneId !== scene.id) {
    state.sceneId = scene.id
    updateHash('scene')
  }
  renderScene()
  $('#composer')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  $('#feedback-text')?.focus()
}

async function deleteEntry(id) {
  const entry = state.feedback.find((item) => item.id === id)
  if (!entry) return
  if (!window.confirm('Delete this feedback entry?')) return
  try {
    await removeEntry(id)
    toast('Feedback entry deleted.')
    renderScene()
  } catch (error) {
    toast(error.message || 'Could not delete feedback', 'error')
  }
}

function updateHash(mode = 'scene') {
  const hash = mode === 'plan' ? '#plan' : `#scene=${encodeURIComponent(state.sceneId || '')}`
  history.replaceState(null, '', hash)
}

function selectScene(id, { scroll = true } = {}) {
  if (!state.manifest) return
  if (!state.manifest.scenes.some((scene) => scene.id === id)) return
  state.sceneId = id
  state.editingEntry = null
  state.composer = null
  updateHash('scene')
  renderScene()
  if (scroll) window.scrollTo({ top: 0, behavior: 'smooth' })
}

function moveScene(delta) {
  const scenes = filteredScenes()
  if (!scenes.length) return
  const index = scenes.findIndex((scene) => scene.id === state.sceneId)
  const next = scenes[(index + delta + scenes.length) % scenes.length]
  selectScene(next.id)
}

function setFilterStatus(status) {
  state.filters.status = status
  document.querySelectorAll('.status-btn').forEach((button) => {
    button.classList.toggle('is-active', button.dataset.status === status)
  })
  renderNav()
}

function copyText(text, label = 'Copied.') {
  const done = () => toast(label)
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done))
  } else {
    fallbackCopy(text, done)
  }
}

function fallbackCopy(text, done) {
  const area = el('textarea', { style: 'position:fixed;left:-9999px;top:-9999px;' })
  area.value = text
  document.body.append(area)
  area.select()
  try {
    document.execCommand('copy')
    done()
  } catch {
    toast('Copy failed; select the text manually.', 'error')
  } finally {
    area.remove()
  }
}

function download(name, text, type = 'application/json') {
  const blob = new Blob([text], { type })
  const url = URL.createObjectURL(blob)
  const anchor = el('a', { href: url, download: name })
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1500)
}

function feedbackExport() {
  return {
    version: 1,
    app: 'lpui-ux-review',
    versionLabel: state.manifest?.version || '',
    exportedAt: new Date().toISOString(),
    backend: state.backend,
    groups: state.manifest?.groups || [],
    scenes: state.manifest?.scenes || [],
    feedback: state.feedback
  }
}

function exportJson() {
  download('lpui-ux-feedback.json', JSON.stringify(feedbackExport(), null, 2) + '\n')
  toast('Feedback JSON downloaded.')
}

function exportMarkdown() {
  const lines = [
    '# lpui UX review feedback',
    '',
    `Generated ${new Date().toISOString()}`,
    `Version ${state.manifest?.version || 'unknown'} · ${plural(state.feedback.length, 'entry', 'entries')}`,
    ''
  ]
  for (const group of state.manifest.groups) {
    const scenes = state.manifest.scenes.filter((scene) => scene.group === group.id)
    const groupEntries = state.feedback.filter((entry) => scenes.some((scene) => scene.id === entry.scene))
    if (!groupEntries.length) continue
    lines.push(`## ${group.title}`, '')
    for (const scene of scenes) {
      const entries = entriesFor(scene.id)
      if (!entries.length) continue
      lines.push(`### ${scene.title} (\`${scene.id}\`)`, '', scene.state, '')
      for (const entry of entries) {
        const meta = [entry.verdict, entry.severity, ...(entry.tags || [])].filter(Boolean).join(' · ')
        lines.push(`- **${meta}** — @${entry.reviewer || 'anonymous'} · ${formatDate(entry.createdAt)}`)
        const body = entry.text || 'Approved without a note.'
        for (const line of body.split('\n')) lines.push(`  > ${line}`)
        lines.push('')
      }
    }
  }
  const unreviewed = state.manifest.scenes.filter((scene) => !entriesFor(scene.id).length)
  if (unreviewed.length) {
    lines.push('## Not reviewed yet', '')
    for (const scene of unreviewed) lines.push(`- ${groupFor(scene.group).title}: ${scene.title} (\`${scene.id}\`)`)
    lines.push('')
  }
  const text = lines.join('\n')
  download('lpui-ux-feedback.md', text, 'text/markdown')
  toast('Feedback Markdown downloaded.')
}

function importFeedback(file) {
  const reader = new FileReader()
  reader.onload = async () => {
    try {
      const payload = JSON.parse(String(reader.result || '{}'))
      const raw = Array.isArray(payload) ? payload : payload.feedback
      if (!Array.isArray(raw)) throw new Error('no feedback array in this file')
      const known = new Set(state.manifest.scenes.map((scene) => scene.id))
      const incoming = raw
        .map(normalizeEntry)
        .filter((entry) => entry && known.has(entry.scene))
      if (!incoming.length) throw new Error('no usable entries for these screens')
      if (!window.confirm(`Import ${incoming.length} entries and merge them by id?`)) return
      for (const entry of incoming) {
        await persistEntry(entry)
      }
      toast(`Imported ${incoming.length} feedback entries.`)
      renderScene()
    } catch (error) {
      toast(`Import failed: ${error.message}`, 'error')
    }
  }
  reader.readAsText(file)
}

function slug(input, fallback = 'entry', length = 24) {
  const text = String(input || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, length)
  return text || fallback
}

function buildPlan() {
  const entries = actionableEntries()
  if (!entries.length) return null
  const groups = new Map()
  for (const entry of entries) {
    const scene = state.manifest.scenes.find((item) => item.id === entry.scene)
    if (!scene) continue
    if (!groups.has(scene.group)) groups.set(scene.group, [])
    groups.get(scene.group).push({ entry, scene })
  }
  const milestones = []
  let taskNumber = 0
  for (const [groupId, items] of groups) {
    const group = groupFor(groupId)
    const tasks = items.map(({ entry, scene }) => {
      taskNumber += 1
      const verb = entry.verdict === 'idea' ? 'Explore' : entry.verdict === 'question' ? 'Answer' : 'Resolve'
      const summary = truncate(entry.text || `${entry.verdict} on ${scene.title}`, 120)
      const tags = (entry.tags || []).length ? entry.tags.join(', ') : 'none'
      const qualifier = entry.tags?.[0] ? `: ${entry.tags[0]}` : ''
      return {
        key: `ux-${slug(entry.id, `entry-${taskNumber}`)}`,
        title: `${verb} ${scene.title}${qualifier}`,
        desc: [
          `Scene: ${scene.title} (${scene.id}).`,
          `Reviewer: ${entry.reviewer || 'anonymous'} · verdict: ${entry.verdict} · severity: ${entry.severity} · tags: ${tags}.`,
          `Feedback: ${entry.text || 'Approved without a note.'}`,
          'Approach: compare the captured screen with the feedback, then change only the layout, copy, keys, color, or flow the note names.',
          'Commit: one focused change for this screen, with the recaptured image in the same commit when the screen moves.',
          `Verify: recapture ${scene.id} with tools/capture-ux-review.py and confirm the note no longer applies.`
        ].join('\n\n'),
        criteria: [`The ${scene.title} screen resolves the review note: ${summary}`]
      }
    })
    milestones.push({
      key: `ux-${slug(groupId || 'group', 'group')}`,
      title: `Refresh ${group.title.toLowerCase()}`,
      desc: [
        `As a person reviewing lpui, I want the ${group.title.toLowerCase()} screens to address the feedback captured in the review, so that the next pass is intentional rather than piecemeal.`,
        `Scope: ${group.blurb}`,
        'Inputs and prerequisites: the captured screens, the feedback entries below, and a green baseline before each slice.'
      ].join('\n\n'),
      criteria: [`Every ${group.title.toLowerCase()} review entry is resolved or explicitly deferred.`],
      tasks
    })
  }
  return {
    plan: {
      key: 'ux-refresh',
      title: 'UX refresh from the lpui screen review',
      why: `The screen review surfaced ${plural(entries.length, 'actionable entry', 'actionable entries')} across ${plural(milestones.length, 'screen group')}. This plan turns the review into scoped work so every touched screen is refreshed and rechecked instead of drifting.`,
      what: [
        '## Scope',
        '',
        ...milestones.map((milestone) => `- ${milestone.title}: ${milestone.tasks.length} reviewed screen${milestone.tasks.length === 1 ? '' : 's'}.`),
        '',
        '## Out of scope',
        '',
        '- New product capabilities that the review does not name.',
        '- Backend, storage, protocol, and release-automation changes.',
        '',
        '## Commit strategy',
        '',
        '- One screen, or one tight set of related screens, per green commit.',
        '- Keep copy, layout, and tests in reviewable slices when they can stand alone.',
        '- Recapture the changed screens and attach the image update to the same slice.',
        '',
        '## Success metrics',
        '',
        '- Every open concern, idea, and question from this review is resolved or explicitly deferred.',
        '- Every changed screen is recaptured from the deterministic fixture harness.',
        '- The review board reaches zero open actionable entries for this refresh.'
      ].join('\n'),
      criteria: [
        'Every open concern, idea, and question from the screen review is resolved or explicitly deferred.',
        'Every changed screen is recaptured with tools/capture-ux-review.py and reviewed again.',
        'The review board shows no open actionable entries for this refresh.'
      ]
    },
    milestones
  }
}

function renderPlanView() {
  const view = $('#plan-view')
  const review = $('#review-view')
  const scrollY = window.scrollY
  review.hidden = true
  view.hidden = false
  updateHash('plan')
  const doc = buildPlan()
  state.planDoc = doc
  state.planText = doc ? JSON.stringify(doc, null, 2) : ''
  state.planCommand =
    'lpui --actor ux-review --porcelain plan apply --file ux-feedback-plan.json --dry-run\n' +
    'lpui --actor ux-review --porcelain plan apply --file ux-feedback-plan.json'
  const { total, reviewed, concerns, actionable } = progress()
  const head = el(
    'header',
    { class: 'screen-head' },
    el(
      'div',
      {},
      el('p', { class: 'eyebrow' }, 'Plan handoff', el('span', { class: 'sep' }, '/'), el('span', {}, 'ux refresh')),
      el('h1', {}, 'Turn this review into work'),
      el(
        'p',
        { class: 'screen-state' },
        `One milestone per screen group, one task per actionable entry, with acceptance criteria on the plan. Captured from v${state.manifest.version}.`
      )
    ),
    el(
      'div',
      { class: 'head-actions' },
      el('button', { class: 'btn btn-quiet', type: 'button', 'data-action': 'back-to-review' }, 'Back to review'),
      el('button', { class: 'btn btn-quiet', type: 'button', 'data-action': 'export-json' }, 'Export feedback'),
      el('button', { class: 'btn btn-gold', type: 'button', 'data-action': 'download-plan', disabled: doc ? undefined : true }, 'Download plan JSON')
    )
  )

  if (!doc) {
    view.replaceChildren(
      el('article', { class: 'screen' }, head),
      el(
        'div',
        { class: 'empty-big' },
        el(
          'div',
          {},
          el('h1', {}, 'Nothing actionable yet'),
          el(
            'p',
            {},
            `Review ${plural(total - reviewed, 'screen')} still open. The plan appears as soon as a screen has a concern, idea, or question.`
          ),
          el('button', { class: 'btn btn-quiet', type: 'button', 'data-action': 'back-to-review' }, 'Go back to the screens')
        )
      )
    )
    window.scrollTo({ top: 0 })
    return
  }

  const included = actionableEntries().map((entry) => {
    const scene = state.manifest.scenes.find((item) => item.id === entry.scene)
    return el(
      'div',
      { class: 'include-item' },
      el('strong', {}, `${entry.verdict} · ${scene?.title || entry.scene}`),
      el('span', {}, truncate(entry.text || 'Approved without a note.', 120))
    )
  })

  view.replaceChildren(
    el('article', { class: 'screen' }, head),
    el(
      'div',
      { class: 'plan-layout' },
      el(
        'section',
        { class: 'plan-panel' },
        el('h2', {}, 'Generated plan document'),
        el(
          'p',
          {},
          'Download the document and apply it with the command below. Stable keys make the retry a no-op; a failure rolls the whole tree back.'
        ),
        el(
          'div',
          { class: 'plan-actions' },
          el('button', { class: 'btn btn-gold', type: 'button', 'data-action': 'download-plan' }, 'Download plan JSON'),
          el('button', { class: 'btn btn-quiet', type: 'button', 'data-action': 'copy-plan' }, 'Copy JSON'),
          el('button', { class: 'btn btn-quiet', type: 'button', 'data-action': 'copy-command' }, 'Copy apply command'),
          el('button', { class: 'btn btn-quiet', type: 'button', 'data-action': 'copy-brief' }, 'Copy agent brief')
        ),
        preText(state.planCommand),
        el('h3', {}, 'Plan JSON'),
        preText(state.planText),
        el('h3', {}, 'Apply it'),
        el(
          'p',
          {},
          'Write the JSON to ux-feedback-plan.json in the repo, then run the two commands above. The first pass is a dry run; the second writes the tree.'
        )
      ),
      el(
        'aside',
        { class: 'side-stack' },
        el(
          'section',
          { class: 'plan-panel' },
          el('h2', {}, 'Review snapshot'),
          el(
            'div',
            { class: 'stat-row' },
            stat(String(total), 'screens'),
            stat(String(reviewed), 'reviewed'),
            stat(String(concerns), 'concerns')
          ),
          el('p', {}, `${plural(actionable, 'actionable entry', 'actionable entries')} across ${plural(doc.milestones.length, 'screen group')}.`),
          el('h3', {}, 'Included entries'),
          el('div', { class: 'include-list' }, ...included)
        ),
        el(
          'section',
          { class: 'plan-panel' },
          el('h2', {}, 'Handoff'),
          el(
            'p',
            {},
            'The plan keeps the why, what, commit strategy, and acceptance criteria. Each task names the scene, the note, the commit slice, and the verification.'
          ),
          el(
            'div',
            { class: 'plan-actions' },
            el('button', { class: 'btn btn-quiet', type: 'button', 'data-action': 'copy-brief' }, 'Copy agent brief')
          )
        )
      )
    )
  )
  window.scrollTo({ top: scrollY })
}

function preText(text) {
  return el('pre', { class: 'code' }, text)
}

function stat(value, label) {
  return el('div', { class: 'stat' }, el('strong', {}, value), el('span', {}, label))
}

function agentBrief() {
  const doc = state.planDoc || buildPlan()
  if (!doc) return ''
  const actionable = actionableEntries()
  return [
    '# lpui UX refresh handoff',
    '',
    `Apply this plan from the repo root. ${plural(actionable.length, 'actionable review entry', 'actionable review entries')}.`,
    '',
    '1. Save the generated document as ux-feedback-plan.json.',
    '2. Run the dry run, fix any validation error, then apply.',
    '3. Treat the plan as the truth: change the plan before changing the course.',
    '4. Recapture every changed screen with tools/capture-ux-review.py and review it again.',
    '',
    '```bash',
    state.planCommand,
    '```',
    '',
    '## Review entries',
    '',
    ...actionable.map((entry) => {
      const scene = state.manifest.scenes.find((item) => item.id === entry.scene)
      return `- **${scene?.title || entry.scene}** · ${entry.verdict} · ${entry.severity}: ${truncate(entry.text || 'no note', 200)}`
    })
  ].join('\n')
}

async function resetReview() {
  if (!window.confirm('Delete every feedback entry and draft on this device? Exported files are not affected.')) {
    return
  }
  try {
    if (state.backend === 'server') {
      for (const entry of [...state.feedback]) await removeEntry(entry.id)
    }
    state.feedback = []
    state.drafts = {}
    state.editingEntry = null
    state.composer = null
    localStorage.removeItem(FEEDBACK_KEY)
    localStorage.removeItem(DRAFT_KEY)
    toast('Review reset.')
    renderScene()
  } catch (error) {
    toast(error.message || 'Could not reset every entry', 'error')
  }
}

function bindGlobalEvents() {
  document.addEventListener('click', async (event) => {
    const target = event.target.closest('[data-action]')
    if (!target) return
    const action = target.dataset.action
    if (action === 'select-scene') selectScene(target.dataset.scene)
    else if (action === 'zoom') openLightbox()
    else if (action === 'approve-current') approveCurrent()
    else if (action === 'copy-scene-link') {
      copyText(location.href, 'Screen link copied.')
    } else if (action === 'pick-verdict') {
      const scene = currentScene()
      if (!scene) return
      snapshotComposer(scene)
      state.composer.verdict = target.dataset.verdict
      state.drafts[scene.id] = {
        ...(state.drafts[scene.id] || {}),
        verdict: state.composer.verdict,
        savedAt: new Date().toISOString()
      }
      persistDrafts()
      renderScene()
    } else if (action === 'pick-tag') {
      const scene = currentScene()
      if (!scene) return
      snapshotComposer(scene)
      const tag = target.dataset.tag
      const index = state.composer.tags.indexOf(tag)
      if (index >= 0) state.composer.tags.splice(index, 1)
      else state.composer.tags.push(tag)
      state.drafts[scene.id] = {
        ...(state.drafts[scene.id] || {}),
        tags: [...state.composer.tags],
        savedAt: new Date().toISOString()
      }
      persistDrafts()
      renderScene()
    } else if (action === 'clear-composer') {
      delete state.drafts[state.sceneId]
      persistDrafts()
      state.editingEntry = null
      state.composer = null
      renderScene()
    } else if (action === 'edit-entry') startEditEntry(target.dataset.entry)
    else if (action === 'delete-entry') deleteEntry(target.dataset.entry)
    else if (action === 'export-json') exportJson()
    else if (action === 'export-md') exportMarkdown()
    else if (action === 'plan-view') renderPlanView()
    else if (action === 'back-to-review') {
      $('#plan-view').hidden = true
      $('#review-view').hidden = false
      updateHash('scene')
      renderScene()
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } else if (action === 'download-plan') {
      if (!state.planText) state.planText = JSON.stringify(buildPlan(), null, 2)
      download('ux-feedback-plan.json', state.planText + '\n')
      toast('Plan JSON downloaded.')
    } else if (action === 'copy-plan') copyText(state.planText || JSON.stringify(buildPlan(), null, 2), 'Plan JSON copied.')
    else if (action === 'copy-command') copyText(state.planCommand, 'Apply command copied.')
    else if (action === 'copy-brief') copyText(agentBrief(), 'Agent brief copied.')
    else if (action === 'reset') resetReview()
  })

  $('#search').addEventListener('input', (event) => {
    state.filters.q = event.target.value
    renderNav()
  })
  $('#group-filter').addEventListener('change', (event) => {
    state.filters.group = event.target.value
    renderNav()
  })
  document.querySelectorAll('.status-btn').forEach((button) => {
    button.addEventListener('click', () => setFilterStatus(button.dataset.status))
  })
  $('#reviewer').addEventListener('input', (event) => {
    state.reviewer = event.target.value.trim()
    localStorage.setItem(REVIEWER_KEY, state.reviewer)
  })
  $('#help-button').addEventListener('click', () => $('#help-dialog').showModal())
  $('#export-button').addEventListener('click', exportJson)
  $('#export-md-button').addEventListener('click', exportMarkdown)
  $('#plan-button').addEventListener('click', renderPlanView)
  $('#reset-button').addEventListener('click', resetReview)
  $('#import-button').addEventListener('click', () => $('#import-file').click())
  $('#import-file').addEventListener('change', (event) => {
    const file = event.target.files?.[0]
    if (file) importFeedback(file)
    event.target.value = ''
  })

  document.addEventListener('keydown', (event) => {
    const tag = event.target?.tagName?.toLowerCase()
    const typing = ['input', 'textarea', 'select'].includes(tag)
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && tag === 'textarea') {
      event.preventDefault()
      $('#feedback-form')?.requestSubmit()
      return
    }
    if (typing || event.metaKey || event.ctrlKey || event.altKey) return
    if (document.querySelector('dialog[open]')) return
    if (event.key === 'j') {
      event.preventDefault()
      moveScene(1)
    } else if (event.key === 'k') {
      event.preventDefault()
      moveScene(-1)
    } else if (event.key === 'a') {
      event.preventDefault()
      approveCurrent()
    } else if (event.key === '/') {
      event.preventDefault()
      $('#search').focus()
    } else if (event.key === '?') {
      event.preventDefault()
      $('#help-dialog').showModal()
    }
  })

  $('#lightbox').addEventListener('click', (event) => {
    if (event.target === $('#lightbox')) $('#lightbox').close()
  })

  window.addEventListener('hashchange', () => {
    const route = readHash()
    if (route?.mode === 'plan') renderPlanView()
    else if (route?.id) selectScene(route.id, { scroll: false })
  })
}

function openLightbox() {
  const scene = currentScene()
  if (!scene) return
  const image = $('#lightbox-image')
  image.src = `./${scene.image}`
  image.alt = `${scene.title}: ${scene.description}`
  $('#lightbox').showModal()
}

function readHash() {
  const hash = location.hash.replace(/^#/, '')
  if (hash === 'plan') return { mode: 'plan' }
  const match = hash.match(/^scene=([^&]+)$/)
  if (match) return { mode: 'scene', id: decodeURIComponent(match[1]) }
  return null
}

async function loadManifest() {
  const response = await fetch('./scenes.json', { cache: 'no-store' })
  if (!response.ok) throw new Error(`scenes.json returned ${response.status}`)
  return response.json()
}

async function boot() {
  try {
    state.manifest = await loadManifest()
  } catch (error) {
    $('#review-view').replaceChildren(
      el(
        'div',
        { class: 'empty-big' },
        el(
          'div',
          {},
          el('h1', {}, 'Screens are not captured yet'),
          el(
            'p',
            {},
            'Run .venv/bin/python tools/capture-ux-review.py to build site/public/ux/scenes.json and the screenshots, then reload.'
          ),
          el('p', { class: 'keys-line' }, String(error.message || error))
        )
      )
    )
    return
  }
  state.reviewer = localStorage.getItem(REVIEWER_KEY) || ''
  $('#reviewer').value = state.reviewer
  state.drafts = loadDrafts()
  await detectBackend()
  renderStorageChip()
  renderGroupOptions()

  const route = readHash()
  if (route?.mode === 'plan') {
    renderPlanView()
  } else {
    const id = route?.id && state.manifest.scenes.some((scene) => scene.id === route.id)
      ? route.id
      : state.manifest.scenes[0]?.id
    state.sceneId = id || null
    renderScene()
  }
  bindGlobalEvents()
  renderProgress()
}

boot()
