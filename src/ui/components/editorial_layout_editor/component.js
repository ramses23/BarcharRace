const instances = new WeakMap()
const clone = value => JSON.parse(JSON.stringify(value))
const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value))
const handles = ["n", "s", "e", "w", "ne", "nw", "se", "sw"]

function createInstanceId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

function buildInstance(parentElement) {
  const root = document.createElement("div")
  const toolbar = document.createElement("div")
  toolbar.className = "editorial-toolbar"
  const status = document.createElement("span")
  status.className = "editorial-status"
  toolbar.appendChild(status)
  const wrap = document.createElement("div")
  wrap.className = "editorial-stage-wrap"
  const stage = document.createElement("div")
  stage.className = "editorial-stage"
  wrap.appendChild(stage)
  const hint = document.createElement("div")
  hint.className = "editorial-hint"
  hint.textContent = "Drag the card or its 8 handles. Arrow keys move 1 px; Shift + arrows move 10 px. Changes are applied when the gesture ends."
  root.append(toolbar, wrap, hint)
  parentElement.appendChild(root)
  return {
    root, status, stage, data: null, rect: null, scale: 1, drag: null,
    incoming: null, instanceId: createInstanceId(), eventCounter: 0,
    setStateValue: null, resizeObserver: null,
  }
}

function stageDimensions(state) {
  const canvasWidth = Number(state.data.canvas_width)
  const canvasHeight = Number(state.data.canvas_height)
  const availableWidth = Math.max(280, state.root.clientWidth || 720)
  const maxHeight = 520
  const width = Math.min(availableWidth, maxHeight * canvasWidth / canvasHeight)
  return { width, height: width * canvasHeight / canvasWidth }
}

function normalized(state, rect) {
  const minWidth = Number(state.data.min_width)
  const minHeight = Number(state.data.min_height)
  const canvasWidth = Number(state.data.canvas_width)
  const canvasHeight = Number(state.data.canvas_height)
  const width = clamp(Math.round(rect.width), minWidth, canvasWidth)
  const height = clamp(Math.round(rect.height), minHeight, canvasHeight)
  return {
    x: Math.round(clamp(rect.x, 0, canvasWidth - width)),
    y: Math.round(clamp(rect.y, 0, canvasHeight - height)),
    width, height,
  }
}

function addOverlay(state, rect, className) {
  if (!rect || Number(rect.width) <= 0 || Number(rect.height) <= 0) return
  const node = document.createElement("div")
  node.className = `overlay-rect ${className}`
  node.style.left = `${Number(rect.x) * state.scale}px`
  node.style.top = `${Number(rect.y) * state.scale}px`
  node.style.width = `${Number(rect.width) * state.scale}px`
  node.style.height = `${Number(rect.height) * state.scale}px`
  state.stage.appendChild(node)
}

function updateStatus(state) {
  const r = state.rect
  state.status.textContent = `Card: X ${r.x} · Y ${r.y} · ${r.width} × ${r.height} px`
}

function positionCard(state, card) {
  const r = state.rect
  card.style.left = `${r.x * state.scale}px`
  card.style.top = `${r.y * state.scale}px`
  card.style.width = `${r.width * state.scale}px`
  card.style.height = `${r.height * state.scale}px`
  updateStatus(state)
}

function render(state) {
  if (!state.data || !state.rect) return
  const dimensions = stageDimensions(state)
  state.scale = dimensions.width / Number(state.data.canvas_width)
  state.stage.style.width = `${dimensions.width}px`
  state.stage.style.height = `${dimensions.height}px`
  state.stage.style.setProperty("--canvas-background", state.data.theme?.background_color || "#111827")
  state.stage.replaceChildren()
  const overlay = state.data.overlay || {}
  for (const bar of overlay.bar_rects || []) addOverlay(state, bar, "overlay-bar")
  for (const rect of Object.values(overlay.text_bounds || {})) addOverlay(state, rect, "overlay-text")
  const card = document.createElement("div")
  card.className = "editorial-card-editor"
  const cardTheme = state.data.theme || {}
  card.dataset.backgroundMode = cardTheme.card_background_mode || "card"
  card.dataset.texture = cardTheme.card_background_texture || "none"
  card.style.setProperty("--card-background", cardTheme.card_background_color || "#111827")
  card.style.setProperty(
    "--card-texture-opacity",
    clamp(Number(cardTheme.card_background_texture_intensity) || 0, 0, 1),
  )
  card.tabIndex = 0
  card.setAttribute("role", "group")
  card.setAttribute("aria-label", "Editorial card. Drag to move; use handles to resize.")
  const label = document.createElement("span")
  label.className = "editorial-card-label"
  label.textContent = "Editorial card"
  card.appendChild(label)
  for (const direction of handles) {
    const handle = document.createElement("span")
    handle.className = `resize-handle handle-${direction}`
    handle.dataset.handle = direction
    handle.setAttribute("role", "button")
    handle.setAttribute("aria-label", `Resize editorial card ${direction}`)
    card.appendChild(handle)
  }
  card.onpointerdown = event => startDrag(state, card, event)
  card.onkeydown = event => keyboardMove(state, card, event)
  positionCard(state, card)
  state.stage.appendChild(card)
  state.card = card
}

