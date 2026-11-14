"""Build the Power BI model tables from the World Bank Sovereign ESG data.

    python prep/build_dataset.py

Downloads the raw files on first run, then writes six CSVs to data/model/.
All transformation is SQL (DuckDB); Python only fetches files and runs it.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
MODEL = ROOT / "data" / "model"

SOURCES = {
    # World Bank ESG data, snapshot of July 2021 (CC BY 4.0), as published with the
    # World Bank's own "ESG gaps" research.
    "ESG_wbg_202107.csv": "https://raw.githubusercontent.com/worldbank/ESG_gaps_research/master/data/ESG_wbg_202107.csv",
    "esg_framework.csv": "https://raw.githubusercontent.com/worldbank/ESG_gaps_research/master/data/esg_framework.csv",
    # UN M49 regions keyed by ISO code (Open Data Commons PDDL).
    "country-codes.csv": "https://raw.githubusercontent.com/datasets/country-codes/master/data/country-codes.csv",
}

FIRST_YEAR, LAST_YEAR = 2000, 2019   # 2020 was only 4% complete in this snapshot
CARRY_FORWARD_YEARS = 5              # how long a reported value may stand in for missing years
MIN_COUNTRIES_TO_RANK = 30           # an indicator-year needs this many countries to be scored
MIN_PILLAR_COVERAGE = 0.5            # share of a pillar's scored indicators a country needs

SQL = f"""
create or replace table observations as
select iso3c as iso3, country, cast("date" as integer) as year, indicatorID as indicator_id,
       indicator as indicator_name, cast(value as double) as value
from read_csv('{(RAW / "ESG_wbg_202107.csv").as_posix()}', header = true, all_varchar = true,
              delim = ',', quote = '"', escape = '"', strict_mode = false)
where value is not null and cast("date" as integer) between {FIRST_YEAR} and {LAST_YEAR};

-- ------------------------------------------------------------------ dimensions
create or replace table dim_indicator as
select
    f.cetsid                                                as indicator_id,
    f.name                                                  as indicator,
    case f.sector when 'ENV' then 'Environment' when 'SOC' then 'Social' else 'Governance' end as pillar,
    f.theme,
    d.direction,
    d.direction <> 'context'                                as in_score,
    d.reason                                                as direction_reason
from read_csv('{(RAW / "esg_framework.csv").as_posix()}', header = true, encoding = 'latin-1') f
join read_csv('{(ROOT / "prep" / "indicator_directions.csv").as_posix()}', header = true) d
  on d.indicator_id = f.cetsid;

create or replace table dim_country as
select
    o.iso3,
    o.country,
    coalesce(c."Region Name", 'Not classified')             as region,
    coalesce(c."Sub-region Name", 'Not classified')         as sub_region
from (select iso3, any_value(country) as country from observations group by iso3) o
left join read_csv('{(RAW / "country-codes.csv").as_posix()}', header = true, all_varchar = true) c
  on c."ISO3166-1-Alpha-3" = o.iso3;

create or replace table dim_year as
select unnest(range({FIRST_YEAR}, {LAST_YEAR} + 1)) as year;

-- ------------------------------------------------------- observations and scores
-- One row per country, indicator and year. Where a year was not reported, the most
-- recent reported value from the previous {CARRY_FORWARD_YEARS} years stands in and is flagged.
create or replace table panel as
with grid as (
    select c.iso3, i.indicator_id, y.year
    from dim_country c cross join dim_indicator i cross join dim_year y
),
filled as (
    select
        g.iso3, g.indicator_id, g.year,
        last_value(o.value ignore nulls) over w             as value,
        last_value(o.year  ignore nulls) over w             as reported_year
    from grid g
    left join observations o using (iso3, indicator_id, year)
    window w as (partition by g.iso3, g.indicator_id order by g.year
                 rows between unbounded preceding and current row)
)
select iso3, indicator_id, year, value, reported_year,
       reported_year <> year                                as is_carried_forward
