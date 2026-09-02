const instances = new WeakMap()
const elementNames = ["title", "subtitle", "date", "source"]
const clone = value => JSON.parse(JSON.stringify(value))
const clamp = (value, minimum, maximum) => Math.min(maximum, Math.max(minimum, value))

function buildInstance(parentElement) {
  const root = document.createElement("div")
  const toolbar = document.createElement("div")
  toolbar.className = "layout-toolbar"
  for (const [action, label] of [["left", "Align left"], ["center", "Center X"], ["right", "Align right"], ["reset", "Reset preset"]]) {
    const button = document.createElement("button")
    button.type = "button"
    button.dataset.action = action
    button.textContent = label
    toolbar.appendChild(button)
  }
  const status = document.createElement("span")
  status.className = "layout-status"
  toolbar.appendChild(status)
  const wrap = document.createElement("div")
  wrap.className = "layout-stage-wrap"
  const stage = document.createElement("div")
  stage.className = "layout-stage"
  stage.tabIndex = 0
  stage.setAttribute("aria-label", "Canvas text placement editor")
  wrap.appendChild(stage)
  const hint = document.createElement("div")
  hint.className = "layout-hint"
  hint.textContent = "Drag text directly. Arrow keys move 1 px; Shift + arrows move 10 px. Dashed overlays come from the selected rendered frame."
  root.append(toolbar, wrap, hint)
  parentElement.appendChild(root)
  return { root, toolbar, status, stage, active: "title", positions: null, data: null, scale: 1, drag: null, incoming: null }
}

function stageDimensions(state) {
  const canvasWidth = Number(state.data.canvas_width)
  const canvasHeight = Number(state.data.canvas_height)
  const availableWidth = Math.max(280, state.root.clientWidth || 720)
  const maxHeight = 520
  const width = Math.min(availableWidth, maxHeight * canvasWidth / canvasHeight)
  return { width, height: width * canvasHeight / canvasWidth }
}

function anchor(name) { return name === "date" ? "right" : "left" }
function isManaged(state, name) { return Boolean(state.data.elements?.[name]?.managed) }
function displayPosition(state, name) {
  const effective = state.data.geometry?.effective_positions?.[name]
  return isManaged(state, name) && effective ? effective : state.positions[name]
}

function positionNode(state, node, name) {
  const position = displayPosition(state, name)
  const definition = state.data.elements[name]
  const pixels = Number(definition.font_size) * Number(state.data.dpi) / 72
  node.style.left = `${position.x * state.scale}px`
  node.style.top = `${position.y * state.scale}px`
  node.style.fontFamily = definition.font_family || state.data.theme.font_family || "sans-serif"
  node.style.fontSize = `${Math.max(7, pixels * state.scale)}px`
  node.style.fontWeight = definition.font_weight || "normal"
  node.style.color = definition.color
  node.style.opacity = definition.opacity ?? 1
  node.style.transform = anchor(name) === "right" ? "translate(-100%, -50%)" : "translate(0, -50%)"
  node.classList.toggle("active", name === state.active)
  node.classList.toggle("managed", isManaged(state, name))
  node.setAttribute("aria-label", `${definition.label || name}${isManaged(state, name) ? ", managed by editorial layout" : ""}`)
}

function updateStatus(state) {
  const position = displayPosition(state, state.active)
  const label = state.data?.elements?.[state.active]?.label || state.active
  const suffix = isManaged(state, state.active) ? " · managed by editorial layout" : ""
  state.status.textContent = position ? `${label}: X ${position.x} · Y ${position.y}${suffix}` : "Select an element"
}

function emit(state) { state.setStateValue("positions", clone(state.positions)) }

function addRect(state, rect, className, label) {
  if (!rect || Number(rect.width) <= 0 || Number(rect.height) <= 0) return
  const node = document.createElement("div")
  node.className = `geometry-rect ${className}`
  node.style.left = `${Number(rect.x) * state.scale}px`
  node.style.top = `${Number(rect.y) * state.scale}px`
  node.style.width = `${Number(rect.width) * state.scale}px`
  node.style.height = `${Number(rect.height) * state.scale}px`
  if (label) {
    const tag = document.createElement("span")
    tag.textContent = label
    node.appendChild(tag)
  }
  state.stage.appendChild(node)
}

