const instances = new WeakMap()
const controlledStyles = [
  "position",
  "top",
  "left",
  "width",
  "zIndex",
  "boxSizing",
]

function schedule(state) {
  if (state.frame !== null) return
  state.frame = window.requestAnimationFrame(() => sync(state))
}

function restoreTarget(state) {
  if (!state.target) return
  for (const property of controlledStyles) {
    state.target.style[property] = state.originalStyles[property] ?? ""
  }
  if (state.placeholder) {
    state.placeholder.style.display = "none"
    state.placeholder.style.height = "0"
  }
  state.active = false
}

function unbindTarget(state) {
  restoreTarget(state)
  state.resizeObserver?.disconnect()
  state.resizeObserver = null
  state.placeholder?.remove()
  state.placeholder = null
  state.target = null
  state.originalStyles = {}
}

function bindTarget(state) {
  const target = document.querySelector(state.selector)
  if (target === state.target && target?.isConnected) return

  unbindTarget(state)
  if (!target) return

  const placeholder = document.createElement("div")
  placeholder.dataset.floatingPreviewPlaceholder = ""
  placeholder.setAttribute("aria-hidden", "true")
  placeholder.style.cssText = [
    "display:none",
    "height:0",
    "width:100%",
    "pointer-events:none",
  ].join(";")
  target.parentNode?.insertBefore(placeholder, target)

  state.target = target
  state.placeholder = placeholder
  state.originalStyles = Object.fromEntries(
    controlledStyles.map(property => [property, target.style[property]])
  )
  state.resizeObserver = new ResizeObserver(() => schedule(state))
  state.resizeObserver.observe(target)
}

function applyFixedPosition(state, anchorRect) {
  const width = Math.max(0, anchorRect.width)
  state.target.style.position = "fixed"
  state.target.style.top = `${state.topOffset}px`
  state.target.style.left = `${anchorRect.left}px`
  state.target.style.width = `${width}px`
  state.target.style.zIndex = "90"
  state.target.style.boxSizing = "border-box"
}

function sync(state) {
  state.frame = null
  bindTarget(state)
  if (!state.target || !state.placeholder) return

  if (window.innerWidth <= state.breakpoint) {
    restoreTarget(state)
    return
  }

  if (!state.active) {
    const targetRect = state.target.getBoundingClientRect()
    if (targetRect.top > state.topOffset) return

    state.placeholder.style.height = `${targetRect.height}px`
    state.placeholder.style.display = "block"
    state.active = true
  }

  const anchorRect = state.placeholder.getBoundingClientRect()
  if (anchorRect.top > state.topOffset) {
    restoreTarget(state)
    return
  }

  state.placeholder.style.height =
    `${state.target.getBoundingClientRect().height}px`
  applyFixedPosition(state, anchorRect)
}

function buildInstance(parentElement) {
  const state = {
    parentElement,
    selector: ".st-key-latest_preview",
    breakpoint: 900,
    topOffset: 80,
    target: null,
    placeholder: null,
    originalStyles: {},
    resizeObserver: null,
    mutationObserver: null,
    frame: null,
    active: false,
  }
  state.onScroll = () => schedule(state)
  state.onResize = () => {
    restoreTarget(state)
    schedule(state)
  }
  window.addEventListener("scroll", state.onScroll, { passive: true })
  window.addEventListener("resize", state.onResize)
  state.mutationObserver = new MutationObserver(() => schedule(state))
  state.mutationObserver.observe(document.body, {
    childList: true,
    subtree: true,
  })
  return state
}

function destroyInstance(state) {
  window.removeEventListener("scroll", state.onScroll)
  window.removeEventListener("resize", state.onResize)
  state.mutationObserver?.disconnect()
  state.mutationObserver = null
  if (state.frame !== null) window.cancelAnimationFrame(state.frame)
  state.frame = null
  unbindTarget(state)
}

export default function (component) {
  const { data, parentElement } = component
  let state = instances.get(parentElement)
  if (!state) {
    state = buildInstance(parentElement)
    instances.set(parentElement, state)
  }

  const selector = String(
    data?.target_selector || ".st-key-latest_preview"
  )
  if (selector !== state.selector) {
    unbindTarget(state)
    state.selector = selector
  }
  state.breakpoint = Number(data?.breakpoint) || 900
  state.topOffset = Number(data?.top_offset) || 80
  schedule(state)

  return () => {
    if (instances.get(parentElement) !== state) return
    destroyInstance(state)
    instances.delete(parentElement)
  }
}
