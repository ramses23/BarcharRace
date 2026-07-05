def ease_in_out(t: float) -> float:
    """
    Función de easing tipo Smoothstep.

    Parámetros
    ----------
    t : float
        Valor entre 0 y 1.

    Retorna
    -------
    float
        Valor suavizado entre 0 y 1.
    """

    if t < 0:
        return 0.0

    if t > 1:
        return 1.0

    return t * t * (3 - 2 * t)