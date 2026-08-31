import pandas as pd

from hevy_analytics.analytics.formulas import is_hard_set
from hevy_analytics.config.landmarks import Landmarks


def classify_volume(weekly_volume_df: pd.DataFrame, landmarks: Landmarks) -> pd.DataFrame:
    """Adds a `classification` column: below_mev | mev_to_mav | mav_to_mrv | above_mrv."""
    if weekly_volume_df.empty:
        return weekly_volume_df.assign(classification=pd.Series(dtype="object"))

    def classify(row) -> str:
        lm = landmarks.landmark_for(row["muscle_group"])
        sets = row["hard_sets"]
        if sets < lm.mev:
            return "below_mev"
        if sets < lm.mav:
            return "mev_to_mav"
        if sets < lm.mrv:
            return "mav_to_mrv"
        return "above_mrv"

    df = weekly_volume_df.copy()
    df["classification"] = df.apply(classify, axis=1)
    return df


def detect_plateau(e1rm_df: pd.DataFrame, landmarks: Landmarks) -> pd.DataFrame:
    """Flags exercises whose best e1RM has not improved by more than
    `min_e1rm_improvement_pct` over the last `window_sessions` sessions.

    Compares the best e1RM of the first half of the window against the best
    e1RM of the second half (rather than single first/last data points) so a
    single light or high-rep session doesn't read as a huge "plateau" purely
    from session-to-session noise."""
    rule = landmarks.plateau_rule
    flags = []
    for exercise_id, group in e1rm_df.groupby("exercise_template_id"):
        group = group.sort_values("workout_date")
        if len(group) < rule.window_sessions:
            continue
        window = group.tail(rule.window_sessions)
        midpoint = len(window) // 2
        first_half = window.iloc[: max(midpoint, 1)]
        second_half = window.iloc[max(midpoint, 1):]
        if second_half.empty:
            continue
        first_e1rm = first_half["e1rm"].max()
        last_e1rm = second_half["e1rm"].max()
        if first_e1rm <= 0:
            continue
        pct_change = (last_e1rm - first_e1rm) / first_e1rm * 100
        if pct_change < rule.min_e1rm_improvement_pct:
            flags.append(
                {
                    "exercise_template_id": exercise_id,
                    "window_sessions": rule.window_sessions,
                    "first_e1rm": first_e1rm,
                    "last_e1rm": last_e1rm,
                    "pct_change": pct_change,
                }
            )
    return pd.DataFrame(flags)


def _session_summary(sets_df: pd.DataFrame, landmarks: Landmarks) -> pd.DataFrame:
    df = sets_df[sets_df["set_type"].apply(lambda t: is_hard_set(t, landmarks.hard_set_types))].copy()
    df = df.dropna(subset=["exercise_template_id", "weight_kg"])
    df["workout_date"] = df["start_time"].dt.date
    return (
        df.groupby(["exercise_template_id", "workout_date"])
        .agg(avg_weight=("weight_kg", "mean"), avg_reps=("reps", "mean"), avg_rpe=("rpe", "mean"))
        .reset_index()
        .sort_values(["exercise_template_id", "workout_date"])
    )


def detect_fatigue_signals(sets_df: pd.DataFrame, landmarks: Landmarks) -> pd.DataFrame:
    """Flags exercises where, at roughly constant load, RPE has risen or reps
    have declined over the configured window. Sessions with no RPE recorded
    are skipped for the RPE-based rule (older history is often RPE-less)."""
    rule = landmarks.deload_rule
    summary = _session_summary(sets_df, landmarks)
    flags = []

    for exercise_id, group in summary.groupby("exercise_template_id"):
        group = group.sort_values("workout_date")
        if len(group) < rule.window_sessions:
            continue
        window = group.tail(rule.window_sessions)

        mean_weight = window["avg_weight"].mean()
        if mean_weight <= 0:
            continue
        weight_spread_pct = (window["avg_weight"].max() - window["avg_weight"].min()) / mean_weight * 100
        if weight_spread_pct > rule.weight_tolerance_pct:
            continue

        rpe_window = window.dropna(subset=["avg_rpe"])
        if len(rpe_window) >= 2:
            rpe_delta = rpe_window.iloc[-1]["avg_rpe"] - rpe_window.iloc[0]["avg_rpe"]
            if rpe_delta >= rule.rpe_increase_threshold:
                flags.append(
                    {
                        "exercise_template_id": exercise_id,
                        "signal": "rising_rpe_at_constant_load",
                        "window_sessions": rule.window_sessions,
                        "rpe_delta": rpe_delta,
                        "avg_weight": mean_weight,
                    }
                )
                continue

        reps_delta = window.iloc[-1]["avg_reps"] - window.iloc[0]["avg_reps"]
        if reps_delta <= -1:
            flags.append(
                {
                    "exercise_template_id": exercise_id,
                    "signal": "declining_reps_at_constant_load",
                    "window_sessions": rule.window_sessions,
                    "reps_delta": reps_delta,
                    "avg_weight": mean_weight,
                }
            )

    return pd.DataFrame(flags)
