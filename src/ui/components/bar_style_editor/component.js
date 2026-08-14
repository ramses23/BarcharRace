const instances = new WeakMap()
const clone = value => JSON.parse(JSON.stringify(value))

function buildInstance(parentElement) {
  const root = document.createElement("div")
  root.className = "bar-editor"
  parentElement.appendChild(root)
  return {
    root,
    settings: null,
    incoming: null,
    data: null,
    setStateValue: null,
    openGroups: new Map(),
  }
}

function button(label, active, onClick) {
  const node = document.createElement("button")
  node.type = "button"
  node.className = `bar-button${active ? " active" : ""}`
  node.textContent = label
  node.onclick = onClick
  return node
}

function emit(state, field, value) {
  state.settings[field] = value
  state.settings.bar_appearance_mode = "unified"
  if (field === "bar_fill_type") state.settings.bar_gradient_enabled = value === "gradient"
  state.setStateValue("settings", clone(state.settings))
  render(state)
}

function renderHeader(state) {
  const header = document.createElement("div")
  header.className = "bar-editor-header"
  const shape = document.createElement("div")
  shape.innerHTML = '<span class="bar-editor-label">Shape</span>'
  const shapeButtons = document.createElement("div")
  shapeButtons.className = "bar-button-row"
  for (const value of ["rectangle", "rounded", "capsule", "lollipop"]) {
    shapeButtons.appendChild(button(value[0].toUpperCase() + value.slice(1), state.settings.bar_shape === value, () => emit(state, "bar_shape", value)))
  }
  shape.appendChild(shapeButtons)
  header.append(shape)
  state.root.appendChild(header)
}

function fillBackground(state, color) {
  const s = state.settings
  if (s.bar_fill_type !== "gradient") return s.bar_fill_use_category_color ? color : s.bar_fill_color_start
  const classicVectorGradient = s.bar_fill_use_category_color
    && s.bar_gradient_direction === "horizontal"
    && Number(s.bar_gradient_color_count) === 2
    && Number(s.bar_edge_darkening) <= 0
  const lightenPercent = Math.max(0, Math.min(100, Number(s.bar_gradient_lighten) * 100))
  const start = s.bar_fill_use_category_color
    ? (classicVectorGradient ? color : `color-mix(in srgb, ${color} 76%, black)`)
    : s.bar_fill_color_start
  const center = s.bar_fill_use_category_color
    ? `color-mix(in srgb, ${color} 70%, white)`
    : s.bar_fill_color_center
  const end = s.bar_fill_use_category_color
    ? (classicVectorGradient ? `color-mix(in srgb, ${color} ${100 - lightenPercent}%, white)` : color)
    : s.bar_fill_color_end
  const direction = { horizontal: "to right", vertical: "to bottom", diagonal: "135deg" }[s.bar_gradient_direction] || "to right"
  return Number(s.bar_gradient_color_count) === 2
    ? `linear-gradient(${direction}, ${start}, ${end})`
    : `linear-gradient(${direction}, ${start}, ${center} ${Number(s.bar_highlight_position) * 100}%, ${end})`
}

function renderActiveSummary(state) {
  const s = state.settings
  const summary = document.createElement("div")
  summary.className = "bar-active-summary"
  const items = [
    s.bar_shape.replaceAll("_", " "),
    `${s.bar_fill_use_category_color ? "category" : "custom"} ${s.bar_fill_type}`,
  ]
  if (s.bar_fill_type === "gradient") items.push(`${s.bar_gradient_direction} · ${s.bar_gradient_color_count} stops`)
  if (s.bar_texture_enabled) items.push("texture")
  if (s.bar_border_enabled) items.push("border")
  if (s.bar_shadow_enabled) items.push("shadow")
  if (s.bar_bevel_enabled) items.push("bevel")
  if (Number(s.bar_inner_shadow_opacity) > 0) items.push("inner shadow")
  if (Number(s.bar_top_highlight_opacity) > 0 || Number(s.bar_bottom_shade_opacity) > 0) items.push("depth")
  if (s.bar_outer_glow_enabled || Number(s.bar_inner_glow_opacity) > 0) items.push("glow")
  if (s.bar_shine_enabled) items.push("shine")
  if (s.bar_track_enabled) items.push("track")
  items.push(`logo ${s.bar_logo_position.replaceAll("_", " ")}`)
  if (s.bar_secondary_logo_enabled) items.push(`second logo ${s.bar_secondary_logo_layout.replaceAll("_", " ")}`)
  items.push(`labels ${s.bar_label_position.replaceAll("_", " ")}`)
  items.push(`values ${s.bar_value_position.replaceAll("_", " ")}`)
  for (const item of items) {
    const chip = document.createElement("span")
    chip.className = "bar-active-chip"
    chip.textContent = item
    summary.appendChild(chip)
  }
  state.root.appendChild(summary)
}

function previewLogoSize(value) {
  const size = Number(value)
  const safeSize = Number.isFinite(size) ? size : 24
  return `${Math.max(8, Math.min(26, safeSize * 0.42))}px`
}