from filled
where value is not null and year - reported_year <= {CARRY_FORWARD_YEARS};

-- Score = percentile rank among all countries with a value for that indicator and
-- year, 0 to 100, flipped where lower is better. Context indicators get no score.
create or replace table fact_observations as
with ranked as (
    select
        p.*,
        i.direction,
        count(*) over (partition by p.indicator_id, p.year)                             as countries_ranked,
        percent_rank() over (partition by p.indicator_id, p.year order by p.value)      as pr
    from panel p join dim_indicator i using (indicator_id)
)
select
    iso3, indicator_id, year, value, reported_year,
    cast(is_carried_forward as integer)                     as is_carried_forward,
    case when direction = 'context' or countries_ranked < {MIN_COUNTRIES_TO_RANK} then null
         when direction = 'higher_better' then round(100 * pr, 2)
         else round(100 * (1 - pr), 2) end                  as score
from ranked;

-- Pillar score = simple average of a country's indicator scores in that pillar,
-- only if it has at least {int(MIN_PILLAR_COVERAGE * 100)}% of the indicators that were scored that year.
-- ESG = simple average of the three pillars, only if all three exist.
create or replace table fact_scores as
with possible as (
    select i.pillar, f.year, count(distinct f.indicator_id) as indicators_possible
    from fact_observations f join dim_indicator i using (indicator_id)
    where f.score is not null
    group by 1, 2
),
pillar as (
    select f.iso3, f.year, i.pillar, avg(f.score) as score, count(*) as indicators_used
    from fact_observations f join dim_indicator i using (indicator_id)
    where f.score is not null
    group by 1, 2, 3
),
kept as (
    select p.iso3, p.year, p.pillar, round(p.score, 2) as score, p.indicators_used, q.indicators_possible
    from pillar p join possible q using (pillar, year)
    where p.indicators_used >= {MIN_PILLAR_COVERAGE} * q.indicators_possible
),
overall as (
    select iso3, year, 'ESG' as pillar, round(avg(score), 2) as score,
           sum(indicators_used) as indicators_used, sum(indicators_possible) as indicators_possible
    from kept group by iso3, year
    having count(*) = 3
),
both_levels as (select * from kept union all select * from overall)
select *, rank() over (partition by pillar, year order by score desc) as rank_in_year
from both_levels;

-- Most recent reported value for each country and indicator, and how old it is.
create or replace table fact_latest as
select
    iso3, indicator_id,
    max(year)                                               as latest_year,
    arg_max(value, year)                                    as latest_value,
    {LAST_YEAR} - max(year)                                 as years_since_update
from observations
group by iso3, indicator_id;
"""

EXPORTS = {
    "dim_country": "select * from dim_country order by country",
    "dim_indicator": "select * from dim_indicator order by pillar, theme, indicator",
    "dim_year": "select * from dim_year order by year",
    "fact_observations": "select * from fact_observations order by iso3, indicator_id, year",
    "fact_scores": "select * from fact_scores order by pillar, year, rank_in_year, iso3",
    "fact_latest": "select * from fact_latest order by iso3, indicator_id",
}


def fetch_raw() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        target = RAW / name
        if not target.exists():
            print(f"Downloading {name}")
            urllib.request.urlretrieve(url, target)


def build() -> duckdb.DuckDBPyConnection:
    fetch_raw()
    con = duckdb.connect()
    con.execute(SQL)
    return con


def export(con: duckdb.DuckDBPyConnection) -> None:
    MODEL.mkdir(parents=True, exist_ok=True)
    for name, query in EXPORTS.items():
        con.execute(f"copy ({query}) to '{(MODEL / (name + '.csv')).as_posix()}' (header, delimiter ',')")
        rows = con.execute(f"select count(*) from {name}").fetchone()[0]
        print(f"  {name:20s} {rows:>8,} rows")


if __name__ == "__main__":
    connection = build()
    export(connection)
