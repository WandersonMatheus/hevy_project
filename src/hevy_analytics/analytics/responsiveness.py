from datetime import datetime, timezone

import pandas as pd

from hevy_analytics.analytics.formulas import is_hard_set, tonnage
from hevy_analytics.analytics.time_utils import week_start
from hevy_analytics.config.landmarks import Landmarks
from hevy_analytics.insights.models import Insight


def _weekly_primary_stats(sets_df: pd.DataFrame, templates_df: pd.DataFrame, landmarks: Landmarks) -> pd.DataFrame:
    """Hard sets AND tonnage per (week, muscle_group), primary mover only --
    no secondary-muscle credit. Kept deliberately simpler than
    `weekly_muscle_group_volume` (which does credit secondary movers) so that
    the volume series and the tonnage series used for responsiveness are on
    the exact same footing and directly comparable to each other."""
    hard = sets_df[sets_df["set_type"].apply(lambda t: is_hard_set(t, landmarks.hard_set_types))].copy()
    hard["week"] = week_start(hard["start_time"])
    merged = hard.merge(
        templates_df[["id", "primary_muscle_group"]],
        left_on="exercise_template_id",
        right_on="id",
        how="left",
    )
    merged = merged.dropna(subset=["primary_muscle_group"]).rename(
        columns={"primary_muscle_group": "muscle_group"}
    )
    merged["tonnage"] = merged.apply(
        lambda r: tonnage(r["weight_kg"], r["reps"])
        if pd.notna(r["weight_kg"]) and pd.notna(r["reps"])
        else 0.0,
        axis=1,
    )
    return merged.groupby(["week", "muscle_group"], as_index=False).agg(
        hard_sets=("set_id", "count"), tonnage=("tonnage", "sum")
    )


def volume_responsiveness(
    sets_df: pd.DataFrame, templates_df: pd.DataFrame, landmarks: Landmarks
) -> pd.DataFrame:
    """For each muscle group, splits your own training weeks into
    "higher volume than your median" vs "lower volume than your median", and
    compares the tonnage produced *the following week* between the two
    groups. A muscle group that reliably does more work the week after a
    high-volume week has a plausible "responds to volume" signal; one that
    doesn't may mean the configured MRV is already above what you can
    actually recover from -- or just reflects normal week-to-week variation.

    This is a correlational, small-N, exploratory comparison (weeks of data,
    not controlled sessions) -- confounded by sleep, stress, nutrition, other
    sports, etc. Treat results as a hypothesis to watch, not a conclusion."""
    rule = landmarks.responsiveness_rule
    weekly = _weekly_primary_stats(sets_df, templates_df, landmarks)
    if weekly.empty:
        return pd.DataFrame(
            columns=["muscle_group", "n_weeks", "median_hard_sets", "high_volume_relative_tonnage",
                     "low_volume_relative_tonnage", "diff_pct", "signal"]
        )

    all_weeks = pd.Index(sorted(sets_df["start_time"].pipe(week_start).unique()), name="week")

    rows = []
    for muscle_group, group in weekly.groupby("muscle_group"):
        # Only reindex the numeric columns -- pandas 3's string dtype raises
        # if the int fill_value=0 lands in a leftover text column (like the
        # muscle_group column groupby keeps around on each sub-frame).
        s = group.set_index("week")[["hard_sets", "tonnage"]].reindex(all_weeks, fill_value=0)
        hard_sets = s["hard_sets"]
        tonnage_series = s["tonnage"]

        trained_weeks = int((hard_sets > 0).sum())
        if trained_weeks < rule.min_trained_weeks:
            rows.append({"muscle_group": muscle_group, "n_weeks": trained_weeks, "signal": "insufficient_data"})
            continue

        avg_tonnage = tonnage_series[tonnage_series > 0].mean()
        if not avg_tonnage or avg_tonnage <= 0:
            rows.append({"muscle_group": muscle_group, "n_weeks": trained_weeks, "signal": "insufficient_data"})
            continue

        median_sets = hard_sets[hard_sets > 0].median()
        # outcome = next week's tonnage relative to this muscle's own average
        # (not a %-change, since a week can start from 0 and blow up a ratio)
        next_relative = (tonnage_series.shift(-1) / avg_tonnage * 100).iloc[:-1]
        this_week_sets = hard_sets.iloc[:-1]
        # Require training BOTH this week and the next: otherwise a "low
        # volume" week is often actually the last week before a break/routine
        # switch, and it gets unfairly dragged down by the 0% that follows --
        # that's a training-continuity effect, not a volume dose-response one.
        continued_mask = (this_week_sets > 0) & (tonnage_series.shift(-1).iloc[:-1] > 0)

        high = next_relative[(this_week_sets >= median_sets) & continued_mask]
        low = next_relative[(this_week_sets < median_sets) & continued_mask]

        if len(high) < rule.min_weeks_per_side or len(low) < rule.min_weeks_per_side:
            rows.append({"muscle_group": muscle_group, "n_weeks": trained_weeks, "signal": "insufficient_data"})
            continue

        high_avg = high.mean()
        low_avg = low.mean()
        diff = high_avg - low_avg

        if diff > rule.signal_threshold_pct:
            signal = "responds_to_volume"
        elif diff < -rule.signal_threshold_pct:
            signal = "not_responding"
        else:
            signal = "no_clear_signal"

        rows.append(
            {
                "muscle_group": muscle_group,
                "n_weeks": trained_weeks,
                "median_hard_sets": round(median_sets, 1),
                "high_volume_relative_tonnage": round(high_avg, 1),
                "low_volume_relative_tonnage": round(low_avg, 1),
                "diff_pct": round(diff, 1),
                "signal": signal,
            }
        )

    return pd.DataFrame(rows)