function startDrag(state, card, event) {
  const handle = event.target?.dataset?.handle || "move"
  card.setPointerCapture(event.pointerId)
  state.drag = {
    mode: handle,
    pointerId: event.pointerId,
    startX: event.clientX,
    startY: event.clientY,
    rect: clone(state.rect),
    baseRect: clone(state.rect),
  }
  card.onpointermove = moveEvent => moveDrag(state, card, moveEvent)
  card.onpointerup = endEvent => endDrag(state, card, endEvent)
  card.onpointercancel = endEvent => endDrag(state, card, endEvent)
  card.onlostpointercapture = endEvent => endDrag(state, card, endEvent)
  event.preventDefault()
}

function moveDrag(state, card, event) {
  if (!state.drag || event.pointerId !== state.drag.pointerId) return
  const dx = (event.clientX - state.drag.startX) / state.scale
  const dy = (event.clientY - state.drag.startY) / state.scale
  const start = state.drag.rect
  const mode = state.drag.mode
  let left = start.x
  let top = start.y
  let right = start.x + start.width
  let bottom = start.y + start.height
  if (mode === "move") { left += dx; right += dx; top += dy; bottom += dy }
  else {
    if (mode.includes("w")) left += dx
    if (mode.includes("e")) right += dx
    if (mode.includes("n")) top += dy
    if (mode.includes("s")) bottom += dy
    const minWidth = Number(state.data.min_width)
    const minHeight = Number(state.data.min_height)
    if (right - left < minWidth) mode.includes("w") ? left = right - minWidth : right = left + minWidth
    if (bottom - top < minHeight) mode.includes("n") ? top = bottom - minHeight : bottom = top + minHeight
  }
  state.rect = normalized(state, { x: left, y: top, width: right - left, height: bottom - top })
  positionCard(state, card)
}

function emit(state, baseRect) {
  state.eventCounter += 1
  state.setStateValue("geometry", {
    rect: clone(state.rect),
    base_rect: clone(baseRect),
    event_id: `${state.instanceId}:${state.eventCounter}`,
  })
}

function endDrag(state, card) {
  if (!state.drag) return
  const baseRect = clone(state.drag.baseRect)
  state.drag = null
  card.onpointermove = null
  card.onpointerup = null
  card.onpointercancel = null
  card.onlostpointercapture = null
  emit(state, baseRect)
}

function keyboardMove(state, card, event) {
  if (!event.key.startsWith("Arrow")) return
  const distance = event.shiftKey ? 10 : 1
  const baseRect = clone(state.rect)
  const next = clone(state.rect)
  if (event.key === "ArrowLeft") next.x -= distance
  if (event.key === "ArrowRight") next.x += distance
  if (event.key === "ArrowUp") next.y -= distance
  if (event.key === "ArrowDown") next.y += distance
  state.rect = normalized(state, next)
  positionCard(state, card)
  emit(state, baseRect)
  event.preventDefault()
}

export default function (component) {
  const { data, parentElement, setStateValue } = component
  let state = instances.get(parentElement)
  if (!state) {
    state = buildInstance(parentElement)
    instances.set(parentElement, state)
    state.resizeObserver = new ResizeObserver(() => {
      if (state.data && !state.drag) render(state)
    })
    state.resizeObserver.observe(state.root)
    state.cleanup = () => {
      state.resizeObserver?.disconnect()
      state.root.remove()
      instances.delete(parentElement)
    }
  }
  state.setStateValue = setStateValue
  if (state.drag) return state.cleanup
  state.data = data
  const incoming = JSON.stringify(data.rect)
  if (!state.drag && (state.incoming === null || incoming !== state.incoming)) state.rect = normalized(state, data.rect)
  state.incoming = incoming
  render(state)
  return state.cleanup
}
