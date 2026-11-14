"""Write the numbers and pictures used to check the Power BI report.

    python prep/make_reference.py

- powerbi/expected_values.md  what each measure should show, computed here
  independently of Power BI from the same model tables
- mockups/page*.png           what each report page should roughly look like
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

ROOT = Path(__file__).resolve().parent.parent
M = ROOT / "data" / "model"
YEAR = 2019
FOCUS = "USA"

country = pd.read_csv(M / "dim_country.csv")
indicator = pd.read_csv(M / "dim_indicator.csv")
obs = pd.read_csv(M / "fact_observations.csv")
scores = pd.read_csv(M / "fact_scores.csv").merge(country, on="iso3")
latest = pd.read_csv(M / "fact_latest.csv")
n_years = len(pd.read_csv(M / "dim_year.csv"))

COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
PILLARS = ["Environment", "ESG", "Governance", "Social"]          # alphabetical, as Power BI orders them
PILLAR_COLOR = dict(zip(PILLARS, COLORS))
REGIONS = sorted(country.region.unique())
REGION_COLOR = dict(zip(REGIONS, COLORS))
INK, INK2, MUTED, GRID, SURFACE, PAGE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb", "#f9f9f7"
SEQ = LinearSegmentedColormap.from_list("seq", ["#f0efec", "#cfe0f6", "#256abf"])

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "text.color": INK, "axes.edgecolor": GRID,
    "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED, "axes.facecolor": SURFACE,
    "figure.facecolor": PAGE, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
})


def pillar_avg(frame: pd.DataFrame, pillar: str, year: int = YEAR) -> float:
    return frame[(frame.pillar == pillar) & (frame.year == year)].score.mean()


# ------------------------------------------------------------ expected values
def expected_values() -> str:
    reported = int((obs.is_carried_forward == 0).sum())
    possible = len(country) * len(indicator) * n_years
    carried = obs.is_carried_forward.mean()
    us = scores[scores.iso3 == FOCUS]
    us_now = us[us.year == YEAR].set_index("pillar")
    us_prev = us[(us.year == YEAR - 5) & (us.pillar == "ESG")].score.iloc[0]
    us_region = country.loc[country.iso3 == FOCUS, "region"].iloc[0]
    region_avg = pillar_avg(scores[scores.region == us_region], "ESG")
    ranked = scores[(scores.pillar == "ESG") & (scores.year == YEAR)]
    stale = int((latest.years_since_update >= 5).sum())
    top = ranked.nsmallest(5, "rank_in_year")
    co2 = obs[(obs.iso3 == FOCUS) & (obs.indicator_id == "EN.ATM.CO2E.PC") & (obs.year == YEAR)].iloc[0]

    lines = [
        "# Expected values",
        "",
        "Use this to check the report after you build it. These numbers were computed outside Power BI",
        "from the same six tables. If a card shows something different, the measure, a relationship or a",
        "data type is wrong.",
        "",
        "## With no filters at all",
        "",
        "| Measure | Expected |",
        "|---|---:|",
        f"| Country Count | {len(country)} |",
        f"| Indicator Count | {len(indicator)} |",
        f"| Reported Values | {reported:,} |",
        f"| Possible Values | {possible:,} |",
        f"| Coverage % | {reported / possible:.1%} |",
        f"| Carried Forward % | {carried:.1%} |",
        f"| Selected Year | {YEAR} |",
        f"| ESG Score | {pillar_avg(scores, 'ESG'):.1f} |",
        f"| Environment Score | {pillar_avg(scores, 'Environment'):.1f} |",
        f"| Social Score | {pillar_avg(scores, 'Social'):.1f} |",
        f"| Governance Score | {pillar_avg(scores, 'Governance'):.1f} |",
        f"| Ranked Countries | {len(ranked)} |",
        f"| Series With Data | {len(latest):,} |",
        f"| Series Never Reported | {len(country) * len(indicator) - len(latest):,} |",
        f"| Stale Series | {stale:,} |",
        f"| Stale Series % | {stale / len(latest):.1%} |",
        f"| Avg Years Since Update | {latest.years_since_update.mean():.1f} |",
        "",
        "## With the Country slicer set to United States",
        "",
        "| Measure | Expected |",
        "|---|---:|",
        f"| ESG Score | {us_now.loc['ESG', 'score']:.1f} |",
        f"| Environment Score | {us_now.loc['Environment', 'score']:.1f} |",
        f"| Social Score | {us_now.loc['Social', 'score']:.1f} |",
        f"| Governance Score | {us_now.loc['Governance', 'score']:.1f} |",
        f"| ESG Rank Label | {int(us_now.loc['ESG', 'rank_in_year'])} of {len(ranked)} |",
        f"| ESG Score 5Y Change | {us_now.loc['ESG', 'score'] - us_prev:+.1f} |",
        f"| Region ESG Score ({us_region}) | {region_avg:.1f} |",
        f"| ESG vs Region | {us_now.loc['ESG', 'score'] - region_avg:+.1f} |",
        f"| World ESG Score | {pillar_avg(scores, 'ESG'):.1f} |",
        "",
        "With the Indicator slicer also set to \"CO2 emissions (metric tons per capita)\":",
        "",
        "| Measure | Expected |",
        "|---|---:|",
        f"| Indicator Value | {co2.value:.2f} |",
        f"| Indicator Score | {co2.score:.1f} |",
        f"| Value Reported In | {int(co2.reported_year)} |",
        "",
        f"## Top five countries by ESG Score, {YEAR}",
        "",
        "| Rank | Country | ESG Score |",
        "|---:|---|---:|",
    ]
    lines += [f"| {int(r.rank_in_year)} | {r.country} | {r.score:.1f} |" for r in top.itertuples()]
    lines += ["", "## Average ESG Score by region, " + str(YEAR), "", "| Region | ESG Score | Countries scored |", "|---|---:|---:|"]
    for region, g in ranked.groupby("region"):
        lines.append(f"| {region} | {g.score.mean():.1f} | {len(g)} |")
    return "\n".join(lines) + "\n"


# -------------------------------------------------------------------- mockups
def new_page(title: str, subtitle: str):
    fig = plt.figure(figsize=(12.8, 7.2), dpi=110)
    fig.text(0.03, 0.945, title, fontsize=16, fontweight="bold")
    fig.text(0.03, 0.912, subtitle, fontsize=9.5, color=INK2)
    return fig


def card(fig, x, y, w, h, label, value, note=""):
    ax = fig.add_axes([x, y, w, h]); ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(True); s.set_color(GRID)
    ax.text(0.07, 0.74, label, fontsize=8.5, color=INK2, transform=ax.transAxes)
    ax.text(0.07, 0.30, value, fontsize=19, fontweight="bold", transform=ax.transAxes)
    if note:
        ax.text(0.07, 0.09, note, fontsize=7.5, color=MUTED, transform=ax.transAxes)


def panel(fig, rect, title):
    ax = fig.add_axes(rect)
    ax.set_title(title, loc="left", fontsize=10.5, fontweight="bold", pad=8)
    return ax


def page_overview():
    fig = new_page(f"Sovereign ESG scores, {YEAR}", "World Bank ESG data · 193 countries · score 0 to 100, higher is better")
    reported = int((obs.is_carried_forward == 0).sum())
    vals = [("Countries", f"{len(country)}", ""), ("Indicators", f"{len(indicator)}", "43 scored, 24 context"),
            ("Reported values", f"{reported:,}", "2000 to 2019"),
            ("Coverage", f"{reported / (len(country) * len(indicator) * n_years):.1%}", "of possible values"),
            ("Average ESG score", f"{pillar_avg(scores, 'ESG'):.1f}", f"{YEAR}")]
    for k, (l, v, n) in enumerate(vals):
        card(fig, 0.03 + k * 0.19, 0.755, 0.175, 0.125, l, v, n)

    ax = fig.add_axes([0.03, 0.07, 0.44, 0.63]); ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(True); s.set_color(GRID)
    ax.set_title("ESG score by country", loc="left", fontsize=10.5, fontweight="bold", pad=8)
    ax.text(0.5, 0.52, "Filled map", ha="center", fontsize=15, color=MUTED, transform=ax.transAxes)
    ax.text(0.5, 0.44, "Location: Country[country]   Colour: ESG Score (light to dark)", ha="center", fontsize=9, color=MUTED, transform=ax.transAxes)

    ranked = scores[(scores.pillar == "ESG") & (scores.year == YEAR)].nsmallest(10, "rank_in_year").iloc[::-1]
    ax = panel(fig, [0.60, 0.42, 0.37, 0.28], "Top 10 countries")
    ax.barh(ranked.country, ranked.score, color=COLORS[0], height=0.62)
    for yv, s in zip(ranked.country, ranked.score):
        ax.text(s + 0.8, yv, f"{s:.1f}", va="center", fontsize=8, color=INK2)
    ax.set_xlim(0, 90); ax.grid(axis="y", visible=False); ax.tick_params(axis="y", labelsize=8, colors=INK2)

    ax = panel(fig, [0.53, 0.07, 0.44, 0.26], "Average ESG score by region")
    trend = scores[scores.pillar == "ESG"].groupby(["year", "region"]).score.mean().unstack()
    for region in REGIONS:
        ax.plot(trend.index, trend[region], color=REGION_COLOR[region], lw=2)
        ax.text(trend.index[-1] + 0.25, trend[region].iloc[-1], region, color=INK2, fontsize=8, va="center")
    ax.set_xlim(2000, 2022.5); ax.set_xticks(range(2000, 2020, 5)); ax.grid(axis="x", visible=False)
    return fig


def page_profile():
    name = country.loc[country.iso3 == FOCUS, "country"].iloc[0]
    us = scores[scores.iso3 == FOCUS]
    now = us[us.year == YEAR].set_index("pillar")
    n_ranked = len(scores[(scores.pillar == "ESG") & (scores.year == YEAR)])
    fig = new_page(f"ESG profile: {name}, {YEAR}", "Pick a country in the slicer · scores are percentiles among all countries")
    cards = [("ESG score", f"{now.loc['ESG', 'score']:.1f}", f"rank {int(now.loc['ESG', 'rank_in_year'])} of {n_ranked}"),
             ("Environment", f"{now.loc['Environment', 'score']:.1f}", ""), ("Social", f"{now.loc['Social', 'score']:.1f}", ""),
             ("Governance", f"{now.loc['Governance', 'score']:.1f}", ""),
             ("5-year change", f"{now.loc['ESG', 'score'] - us[(us.year == YEAR - 5) & (us.pillar == 'ESG')].score.iloc[0]:+.1f}", "ESG score, points")]
    for k, (l, v, n) in enumerate(cards):
        card(fig, 0.03 + k * 0.19, 0.755, 0.175, 0.125, l, v, n)

    ax = panel(fig, [0.05, 0.08, 0.38, 0.60], "Pillar scores over time")
    wide = us.pivot(index="year", columns="pillar", values="score")
    for p in PILLARS:
        ax.plot(wide.index, wide[p], color=PILLAR_COLOR[p], lw=2.6 if p == "ESG" else 1.8)
        ax.text(wide.index[-1] + 0.25, wide[p].iloc[-1], p, fontsize=8, va="center", color=INK2)
    ax.set_xlim(2000, 2023); ax.set_ylim(0, 100); ax.set_xticks(range(2000, 2020, 5)); ax.grid(axis="x", visible=False)

    d = obs[(obs.iso3 == FOCUS) & (obs.year == YEAR) & obs.score.notna()].merge(indicator, on="indicator_id")
    d = pd.concat([d.nlargest(8, "score"), d.nsmallest(8, "score")]).sort_values("score")
    ax = panel(fig, [0.66, 0.08, 0.31, 0.60], "Strongest and weakest indicators (percentile)")
    labels = [t if len(t) < 46 else t[:44] + "…" for t in d.indicator]
    ax.barh(range(len(d)), d.score, color=[PILLAR_COLOR[p] for p in d.pillar], height=0.66)
    ax.set_yticks(range(len(d))); ax.set_yticklabels(labels, fontsize=7.3, color=INK2)
    for k, s in enumerate(d.score):
        ax.text(s + 1.5, k, f"{s:.0f}", va="center", fontsize=7.5, color=INK2)
    ax.set_xlim(0, 112); ax.grid(axis="y", visible=False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=PILLAR_COLOR[p]) for p in ("Environment", "Governance", "Social")]
    ax.legend(handles, ["Environment", "Governance", "Social"], loc="lower right", frameon=False, fontsize=8)
    return fig


def page_compare():
    fig = new_page(f"Comparing countries and regions, {YEAR}", "Each dot is a country · hover for its name and scores")
    now = scores[scores.year == YEAR].pivot_table(index=["iso3", "country", "region"], columns="pillar", values="score").reset_index().dropna()
    ax = panel(fig, [0.06, 0.10, 0.50, 0.74], "Governance against social outcomes")
    for region in REGIONS:
        g = now[now.region == region]
        ax.scatter(g.Governance, g.Social, s=42, color=REGION_COLOR[region], edgecolor=SURFACE, linewidth=1.2, label=region)
    for iso in ("CHE", "USA", "IND", "BRA", "SOM", "CHN"):
        r = now[now.iso3 == iso]
        if len(r):
            ax.annotate(r.country.iloc[0], (r.Governance.iloc[0], r.Social.iloc[0]), xytext=(6, 5), textcoords="offset points", fontsize=8, color=INK2)
    ax.set_xlabel("Governance score"); ax.set_ylabel("Social score"); ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")

    ax = panel(fig, [0.66, 0.44, 0.31, 0.40], "Average score by region and pillar")
    mat = scores[scores.year == YEAR].groupby(["region", "pillar"]).score.mean().unstack()[["Environment", "Social", "Governance", "ESG"]]
    ax.imshow(mat.values, cmap=SEQ, vmin=20, vmax=80, aspect="auto"); ax.grid(False)
    ax.set_xticks(range(4)); ax.set_xticklabels(mat.columns, fontsize=8.5, color=INK2); ax.xaxis.tick_top()
    ax.set_yticks(range(len(mat))); ax.set_yticklabels(mat.index, fontsize=8.5, color=INK2)
    ax.set_title("Average score by region and pillar", loc="left", fontsize=10.5, fontweight="bold", pad=26)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            v = mat.values[i, j]
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=9.5, color="white" if v > 62 else INK)
    for s in ax.spines.values():
        s.set_visible(False)

    ax = panel(fig, [0.70, 0.10, 0.27, 0.24], "Biggest 5-year gains in ESG score")
    e = scores[scores.pillar == "ESG"].pivot(index="country", columns="year", values="score")
    gain = (e[YEAR] - e[YEAR - 5]).dropna().nlargest(6).iloc[::-1]
    ax.barh(gain.index, gain.values, color=COLORS[0], height=0.6)
    for k, v in enumerate(gain.values):
        ax.text(v + 0.15, k, f"+{v:.1f}", va="center", fontsize=8, color=INK2)
    ax.set_xlim(0, gain.max() * 1.25); ax.grid(axis="y", visible=False); ax.tick_params(axis="y", labelsize=8, colors=INK2)
    return fig


def page_gaps():
    reported = obs[obs.is_carried_forward == 0].merge(indicator, on="indicator_id")
    stale = (latest.years_since_update >= 5).mean()
    never = len(country) * len(indicator) - len(latest)
    fig = new_page("Data gaps: how complete and how current is sovereign ESG data?", "Reported values only · carried-forward values are not counted as coverage")
    cards = [("Coverage", f"{len(reported) / (len(country) * len(indicator) * n_years):.1%}", "of country × indicator × year"),
             ("Carried forward", f"{obs.is_carried_forward.mean():.1%}", "of values in the model"),
             ("Stale series", f"{stale:.1%}", "newest value 5+ years old"),
             ("Never reported", f"{never:,}", "country-indicator pairs"),
             ("Avg years since update", f"{latest.years_since_update.mean():.1f}", f"as of {YEAR}")]
    for k, (l, v, n) in enumerate(cards):
        card(fig, 0.03 + k * 0.19, 0.755, 0.175, 0.125, l, v, n)

    per_theme = indicator.groupby(["pillar", "theme"]).size().rename("n")
    cov = reported.groupby(["pillar", "theme", "year"]).size().unstack(fill_value=0)
    cov = cov.div(per_theme * len(country), axis=0).sort_index()
    ax = fig.add_axes([0.25, 0.07, 0.38, 0.60])
    ax.imshow(cov.values, cmap=SEQ, vmin=0, vmax=1, aspect="auto"); ax.grid(False)
    ax.set_title("Coverage by theme and year (share of countries reporting)", loc="left", fontsize=10.5, fontweight="bold", pad=8, x=-0.58)
    ax.set_yticks(range(len(cov))); ax.set_yticklabels([f"{p[:3]} · {t}" for p, t in cov.index], fontsize=7.6, color=INK2)
    ax.set_xticks(range(0, 20, 3)); ax.set_xticklabels(cov.columns[::3], fontsize=8)
    for i in range(cov.shape[0]):
        for j in (0, 5, 10, 15, 19):
            v = cov.values[i, j]
            ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=6.8, color="white" if v > 0.7 else INK2)
    for s in ax.spines.values():
        s.set_visible(False)

    age = latest.merge(indicator, on="indicator_id").groupby("indicator").years_since_update.mean().nlargest(9).iloc[::-1]
    ax = panel(fig, [0.845, 0.07, 0.125, 0.60], "Least current indicators\n(avg years since update)")
    ax.title.set_fontsize(9.5)
    ax.title.set_x(-1.35)
    ax.barh(range(len(age)), age.values, color=COLORS[1], height=0.62)
    ax.set_yticks(range(len(age))); ax.set_yticklabels([t if len(t) < 27 else t[:25] + "…" for t in age.index], fontsize=7, color=INK2)
    for k, v in enumerate(age.values):
        ax.text(v + 0.15, k, f"{v:.1f}", va="center", fontsize=7.5, color=INK2)
    ax.set_xlim(0, age.max() * 1.25); ax.grid(axis="y", visible=False)
    return fig


if __name__ == "__main__":
    (ROOT / "powerbi" / "expected_values.md").write_text(expected_values(), encoding="utf-8")
    out = ROOT / "mockups"; out.mkdir(exist_ok=True)
    for name, make in [("page1_overview", page_overview), ("page2_country_profile", page_profile),
                       ("page3_compare", page_compare), ("page4_data_gaps", page_gaps)]:
        figure = make(); figure.savefig(out / f"{name}.png"); plt.close(figure)
    print("wrote powerbi/expected_values.md and 4 mockups")
