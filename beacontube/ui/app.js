const ICONS = {
  play: '<path d="M8 5v14l11-7z"/>',
  next: '<path d="M3 10h11v2H3zm0-4h11v2H3zm0 8h7v2H3zm13-1v8l6-4z"/>',
  queue: '<path d="M3 10h11v2H3zm0-4h11v2H3zm0 8h7v2H3zm16-1v-3h-2v3h-3v2h3v3h2v-3h3v-2z"/>',
  remove:
    '<path d="M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>',
  history:
    '<path d="M13 3a9 9 0 0 0-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42A8.95 8.95 0 0 0 13 21a9 9 0 0 0 0-18m-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8z"/>',
  chart: '<path d="M5 9.2h3V19H5zM10.6 5h2.8v14h-2.8zm5.6 8H19v6h-2.8z"/>',
  home: '<path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/>',
  library:
    '<path d="M4 6H2v14c0 1.1.9 2 2 2h14v-2H4zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2m-1 9h-4v4h-2v-4H9V9h4V5h2v4h4z"/>',
  cloud:
    '<path d="M19.35 10.04A7.49 7.49 0 0 0 12 4C9.11 4 6.6 5.64 5.35 8.04A5.99 5.99 0 0 0 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96M17 13l-5 5-5-5h3V9h4v4z"/>',
  channel: '<path d="M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8m0 10c4.42 0 8 1.79 8 4v2H4v-2c0-2.21 3.58-4 8-4"/>',
  search:
    '<path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14"/>',
}
const icon = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`
const BARS = '<span class="bars" aria-label="Playing"><i></i><i></i><i></i></span>'
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
const when = (seconds) => {
  const ago = Date.now() / 1000 - seconds
  if (ago < 60) return 'just now'
  if (ago < 3600) return `${Math.floor(ago / 60)} min ago`
  if (ago < 86400) return `${Math.floor(ago / 3600)} h ago`
  return new Date(seconds * 1000).toLocaleDateString([], { dateStyle: 'medium' })
}
const joined = (...parts) => parts.filter(Boolean).join(' · ')
// A link plays; anything else is searched for.
const isLink = (text) => /^https?:\/\/\S+$/i.test(text.trim())

const $ = (id) => document.getElementById(id)
const hero = $('hero')
const form = $('form')
const input = $('query')
const go = $('go')
const results = $('results')
const resultsTitle = $('results-title')
const resultList = $('result-list')
const recentList = $('recent')
const topList = $('most-played')
const channelList = $('channels')
const homeView = $('home-view')
const libraryView = $('library-view')
const libraryList = $('library-list')
const libraryCount = $('library-count')
const libraryFilter = $('library-filter')
const librarySort = $('library-sort')
const toastBox = $('toast')

let recent = []
let mostPlayed = []
let found = []
// Every link ever played, from the app; the channels are counted from it.
let library = []
let view = 'home'
// The link being fetched: yt-dlp downloads one at a time, so one is enough.
let pending = null
// What Beacon says is playing: {title, artist, album} or null.
let nowPlaying = null
let answered = null
let searched = 0

// --- talking to Beacon and to the app -----------------------------------------

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

async function post(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return { response, data: await response.json() }
}

async function fetchJSON(path) {
  try {
    return await (await fetch(path)).json()
  } catch {
    return []
  }
}

const DONE = { now: 'Playing', next: 'Plays next:', queue: 'Added to the queue:' }

async function play(url, mode, title) {
  if (pending) return toast(`Still fetching ${pending.title || 'the last link'}…`)
  pending = { url, title }
  renderAll()
  toast(title ? `Fetching ${title}…` : 'Fetching the audio…', { stay: true })
  try {
    const { response, data } = await post('api/play', { url })
    if (!response.ok) return toast(data.error || 'Could not play that link', { error: true })
    const result = await send(data.item, mode)
    if (!result.ok) return toast(result.error || 'Beacon could not play that', { error: true })
    toast(`${DONE[mode]} ${data.item.title}`)
  } catch {
    toast('Could not reach BeaconTube', { error: true })
  } finally {
    pending = null
    await load()
  }
}

async function forget(list, url) {
  try {
    await post(`api/${list}/remove`, { url })
  } catch {
    return toast('Could not reach BeaconTube', { error: true })
  }
  await load()
}

async function load() {
  ;[recent, mostPlayed, library] = await Promise.all([
    fetchJSON('api/history'),
    fetchJSON('api/most-played'),
    fetchJSON('api/library'),
  ])
  renderAll()
}

// --- the two views ---------------------------------------------------------------

function show(next, { sort, filter } = {}) {
  view = next
  if (sort) librarySort.value = sort
  if (filter !== undefined) libraryFilter.value = filter
  homeView.hidden = next !== 'home'
  libraryView.hidden = next !== 'library'
  for (const tab of document.querySelectorAll('[data-view]')) {
    const active = tab.dataset.view === next
    tab.classList.toggle('is-active', active)
    tab.setAttribute('aria-selected', String(active))
  }
  renderLibrary()
  // The hero stays on both tabs, so nothing above the lists moves. Only when
  // the search bar is already stuck to the top does the new tab start right
  // under it, rather than somewhere down the old tab's length.
  const stuckAt =
    hero.offsetTop + hero.offsetHeight + parseFloat(getComputedStyle(hero).marginBottom)
  if (scrollY > stuckAt) scrollTo({ top: stuckAt })
}

async function find(query) {
  const asked = ++searched
  results.hidden = false
  resultsTitle.textContent = `Results for “${query}”`
  found = null
  renderResults()
  try {
    const response = await fetch(`api/search?q=${encodeURIComponent(query)}`)
    const data = await response.json()
    if (asked !== searched) return
    if (!response.ok) {
      found = []
      renderResults()
      return toast(data.error || 'The search did not work', { error: true })
    }
    found = data
  } catch {
    if (asked !== searched) return
    found = []
    toast('Could not reach BeaconTube', { error: true })
  }
  renderResults()
}

function closeResults() {
  searched++
  results.hidden = true
  found = []
}

// --- drawing ---------------------------------------------------------------------

// Beacon names what it plays by title and artist; that is all there is to
// tell its song apart from the others here.
const isPlaying = (item) =>
  nowPlaying && nowPlaying.title === item.title && (nowPlaying.artist || '') === (item.artist || '')
const isPending = (url) => pending?.url === url

function stateClass(url, item) {
  if (isPending(url)) return 'is-pending'
  return item && isPlaying(item) ? 'is-playing' : ''
}

function actions(url, title, { remove, play = true } = {}) {
  const attrs = `data-url="${esc(url)}" data-title="${esc(title)}"`
  return `
    ${play ? `<button class="icon-btn" ${attrs} data-mode="now" title="Play">${icon('play')}</button>` : ''}
    <button class="icon-btn" ${attrs} data-mode="next" title="Play next">${icon('next')}</button>
    <button class="icon-btn" ${attrs} data-mode="queue" title="Add to queue">${icon('queue')}</button>
    ${remove ? `<button class="icon-btn" data-remove="${remove.list}" data-url="${esc(url)}" title="${remove.label}">${icon('remove')}</button>` : ''}`
}

function picture(src, className) {
  return src
    ? `<img class="${className}" src="${esc(src)}" alt="" loading="lazy">`
    : `<div class="${className} ${className}--empty">${icon('play')}</div>`
}

// The hero shows the song Beacon is playing when it came from here, the last
// one played otherwise: its picture blurred behind it, as Beacon's own does.
function renderHero() {
  const playing = recent.find((entry) => isPlaying(entry.item))
  const shown = playing || recent[0]
  if (!shown) {
    hero.className = 'hero hero--empty'
    hero.innerHTML = `
      <div class="hero__content">
        <div class="hero__info">
          <div class="eyebrow">BeaconTube</div>
          <h1 class="display-title">Play anything with a link</h1>
          <p class="hero__sub">Search YouTube below, or paste a link anywhere on this page.</p>
        </div>
      </div>`
    return
  }
  const { url, playedAt, cover, item } = shown
  hero.className = `hero ${stateClass(url, item)}`
  hero.innerHTML = `
    <div class="hero__backdrop"></div>
    <div class="hero__scrim"></div>
    <div class="hero__content">
      ${cover ? `<img class="hero__cover" src="${esc(cover)}" alt="">` : ''}
      <div class="hero__info">
        <div class="eyebrow">${playing ? `${BARS} Now playing` : 'Last played'}</div>
        <h1 class="display-title" title="${esc(item.title)}">${esc(item.title)}</h1>
        <p class="hero__sub">${esc(joined(item.artist, host(url), item.duration && minutes(item.duration), !playing && when(playedAt)))}</p>
        <div class="hero__actions">
          <button class="pill" data-url="${esc(url)}" data-title="${esc(item.title)}" data-mode="now">${icon('play')} Play</button>
          <button class="pill tonal" data-url="${esc(url)}" data-title="${esc(item.title)}" data-mode="next">${icon('next')} Play next</button>
          <button class="pill tonal" data-url="${esc(url)}" data-title="${esc(item.title)}" data-mode="queue">${icon('queue')} Add to queue</button>
        </div>
      </div>
    </div>`
  if (cover) hero.querySelector('.hero__backdrop').style.backgroundImage = `url("${cover}")`
}

function empty(iconName, title, line) {
  return `<li class="empty"><span class="empty__ring">${icon(iconName)}</span>
    <div><div class="empty__title">${title}</div><div class="empty__line">${line}</div></div></li>`
}

// Like Beacon's Home: the recently played as tiles, the whole tile plays.
function renderRecent() {
  recentList.innerHTML = recent.length
    ? recent
        .map(({ url, cover, playedAt, item }) => {
          const playing = isPlaying(item)
          return `
      <li class="tile ${stateClass(url, item)}" data-url="${esc(url)}" data-title="${esc(item.title)}" data-mode="now" title="${esc(item.title)}">
        <div class="tile__art">${picture(cover, 'tile__img')}<span class="tile__mark">${playing ? BARS : icon('play')}</span></div>
        <div class="tile__text">
          <div class="tile__title">${esc(item.title)}</div>
          <div class="tile__sub">${esc(joined(item.artist, when(playedAt)))}</div>
        </div>
        <!-- The whole tile plays; these say how else. -->
        <div class="tile__actions">${actions(url, item.title, { play: false, remove: { list: 'history', label: 'Remove from recently played' } })}</div>
      </li>`
        })
        .join('')
    : empty('history', 'Nothing played yet', 'What you play from here shows up here.')
}

// Beacon's most played songs: a rank, the song, its plays, down one column
// and on into the next.
function renderTop() {
  topList.innerHTML = mostPlayed.length
    ? mostPlayed
        .map(({ url, cover, plays, item }, index) => {
          const playing = isPlaying(item)
          return `
      <li class="song ${stateClass(url, item)}" data-url="${esc(url)}" data-title="${esc(item.title)}" data-mode="now">
        <span class="song__rank">${playing ? BARS : index + 1}</span>
        ${picture(cover, 'song__img')}
        <div class="song__text">
          <div class="song__title">${esc(item.title)}</div>
          <div class="song__sub">${esc(joined(item.artist, item.duration && minutes(item.duration)))}</div>
        </div>
        <span class="song__plays">${plays} ${plays === 1 ? 'play' : 'plays'}</span>
        <div class="song__actions">${actions(url, item.title, { remove: { list: 'most-played', label: 'Remove from most played and the library' } })}</div>
      </li>`
        })
        .join('')
    : empty('chart', 'No favourites yet', 'Songs you play again and again rise to the top here.')
}

function renderResults() {
  if (results.hidden) return
  if (found === null) {
    resultList.innerHTML = Array.from(
      { length: 8 },
      () => `<li class="card card--skeleton" aria-hidden="true"><div class="card__art"></div>
        <div class="card__text"><div class="skeleton-line"></div><div class="skeleton-line short"></div></div></li>`,
    ).join('')
    return
  }
  resultList.innerHTML = found.length
    ? found
        .map(
          (result) => `
      <li class="card ${stateClass(result.url, result)}" data-url="${esc(result.url)}" data-title="${esc(result.title)}" data-mode="now">
        <div class="card__art">
          <img src="${esc(result.thumbnail)}" alt="" loading="lazy">
          ${result.duration ? `<span class="card__time">${minutes(result.duration)}</span>` : ''}
          <span class="card__mark">${isPlaying(result) ? BARS : icon('play')}</span>
        </div>
        <div class="card__text">
          <div class="card__title" title="${esc(result.title)}">${esc(result.title)}</div>
          <div class="card__sub">${esc(result.artist)}</div>
        </div>
        <div class="card__actions">${actions(result.url, result.title)}</div>
      </li>`,
        )
        .join('')
    : empty('search', 'Nothing found', 'Try other words, or paste the link itself.')
}

// The channels most listened to, counted over the whole library: their
// plays together, their songs, and the picture of the one played most.
function channels() {
  const byName = new Map()
  for (const entry of library) {
    const name = entry.item.artist
    if (!name) continue
    const channel = byName.get(name) ?? { name, plays: 0, songs: 0, cover: null, best: -1 }
    channel.plays += entry.plays || 0
    channel.songs += 1
    if ((entry.plays || 0) > channel.best) {
      channel.best = entry.plays || 0
      channel.cover = entry.cover
    }
    byName.set(name, channel)
  }
  return [...byName.values()]
    .sort((a, b) => b.plays - a.plays || a.name.localeCompare(b.name))
    .slice(0, 10)
}

function renderChannels() {
  const top = channels()
  const most = top[0]?.plays || 1
  channelList.innerHTML = top.length
    ? top
        .map(
          (channel, index) => `
      <li class="channel" data-channel="${esc(channel.name)}" title="Show ${esc(channel.name)} in the library">
        <span class="song__rank">${index + 1}</span>
        ${channel.cover ? `<img class="channel__img" src="${esc(channel.cover)}" alt="" loading="lazy">` : `<span class="channel__img channel__img--empty">${icon('channel')}</span>`}
        <div class="channel__text">
          <div class="song__title">${esc(channel.name)}</div>
          <div class="channel__meter"><span style="width:${Math.max(4, (channel.plays / most) * 100)}%"></span></div>
        </div>
        <span class="song__plays">${channel.plays} ${channel.plays === 1 ? 'play' : 'plays'}</span>
        <div class="song__actions">
          <button class="icon-btn" data-search="${esc(channel.name)}" title="Search YouTube for ${esc(channel.name)}">${icon('search')}</button>
        </div>
      </li>`,
        )
        .join('')
    : empty('channel', 'No channels yet', 'The channels you listen to most line up here.')
}

const SORTS = {
  recent: (a, b) => b.playedAt - a.playedAt,
  plays: (a, b) => (b.plays || 0) - (a.plays || 0) || b.playedAt - a.playedAt,
  title: (a, b) => a.item.title.localeCompare(b.item.title),
  channel: (a, b) =>
    (a.item.artist || '').localeCompare(b.item.artist || '') ||
    a.item.title.localeCompare(b.item.title),
}

function renderLibrary() {
  $('library-tab-count').textContent = library.length || ''
  if (view !== 'library') return
  const words = libraryFilter.value.toLowerCase().split(/\s+/).filter(Boolean)
  const shown = library
    .filter((entry) => {
      const text = `${entry.item.title} ${entry.item.artist}`.toLowerCase()
      return words.every((word) => text.includes(word))
    })
    .sort(SORTS[librarySort.value])
  libraryCount.textContent =
    shown.length === library.length
      ? `${library.length} ${library.length === 1 ? 'song' : 'songs'}`
      : `${shown.length} of ${library.length}`
  if (!library.length) {
    libraryList.innerHTML = empty('library', 'Your library is empty', 'Every link you play is kept here, however long ago.')
    return
  }
  if (!shown.length) {
    libraryList.innerHTML = empty('search', 'Nothing matches', 'Try fewer words, or search YouTube above.')
    return
  }
  libraryList.innerHTML = shown
    .map(({ url, cover, plays, playedAt, cached, item }) => {
      const playing = isPlaying(item)
      return `
      <li class="entry ${stateClass(url, item)}" data-url="${esc(url)}" data-title="${esc(item.title)}" data-mode="now">
        <div class="entry__art">${picture(cover, 'entry__img')}<span class="tile__mark">${playing ? BARS : icon('play')}</span></div>
        <div class="entry__text">
          <div class="song__title">${esc(item.title)}${cached ? '' : `<span class="entry__fetch" title="Its audio was cleaned up; it downloads again when played">${icon('cloud')}</span>`}</div>
          <div class="song__sub">${esc(joined(item.artist, item.duration && minutes(item.duration)))}</div>
        </div>
        <span class="entry__when">${esc(when(playedAt))}</span>
        <span class="entry__plays">${plays} ${plays === 1 ? 'play' : 'plays'}</span>
        <div class="entry__actions">${actions(url, item.title, { remove: { list: 'most-played', label: 'Remove from the library' } })}</div>
      </li>`
    })
    .join('')
}

function renderAll() {
  renderHero()
  renderRecent()
  renderTop()
  renderChannels()
  renderLibrary()
  renderResults()
}

let toastTimer = null
function toast(text, { error = false, stay = false } = {}) {
  toastBox.textContent = text
  toastBox.classList.toggle('error', error)
  toastBox.classList.add('show')
  clearTimeout(toastTimer)
  if (!stay) toastTimer = setTimeout(() => toastBox.classList.remove('show'), error ? 4000 : 2400)
}

// --- input -----------------------------------------------------------------------

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
const label = () => (go.textContent = isLink(input.value) ? 'Play' : 'Search')
input.addEventListener('input', label)
input.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    closeResults()
    input.blur()
  }
})
$('close-results').addEventListener('click', closeResults)
libraryFilter.addEventListener('input', renderLibrary)
librarySort.addEventListener('change', renderLibrary)
libraryFilter.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    libraryFilter.value = ''
    renderLibrary()
  }
})

// "/" jumps to the search from anywhere, as on many sites.
addEventListener('keydown', (event) => {
  const typing = event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement
  if (event.key === '/' && !typing && !event.ctrlKey && !event.metaKey) {
    event.preventDefault()
    input.focus()
    input.select()
  }
})

// A pasted link plays straight away, in the field or anywhere on the page.
// Pasted words land in the field, to be searched for with Enter.
addEventListener('paste', (event) => {
  const text = event.clipboardData?.getData('text') ?? ''
  if (isLink(text)) {
    event.preventDefault()
    input.value = text.trim()
    label()
    play(input.value, 'now')
  } else if (event.target !== input && text.trim()) {
    event.preventDefault()
    input.value = text.trim()
    label()
    input.focus()
  }
})

// One handler for every list: a button says how to play (or removes), and
// anywhere else on a row, tile or card plays it now.
document.addEventListener('click', (event) => {
  const tab = event.target.closest('[data-view]')
  if (tab) return show(tab.dataset.view, { sort: tab.dataset.sort })
  const searching = event.target.closest('[data-search]')
  if (searching) {
    input.value = searching.dataset.search
    label()
    return find(searching.dataset.search)
  }
  const channel = event.target.closest('[data-channel]')
  if (channel) return show('library', { sort: 'plays', filter: channel.dataset.channel })
  const removing = event.target.closest('[data-remove]')
  if (removing) return forget(removing.dataset.remove, removing.dataset.url)
  const target = event.target.closest('[data-url][data-mode]')
  if (!target) return
  play(target.dataset.url, target.dataset.mode, target.dataset.title)
})

addEventListener('message', (event) => {
  if (event.source !== parent) return
  const message = event.data
  if (message.type === 'beacon.played') {
    answered?.(message)
    answered = null
  } else if (message.type === 'beacon.nowPlaying') {
    nowPlaying = message.item
    renderAll()
  } else if (message.type === 'beacon.theme') {
    const c = message.colors
    const s = document.documentElement.style
    s.setProperty('--bg', c.background)
    s.setProperty('--fg', c['on-background'])
    s.setProperty('--surface', c.surface)
    s.setProperty('--primary', c.primary)
    s.setProperty('--on-primary', c['on-primary'])
    if (c.error) s.setProperty('--error', c.error)
    s.colorScheme = message.dark ? 'dark' : 'light'
    document.documentElement.classList.toggle('light', !message.dark)
  }
})

$('standalone').hidden = parent !== window
// Relative times ("5 min ago") stay right while the tab is open.
setInterval(() => {
  renderHero()
  renderRecent()
}, 60000)
load()
parent.postMessage({ type: 'beacon.ready' }, '*')
