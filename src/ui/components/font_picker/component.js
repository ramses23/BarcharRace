const instances = new WeakMap()

function fontStyle(value) {
  return value ? `"${String(value).replaceAll('"', '')}"` : "inherit"
}

export default function (component) {
  const { data, parentElement, setStateValue } = component
  let state = instances.get(parentElement)
  if (!state) {
    const root = document.createElement("div")
    root.className = "font-picker"
    parentElement.appendChild(root)
    state = { root, open: false, value: "" }
    instances.set(parentElement, state)
  }

  const incomingValue = data?.value ?? ""
  if (incomingValue !== state.value) state.value = incomingValue

  const displayName = value => value || data?.theme_default_label || "Project default"
  const selectValue = value => {
    state.value = value
    state.open = false
    setStateValue("value", value)
    render()
  }
  const option = value => {
    const button = document.createElement("button")
    button.type = "button"
    button.className = `font-option${value === state.value ? " selected" : ""}`
    button.style.fontFamily = fontStyle(value)
    const name = document.createElement("span")
    name.textContent = displayName(value)
    const sample = document.createElement("span")
    sample.className = "font-sample"
    sample.textContent = "Aa 123"
    button.append(name, sample)
    button.onclick = () => selectValue(value)
    return button
  }
  const render = () => {
    state.root.replaceChildren()
    const label = document.createElement("label")
    label.className = "font-label"
    label.textContent = data?.label ?? "Font"
    const trigger = document.createElement("button")
    trigger.type = "button"
    trigger.className = "font-trigger"
    trigger.setAttribute("aria-expanded", String(state.open))
    trigger.style.fontFamily = fontStyle(state.value)
    const selected = document.createElement("span")
    selected.textContent = displayName(state.value)
    const arrow = document.createElement("span")
    arrow.textContent = "▼"
    trigger.append(selected, arrow)
    trigger.onclick = () => { state.open = !state.open; render() }
    const menu = document.createElement("div")
    menu.className = `font-menu${state.open ? " open" : ""}`
    menu.appendChild(option(""))
    for (const value of data?.options ?? []) menu.appendChild(option(value))
    state.root.append(label, trigger, menu)
  }

  render()
  return () => { state.root.replaceChildren() }
}
