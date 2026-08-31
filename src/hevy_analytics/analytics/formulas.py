def epley_1rm(weight: float, reps: int) -> float:
    return weight * (1 + reps / 30)


def brzycki_1rm(weight: float, reps: int) -> float:
    if reps >= 37:
        raise ValueError("Brzycki formula is unstable for reps >= 37")
    return weight * 36 / (37 - reps)


def estimate_1rm(weight: float, reps: int, formula: str = "epley") -> float:
    if formula == "epley":
        return epley_1rm(weight, reps)
    if formula == "brzycki":
        return brzycki_1rm(weight, reps)
    raise ValueError(f"Unknown 1RM formula: {formula}")


def tonnage(weight: float, reps: int) -> float:
    return weight * reps


def is_hard_set(set_type: str, hard_set_types: list[str]) -> bool:
    return set_type in hard_set_types
