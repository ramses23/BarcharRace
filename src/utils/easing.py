def clamp_unit(t):
    return min(1.0, max(0.0, t))


def linear(t):
    return clamp_unit(t)


def smoothstep(t):
    t = clamp_unit(t)
    return t * t * (3 - 2 * t)


def ease_in_cubic(t):
    t = clamp_unit(t)
    return t * t * t


def ease_out_cubic(t):
    t = clamp_unit(t)
    return 1 - (1 - t) ** 3


def ease_in_out_cubic(t):
    t = clamp_unit(t)

    if t < 0.5:
        return 4 * t * t * t

    return 1 - ((-2 * t + 2) ** 3) / 2


EASING_PRESETS = {
    "linear": linear,
    "smoothstep": smoothstep,
    "ease_in_out": smoothstep,
    "ease_in_cubic": ease_in_cubic,
    "ease_out_cubic": ease_out_cubic,
    "ease_in_out_cubic": ease_in_out_cubic,
}


def ease_in_out(t):
    return smoothstep(t)


def get_easing_function(name):
    try:
        return EASING_PRESETS[name]
    except KeyError as exc:
        available = ", ".join(list_easings())
        raise ValueError(f"Unknown easing '{name}'. Available easings: {available}") from exc


def list_easings():
    return tuple(sorted(EASING_PRESETS))
