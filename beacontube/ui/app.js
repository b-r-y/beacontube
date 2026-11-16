const ICONS = {
  play: '<path d="M8 5v14l11-7z"/>',
  queue: '<path d="M3 10h11v2H3zm0-4h11v2H3zm0 8h7v2H3zm16-1v-3h-2v3h-3v2h3v3h2v-3h3v-2z"/>',
  remove: '<path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>',
}
const icon = (name) => `<svg viewBox="0 0 24 24">${ICONS[name]}</svg>`
const esc = (text) => String(text ?? '').replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)
const minutes = (seconds) =>
  `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
const host = (url) => {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return ''
  }
}
const when = (seconds) =>
  new Date(seconds * 1000).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })

const form = document.getElementById('form')
const input = document.getElementById('url')
const go = document.getElementById('go')
const results = document.getElementById('results')
const resultsTitle = document.getElementById('results-title')
const resultList = document.getElementById('result-list')
const note = document.getElementById('note')
const banner = document.getElementById('banner')
const recentList = document.getElementById('recent')
const topList = document.getElementById('most-played')

let recent = []
let mostPlayed = []
let busy = false
let answered = null
let searched = 0

// A link plays; anything else is searched for.
const isLink = (text) => /^https?:\/\/\S+$/i.test(text.trim())

function say(text, error = false) {
  note.textContent = text
  note.classList.toggle('error', error)
}

// Beacon answers every beacon.play with beacon.played.
function send(item, mode) {
  return new Promise((resolve) => {
    answered = resolve
    parent.postMessage({ type: 'beacon.play', mode, item }, '*')
    setTimeout(() => {
      if (answered === resolve) {
        answered = null
        resolve({ ok: false, error: 'Beacon did not answer' })
      }
    }, 15000)
  })
}

async function play(url, mode) {
  if (busy) return
  busy = true
  say('Fetching the audio…')
  try {
    const response = await fetch('api/play', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })
    const data = await response.json()
    if (!response.ok) return say(data.error || 'Could not play that link', true)
    const result = await send(data.item, mode)
    if (!result.ok) return say(result.error || 'Beacon could not play that', true)
    say(mode === 'queue' ? `Added ${data.item.title}` : `Playing ${data.item.title}`)
    await load()
  } catch {
    say('Could not reach BeaconTube', true)
  } finally {
    busy = false
  }
}

async function find(query) {
  const asked = ++searched
  say('Searching…')
  results.hidden = false
  resultsTitle.textContent = `Results for “${query}”`
  resultList.innerHTML = '<li class="empty">Searching…</li>'
  let data
  try {
    const response = await fetch(`api/search?q=${encodeURIComponent(query)}`)
    data = await response.json()
    if (asked !== searched) return
    if (!response.ok) {
      resultList.innerHTML = ''
      return say(data.error || 'The search did not work', true)
    }
  } catch {
    if (asked === searched) say('Could not reach BeaconTube', true)
    return
  }
  say('')
  resultList.innerHTML = data.length
    ? data
        .map(
          (result) => `
      <li class="row" data-url="${esc(result.url)}">
        <img class="thumb" src="${esc(result.thumbnail)}" alt="" loading="lazy">
        <div class="meta">
          <div class="title">${esc(result.title)}</div>
          <div class="sub">${esc([result.artist, result.duration && minutes(result.duration)].filter(Boolean).join(' · '))}</div>
        </div>
        <button data-url="${esc(result.url)}" data-mode="now" title="Play">${icon('play')}</button>
        <button data-url="${esc(result.url)}" data-mode="queue" title="Add to queue">${icon('queue')}</button>
      </li>`,
        )
        .join('')
    : '<li class="empty">Nothing found</li>'
}

function closeResults() {
  searched++
  results.hidden = true
  resultList.innerHTML = ''
}

async function forget(list, url) {
  try {
    await fetch(`api/${list}/remove`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    })
  } catch {
    return say('Could not reach BeaconTube', true)
  }
  say('Removed')
  await load()
}

async function fetchJSON(path) {
  try {
    return await (await fetch(path)).json()
  } catch {
    return []
  }
}

async function load() {
  ;[recent, mostPlayed] = await Promise.all([fetchJSON('api/history'), fetchJSON('api/most-played')])
  renderBanner()
  renderList(recentList, recent, (entry) => [
    entry.item.artist,
    host(entry.url),
    entry.item.duration && minutes(entry.item.duration),
  ], (entry) => `Played ${when(entry.playedAt)}`, 'Links you play show up here',
    'history', 'Remove from last played')
  renderList(topList, mostPlayed, (entry) => [
    entry.item.artist,
    host(entry.url),
    entry.item.duration && minutes(entry.item.duration),
  ], (entry) => `${entry.plays} ${entry.plays === 1 ? 'play' : 'plays'}`, 'Links you play often show up here',
    'most-played', 'Remove from most played')
}

// The banner shows the last link played, in the same layout as Beacon's own
// detail headers: its picture behind the text, and its details beside it.
function renderBanner() {
  const latest = recent[0]
  banner.hidden = false
  if (!latest) {
    banner.classList.add('detail-header--text-only')
    banner.innerHTML = `
      <div class="detail-header__content">
        <div class="detail-header__info">
          <div class="detail-header__title">BeaconTube</div>
          <div class="detail-header__subtitle">Search below, or paste a link to play it</div>
        </div>
      </div>`
    return
  }
  const { url, playedAt, cover, item } = latest
  const details = [host(url), item.duration && minutes(item.duration), `Played ${when(playedAt)}`]
  banner.classList.remove('detail-header--text-only')
  banner.innerHTML = `
    <div class="detail-header__backdrop"></div>
    <div class="detail-header__scrim"></div>
    <div class="detail-header__content">
      ${cover ? `<img class="detail-header__cover" src="${esc(cover)}" alt="">` : ''}
      <div class="detail-header__info">
        <div class="detail-header__eyebrow">Last played</div>
        <div class="detail-header__title">${esc(item.title)}</div>
        <div class="detail-header__subtitle">${esc(item.artist)}</div>
        <div class="detail-header__meta">${esc(details.filter(Boolean).join(' · '))}</div>
        <div class="detail-header__actions">
          <button class="pill" data-url="${esc(url)}" data-mode="now">Play</button>
          <button class="pill ghost" data-url="${esc(url)}" data-mode="queue">Add to queue</button>
        </div>
      </div>
    </div>`
  if (cover) {
    banner
      .querySelector('.detail-header__backdrop')
      .style.setProperty('--backdrop-image', `url("${cover}")`)
  }
}

function renderList(element, entries, details, line, empty, list, label) {
  element.innerHTML = entries.length
    ? entries
        .map((entry) => {
          const picture = entry.cover
            ? `<img class="thumb" src="${esc(entry.cover)}" alt="" loading="lazy">`
            : '<div class="thumb"></div>'
          return `
      <li class="row" data-url="${esc(entry.url)}">
        ${picture}
        <div class="meta">
          <div class="title">${esc(entry.item.title)}</div>
          <div class="sub">${esc(details(entry).filter(Boolean).join(' · '))}</div>
          <div class="sub">${esc(line(entry))}</div>
        </div>
        <button data-url="${esc(entry.url)}" data-mode="now" title="Play">${icon('play')}</button>
        <button data-url="${esc(entry.url)}" data-mode="queue" title="Add to queue">${icon('queue')}</button>
        <button data-remove="${list}" data-url="${esc(entry.url)}" title="${label}">${icon('remove')}</button>
      </li>`
        })
        .join('')
    : `<li class="empty">${empty}</li>`
}

function submit(text) {
  text = text.trim()
  if (!text) return
  if (isLink(text)) play(text, 'now')
  else find(text)
}

form.addEventListener('submit', (event) => {
  event.preventDefault()
  submit(input.value)
})

// The button says what Enter will do.
input.addEventListener('input', () => {
  go.textContent = isLink(input.value) ? 'Play' : 'Search'
})
input.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeResults()
})
document.getElementById('close-results').addEventListener('click', closeResults)

// A pasted link plays straight away, in the field or anywhere on the page.
// Pasted words land in the field, to be searched for with Enter.
addEventListener('paste', (event) => {
  const text = event.clipboardData?.getData('text') ?? ''
  if (isLink(text)) {
    event.preventDefault()
    input.value = text.trim()
    go.textContent = 'Play'
    play(input.value, 'now')
  } else if (event.target !== input && text.trim()) {
    event.preventDefault()
    input.value = text.trim()
    go.textContent = 'Search'
    input.focus()
  }
})

// A row plays its link; its buttons say how (now or queued) or remove it.
function onPlayClick(event) {
  const removing = event.target.closest('button[data-remove]')
  if (removing) return forget(removing.dataset.remove, removing.dataset.url)
  const target = event.target.closest('[data-url]')
  if (!target) return
  const button = event.target.closest('button[data-url]')
  play(target.dataset.url, button?.dataset.mode ?? 'now')
}
resultList.addEventListener('click', onPlayClick)
recentList.addEventListener('click', onPlayClick)
topList.addEventListener('click', onPlayClick)
banner.addEventListener('click', onPlayClick)

addEventListener('message', (event) => {
  if (event.source !== parent) return
  const message = event.data
  if (message.type === 'beacon.played') {
    answered?.(message)
    answered = null
  } else if (message.type === 'beacon.theme') {
    const c = message.colors
    const s = document.documentElement.style
    s.setProperty('--bg', c.background)
    s.setProperty('--fg', c['on-background'])
    s.setProperty('--surface', c.surface)
    s.setProperty('--primary', c.primary)
    s.setProperty('--on-primary', c['on-primary'])
    s.colorScheme = message.dark ? 'dark' : 'light'
  }
})

document.getElementById('standalone').hidden = parent !== window
load()
parent.postMessage({ type: 'beacon.ready' }, '*')