def generate_responsiveness_insights(responsiveness_df: pd.DataFrame, landmarks: Landmarks) -> list[Insight]:
    if responsiveness_df.empty:
        return []

    now = datetime.now(timezone.utc).isoformat()
    analyzed = responsiveness_df[responsiveness_df["signal"] != "insufficient_data"]
    insufficient = responsiveness_df[responsiveness_df["signal"] == "insufficient_data"]
    if analyzed.empty:
        return []

    insights: list[Insight] = []
    responds = analyzed[analyzed["signal"] == "responds_to_volume"]
    not_responding = analyzed[analyzed["signal"] == "not_responding"]

    body = (
        f"Olhando {len(analyzed)} grupos musculares com histórico suficiente, {len(responds)} mostram "
        "sinal de produzir mais tonnage na semana seguinte a semanas de volume mais alto (indício de que "
        f"respondem bem a mais volume), e {len(not_responding)} não mostram esse padrão."
    )
    if not insufficient.empty:
        body += f" ({len(insufficient)} grupos ainda não têm semanas suficientes pra entrar nessa análise.)"
    body += (
        " Isso é uma comparação exploratória com poucas semanas de dado -- sono, estresse, nutrição e "
        "outras atividades físicas também influenciam o resultado. Trate como hipótese pra observar ao "
        "longo do tempo, não como conclusão fechada."
    )
    insights.append(
        Insight(
            id="resp-overview",
            type="diagnostic",
            title="Você reage melhor a mais volume?",
            body=body,
            metrics={"responds": len(responds), "not_responding": len(not_responding), "analyzed": len(analyzed)},
            severity="info",
            created_at=now,
        )
    )

    # One consolidated card per direction (not one per muscle group) --
    # avoids turning "12 muscle groups analyzed" into 12 nearly-identical cards.
    if not responds.empty:
        lines = [
            f"• {row['muscle_group']}: {row['high_volume_relative_tonnage']:.0f}% da média após "
            f"semana forte, vs {row['low_volume_relative_tonnage']:.0f}% após semana fraca "
            f"({row['n_weeks']} semanas)"
            for _, row in responds.iterrows()
        ]
        insights.append(
            Insight(
                id="resp-responds",
                type="diagnostic",
                title=f"{len(responds)} grupo(s) parecem responder bem a mais volume",
                body=(
                    "Semanas com mais hard sets foram seguidas de mais tonnage na semana seguinte:\n"
                    + "\n".join(lines)
                ),
                metrics={"count": len(responds)},
                severity="positive",
                created_at=now,
            )
        )

    if not not_responding.empty:
        lines = [
            f"• {row['muscle_group']}: MRV configurado hoje é {landmarks.landmark_for(row['muscle_group']).mrv} "
            f"sets ({row['n_weeks']} semanas analisadas)"
            for _, row in not_responding.iterrows()
        ]
        insights.append(
            Insight(
                id="resp-not-responding",
                type="diagnostic",
                title=f"{len(not_responding)} grupo(s) onde mais volume não parece ajudar",
                body=(
                    "Semanas de volume mais alto não vieram seguidas de mais tonnage -- pode ser que o "
                    "MRV configurado esteja mais alto do que você realmente absorve nesses grupos, ou só "
                    "ruído com poucas semanas de dado:\n" + "\n".join(lines)
                ),
                metrics={"count": len(not_responding)},
                severity="info",
                created_at=now,
            )
        )

    return insights