function renderPreview(state) {
  const preview = document.createElement("div")
  preview.className = "bar-preview"
  preview.style.setProperty("--chart-background", state.data.background_color || "#fff")
  const colors = state.data.bar_colors?.length ? state.data.bar_colors : ["#4E79A7", "#F28E2B", "#E15759"]
  for (let index = 0; index < 3; index += 1) {
    const row = document.createElement("div")
    row.className = "bar-preview-row"
    const rank = document.createElement("span")
    rank.className = "bar-preview-rank"
    rank.textContent = `#${index + 1}`
    const name = document.createElement("span")
    name.className = "bar-preview-name"
    name.textContent = "Category"
    const track = document.createElement("div")
    track.className = "bar-preview-track"
    const fill = document.createElement("div")
    fill.className = `bar-preview-fill ${state.settings.bar_shape}`
    fill.style.width = `${88 - index * 18}%`
    fill.style.background = fillBackground(state, colors[index % colors.length])
    fill.style.borderRadius = state.settings.bar_shape === "rectangle" ? "0" : state.settings.bar_shape === "rounded" ? "6px" : "999px"
    fill.style.border = state.settings.bar_border_enabled ? `${state.settings.bar_border_width}px solid ${state.settings.bar_border_color}` : "none"
    const shadows = []
    if (state.settings.bar_shadow_enabled) shadows.push(`${state.settings.bar_shadow_offset_x}px ${state.settings.bar_shadow_offset_y}px 0 rgb(0 0 0 / ${state.settings.bar_shadow_alpha})`)
    if (state.settings.bar_outer_glow_enabled) shadows.push(`0 0 ${state.settings.bar_glow_blur}px ${state.settings.bar_glow_color}`)
    fill.style.boxShadow = shadows.join(", ")
    track.appendChild(fill)
    if (state.settings.bar_logo_position !== "hidden") {
      const logo = document.createElement("span")
      logo.className = "bar-preview-logo primary"
      logo.textContent = "1"
      logo.style.width = previewLogoSize(state.settings.logo_size)
      logo.style.height = previewLogoSize(state.settings.logo_size)
      track.appendChild(logo)
    }
    if (state.settings.bar_secondary_logo_enabled) {
      const logo = document.createElement("span")
      logo.className = "bar-preview-logo secondary"
      logo.textContent = "2"
      logo.style.width = previewLogoSize(state.settings.bar_secondary_logo_size)
      logo.style.height = previewLogoSize(state.settings.bar_secondary_logo_size)
      track.appendChild(logo)
    }
    row.append(rank, name, track)
    preview.appendChild(row)
  }
  state.root.appendChild(preview)
}

function fieldControl(state, descriptor) {
  if (descriptor.type === "boolean") {
    const label = document.createElement("label")
    label.className = "bar-toggle"
    const input = document.createElement("input")
    input.type = "checkbox"
    input.checked = Boolean(state.settings[descriptor.field])
    input.onchange = () => emit(state, descriptor.field, input.checked)
    label.append(input, document.createTextNode(descriptor.label))
    return label
  }
  const label = document.createElement("label")
  label.className = `bar-field${descriptor.type === "range" ? " wide" : ""}`
  const title = document.createElement("span")
  title.textContent = descriptor.label
  let input
  if (descriptor.type === "enum") {
    input = document.createElement("select")
    for (const value of descriptor.options) {
      const option = document.createElement("option")
      option.value = value
      option.textContent = value.replaceAll("_", " ")
      input.appendChild(option)
    }
    input.value = state.settings[descriptor.field]
    input.onchange = () => emit(state, descriptor.field, input.value)
  } else {
    input = document.createElement("input")
    input.type = descriptor.type === "color" ? "color" : "range"
    input.value = state.settings[descriptor.field]
    if (descriptor.type === "range") {
      input.min = descriptor.minimum
      input.max = descriptor.maximum
      input.step = descriptor.step
      const output = document.createElement("span")
      output.className = "bar-range-value"
      output.textContent = String(input.value)
      input.oninput = () => { output.textContent = input.value; emit(state, descriptor.field, Number(input.value)) }
      label.append(title, input, output)
      return label
    }
    input.oninput = () => emit(state, descriptor.field, input.value.toUpperCase())
  }
  label.append(title, input)
  return label
}

function rememberOpenGroups(state) {
  for (const details of state.root.querySelectorAll("details.bar-group[data-group]")) {
    state.openGroups.set(details.dataset.group, details.open)
  }
}

function renderFields(state) {
  const groups = document.createElement("div")
  groups.className = "bar-groups"
  const grouped = new Map()
  for (const descriptor of state.data.fields ?? []) {
    if (!grouped.has(descriptor.group)) grouped.set(descriptor.group, [])
    grouped.get(descriptor.group).push(descriptor)
  }
  for (const [groupName, descriptors] of grouped.entries()) {
    const details = document.createElement("details")
    details.className = "bar-group"
    details.dataset.group = groupName
    const defaultOpen = ["Fill", "Frame", "Category text", "Content"].includes(groupName)
    details.open = state.openGroups.has(groupName)
      ? state.openGroups.get(groupName)
      : defaultOpen
    details.addEventListener("toggle", () => {
      state.openGroups.set(groupName, details.open)
    })
    const summary = document.createElement("summary")
    summary.textContent = groupName
    const fields = document.createElement("div")
    fields.className = "bar-fields"
    for (const descriptor of descriptors) fields.appendChild(fieldControl(state, descriptor))
    details.append(summary, fields)
    groups.appendChild(details)
  }
  state.root.appendChild(groups)
}

function render(state) {
  if (!state.settings || !state.data) return
  rememberOpenGroups(state)
  state.root.replaceChildren()
  renderHeader(state)
  renderActiveSummary(state)
  renderPreview(state)
  renderFields(state)
}

export default function (component) {
  const { data, parentElement, setStateValue } = component
  let state = instances.get(parentElement)
  if (!state) { state = buildInstance(parentElement); instances.set(parentElement, state) }
  state.data = data
  state.setStateValue = setStateValue
  const incoming = JSON.stringify(data.settings)
  if (state.incoming === null || (incoming !== state.incoming && incoming !== JSON.stringify(state.settings))) {
    state.settings = clone(data.settings)
  }
  state.incoming = incoming
  render(state)
  return () => { state.root.remove(); instances.delete(parentElement) }
}
