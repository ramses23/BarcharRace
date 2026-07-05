def lerp(start: float, end: float, t: float) -> float:
    """
    Linear interpolation.

    Parameters
    ----------
    start : float
        Valor inicial.

    end : float
        Valor final.

    t : float
        Valor entre 0 y 1.

    Returns
    -------
    float
        Valor interpolado.
    """
    return start + (end - start) * t