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
  wrap.appendChild(stage)
  const hint = document.createElement("div")
  hint.className = "layout-hint"
  hint.textContent = "Drag text directly. Arrow keys move 1 px; Shift + arrows move 10 px."
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

function positionNode(state, node, name) {
  const position = state.positions[name]
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
}

function updateStatus(state) {
  const position = state.positions?.[state.active]
  const label = state.data?.elements?.[state.active]?.label || state.active
  state.status.textContent = position ? `${label}: X ${position.x} · Y ${position.y}` : "Select an element"
}

function emit(state) { state.setStateValue("positions", clone(state.positions)) }

function render(state) {
  if (!state.data || !state.positions) return
  const dimensions = stageDimensions(state)
  state.scale = dimensions.width / Number(state.data.canvas_width)
  state.stage.style.width = `${dimensions.width}px`
  state.stage.style.height = `${dimensions.height}px`
  state.stage.style.setProperty("--canvas-background", state.data.theme.background_color || "#fff")
  state.stage.replaceChildren()
  const safe = document.createElement("div")
  safe.className = "layout-safe-area"
  state.stage.appendChild(safe)
  const layout = state.data.layout
  const count = Math.max(3, Math.min(8, Number(layout.bar_count) || 6))
  const usable = Math.max(1, state.data.canvas_height - layout.top_margin - layout.bottom_margin)
  for (let index = 0; index < count; index += 1) {
    const bar = document.createElement("div")
    bar.className = "layout-bar"
    bar.style.left = `${layout.left_margin * state.scale}px`
    bar.style.top = `${(layout.top_margin + index * usable / count) * state.scale}px`
    bar.style.width = `${Math.max(20, (state.data.canvas_width - layout.left_margin - layout.right_margin) * (1 - index * .07)) * state.scale}px`
    bar.style.height = `${Math.max(2, layout.bar_height * state.scale)}px`
    bar.style.background = state.data.theme.bar_color || "#4e79a7"
    state.stage.appendChild(bar)
  }
  for (const name of elementNames) {
    const definition = state.data.elements[name]
    const node = document.createElement("div")
    node.className = "layout-element"
    node.dataset.name = name
    node.textContent = definition.text
    node.onpointerdown = event => startDrag(state, event)
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
    state.toolbar.onclick = event => {
      const action = event.target?.dataset?.action
      if (action) align(state, action)
    }
    state.stage.onkeydown = event => {
      if (!state.positions?.[state.active] || !event.key.startsWith("Arrow")) return
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
  if (state.incoming === null || (incoming !== state.incoming && incoming !== JSON.stringify(state.positions))) {
    state.positions = clone(data.positions)
  }
  state.incoming = incoming
  render(state)
  return () => { state.root.remove(); instances.delete(parentElement) }
}