function renderGeometry(state) {
  const geometry = state.data.geometry || {}
  addRect(state, geometry.safe_area, "safe-area", "safe")
  addRect(state, geometry.data_area, "data-area", "bars")
  addRect(state, geometry.ranking_lane, "ranking-lane", "rank")
  addRect(state, geometry.category_lane, "category-lane", "category")
  addRect(state, geometry.value_lane, "value-lane", "value")
  addRect(state, geometry.source_layout?.available_rect, "source-available", "source width")
  for (const row of geometry.row_rects || []) addRect(state, row, "bar-row", "")
  for (const bar of geometry.bar_rects || []) addRect(state, bar, "bar-extent", "")
  for (const logo of geometry.primary_logo_rects || []) addRect(state, logo, "primary-logo", "L1")
  for (const logo of geometry.secondary_logo_rects || []) addRect(state, logo, "secondary-logo", "L2")
  addRect(state, geometry.collision_rect, "collision-area", "collision")
  addRect(state, geometry.editorial_rect, "editorial-card", "editorial")
  for (const [name, rect] of Object.entries(geometry.text_bounds || {})) addRect(state, rect, `text-bound text-bound-${name}`, "")
}

function render(state) {
  if (!state.data || !state.positions) return
  const dimensions = stageDimensions(state)
  state.scale = dimensions.width / Number(state.data.canvas_width)
  state.stage.style.width = `${dimensions.width}px`
  state.stage.style.height = `${dimensions.height}px`
  state.stage.style.setProperty("--canvas-background", state.data.theme.background_color || "#fff")
  state.stage.replaceChildren()
  renderGeometry(state)
  for (const name of elementNames) {
    const definition = state.data.elements[name]
    const node = document.createElement("div")
    node.className = "layout-element"
    node.dataset.name = name
    node.textContent = definition.text
    node.tabIndex = 0
    node.onpointerdown = event => startDrag(state, event)
    node.onclick = () => setActive(state, name)
    positionNode(state, node, name)
    state.stage.appendChild(node)
  }
  updateStatus(state)
}

function setActive(state, name) {
  state.active = name
  state.stage.querySelectorAll(".layout-element").forEach(node => node.classList.toggle("active", node.dataset.name === name))
  updateStatus(state)
}

function startDrag(state, event) {
  const node = event.currentTarget
  const name = node.dataset.name
  setActive(state, name)
  if (isManaged(state, name)) return
  state.stage.focus()
  node.setPointerCapture(event.pointerId)
  node.classList.add("dragging")
  const rect = state.stage.getBoundingClientRect()
  state.drag = {
    name, pointerId: event.pointerId,
    offsetX: state.positions[name].x * state.scale - (event.clientX - rect.left),
    offsetY: state.positions[name].y * state.scale - (event.clientY - rect.top),
  }
  node.onpointermove = moveEvent => moveDrag(state, moveEvent)
  node.onpointerup = endEvent => endDrag(state, endEvent)
  node.onpointercancel = endEvent => endDrag(state, endEvent)
  event.preventDefault()
}

function moveDrag(state, event) {
  if (!state.drag || event.pointerId !== state.drag.pointerId) return
  const rect = state.stage.getBoundingClientRect()
  const position = state.positions[state.drag.name]
  position.x = Math.round(clamp((event.clientX - rect.left + state.drag.offsetX) / state.scale, 0, state.data.canvas_width))
  position.y = Math.round(clamp((event.clientY - rect.top + state.drag.offsetY) / state.scale, 0, state.data.canvas_height))
  positionNode(state, event.currentTarget, state.drag.name)
  updateStatus(state)
}

function endDrag(state, event) {
  if (!state.drag) return
  event.currentTarget.classList.remove("dragging")
  event.currentTarget.onpointermove = null
  state.drag = null
  emit(state)
}

function align(state, action) {
  if (isManaged(state, state.active)) return
  if (action === "reset") state.positions = clone(state.data.preset_positions)
  else if (action === "left") state.positions[state.active].x = 0
  else if (action === "center") state.positions[state.active].x = Math.round(state.data.canvas_width / 2)
  else if (action === "right") state.positions[state.active].x = state.data.canvas_width
  render(state)
  emit(state)
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
    state.toolbar.onclick = event => {
      const action = event.target?.dataset?.action
      if (action) align(state, action)
    }
    state.stage.onkeydown = event => {
      if (!state.positions?.[state.active] || !event.key.startsWith("Arrow") || isManaged(state, state.active)) return
      const distance = event.shiftKey ? 10 : 1
      const position = state.positions[state.active]
      if (event.key === "ArrowLeft") position.x -= distance
      if (event.key === "ArrowRight") position.x += distance
      if (event.key === "ArrowUp") position.y -= distance
      if (event.key === "ArrowDown") position.y += distance
      position.x = clamp(position.x, 0, state.data.canvas_width)
      position.y = clamp(position.y, 0, state.data.canvas_height)
      render(state); emit(state); event.preventDefault()
    }
  }
  state.setStateValue = setStateValue
  state.data = data
  const incoming = JSON.stringify(data.positions)
  if (!state.drag && (state.incoming === null || (incoming !== state.incoming && incoming !== JSON.stringify(state.positions)))) state.positions = clone(data.positions)
  state.incoming = incoming
  render(state)
  return () => { state.resizeObserver?.disconnect(); state.root.remove(); instances.delete(parentElement) }
}
