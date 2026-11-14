"""Generate the Power BI project (PBIP) for the Sovereign ESG Tracker.

    python powerbi/make_pbip.py

Writes powerbi/project/, which Power BI Desktop opens directly ("ESG Tracker.pbip").
The semantic model is TMDL, the report is in the enhanced report format (PBIR), and
the data is read from this repository's data/model/ folder on GitHub, so the project
has no dependency on local file paths.

Everything is derived from three sources of truth that also drive the manual build
guide: data/model/*.csv (columns), powerbi/measures.dax (measures) and powerbi/theme.json.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "powerbi" / "project"
NAME = "ESG Tracker"
DATA_URL = "https://raw.githubusercontent.com/theabdulaziz/esg-powerbi/main/data/model/"
S = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/"
NS = uuid.UUID("6f1d2c1e-5b0a-4c3e-9d41-000000000e59")

TABLES = {  # table name -> csv file
    "Country": "dim_country", "Indicator": "dim_indicator", "Years": "dim_year",
    "Observations": "fact_observations", "Scores": "fact_scores", "Latest": "fact_latest",
}
INT = {"year", "reported_year", "latest_year", "years_since_update", "rank_in_year", "indicators_used",
       "indicators_possible", "is_carried_forward"}
NUM = {"value", "latest_value", "score"}
BOOL = {"in_score"}
HIDDEN = {("Observations", "iso3"), ("Observations", "indicator_id"), ("Observations", "year"),
          ("Scores", "iso3"), ("Scores", "year"), ("Latest", "iso3"), ("Latest", "indicator_id")}
RELATIONSHIPS = [("Observations", "iso3", "Country"), ("Observations", "indicator_id", "Indicator"),
                 ("Observations", "year", "Years"), ("Scores", "iso3", "Country"), ("Scores", "year", "Years"),
                 ("Latest", "iso3", "Country"), ("Latest", "indicator_id", "Indicator")]
FORMATS = {"Whole number": "#,0", "Decimal, 1 decimal": "0.0", "Decimal, 2 decimals": "#,0.00",
           "Percentage, 1 decimal": "0.0%", "+0.0;-0.0;0.0": "+0.0;-0.0;0.0", "Year": "0"}


def guid(*parts: str) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


def short(*parts: str) -> str:
    return hashlib.sha1("/".join(parts).encode()).hexdigest()[:20]


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def dump(path: Path, obj) -> None:
    write(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


# ============================================================ semantic model
def columns_of(table: str) -> list[str]:
    with (ROOT / "data" / "model" / f"{TABLES[table]}.csv").open(encoding="utf-8") as f:
        return next(csv.reader(f))


def col_types(name: str) -> tuple[str, str]:
    """(TMDL dataType, Power Query type) for a column."""
    if name in INT:
        return "int64", "Int64.Type"
    if name in NUM:
        return "double", "type number"
    if name in BOOL:
        return "boolean", "type logical"
    return "string", "type text"


def table_tmdl(table: str) -> str:
    cols = columns_of(table)
    out = [f"table {table}", f"\tlineageTag: {guid('table', table)}", ""]
    for c in cols:
        dtype, _ = col_types(c)
        out.append(f"\tcolumn {c}")
        out.append(f"\t\tdataType: {dtype}")
        if (table, c) in HIDDEN:
            out.append("\t\tisHidden")
        if dtype == "int64":
            out.append("\t\tformatString: 0")
        out.append(f"\t\tlineageTag: {guid('column', table, c)}")
        if (table, c) == ("Country", "country"):
            out.append("\t\tdataCategory: Country")
        out += ["\t\tsummarizeBy: none", f"\t\tsourceColumn: {c}", "", "\t\tannotation SummarizationSetBy = User", ""]
    typed = ", ".join(f'{{"{c}", {col_types(c)[1]}}}' for c in cols)
    out += [
        f"\tpartition {table} = m",
        "\t\tmode: import",
        "\t\tsource =",
        "\t\t\t\tlet",
        f'\t\t\t\t\tSource = Csv.Document(Web.Contents(DataSource, [RelativePath = "{TABLES[table]}.csv"]), '
        f"[Delimiter = \",\", Columns = {len(cols)}, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),",
        "\t\t\t\t\tPromoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        f'\t\t\t\t\tTyped = Table.TransformColumnTypes(Promoted, {{{typed}}}, "en-US")',
        "\t\t\t\tin",
        "\t\t\t\t\tTyped",
        "",
        "\tannotation PBI_ResultType = Table",
        "",
    ]
    return "\n".join(out)


def parse_measures() -> list[tuple[str, list[str], str | None]]:
    """(name, expression lines, format string) for every measure in measures.dax."""
    lines = (ROOT / "powerbi" / "measures.dax").read_text(encoding="utf-8").splitlines()
    measures, fmt, i = [], None, 0
    head = re.compile(r"^([A-Z][A-Za-z0-9 %]*?) =\s*(.*)$")
    while i < len(lines):
        line = lines[i]
        if line.startswith("//"):
            m = re.search(r"Format: (.+?)\s*$", line)
            if m:
                fmt = FORMATS[m.group(1)]
            i += 1
            continue
        m = head.match(line)
        if not m:
            i += 1
            continue
        name, first = m.group(1), m.group(2)
        body = [first] if first else []
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].startswith("//"):
            body.append(lines[i])
            i += 1
        measures.append((name, body, fmt))
        fmt = None
    return measures


def measures_tmdl() -> str:
    out = ["table Measures", f"\tlineageTag: {guid('table', 'Measures')}", ""]
    for name, body, fmt in parse_measures():
        if len(body) == 1:
            out.append(f"\tmeasure '{name}' = {body[0]}")
        else:
            out.append(f"\tmeasure '{name}' =")
            out += ["\t\t\t" + b for b in body]
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out += [f"\t\tlineageTag: {guid('measure', name)}", ""]
    out += [
        "\tcolumn Hidden", "\t\tdataType: string", "\t\tisHidden", f"\t\tlineageTag: {guid('column', 'Measures', 'Hidden')}",
        "\t\tsummarizeBy: none", "\t\tsourceColumn: Hidden", "",
        "\tpartition Measures = m", "\t\tmode: import", "\t\tsource = #table(type table [Hidden = text], {})", "",
        "\tannotation PBI_ResultType = Table", "",
    ]
    return "\n".join(out)


def build_model() -> None:
    sm = OUT / f"{NAME}.SemanticModel"
    dump(sm / ".platform", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": NAME},
        "config": {"version": "2.0", "logicalId": guid("semanticmodel")},
    })
    dump(sm / "definition.pbism", {"version": "4.1", "settings": {}})
    d = sm / "definition"
    write(d / "database.tmdl", "database\n\tcompatibilityLevel: 1601\n\n")
    order = json.dumps(["DataSource", *TABLES, "Measures"], separators=(",", ":"))
    write(d / "model.tmdl", "\n".join([
        "model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3", "\tdiscourageImplicitMeasures",
        "\tsourceQueryCulture: en-US", "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", "",
        "annotation __PBI_TimeIntelligenceEnabled = 0", "", f"annotation PBI_QueryOrder = {order}", "",
        *[f"ref table {t}" for t in [*TABLES, "Measures"]], "",
    ]))
    write(d / "expressions.tmdl", "\n".join([
        "/// Folder that holds the six model tables. Point it at a local folder URL to work offline.",
        "expression DataSource =", f'\t\t"{DATA_URL}" meta [', "\t\t\tIsParameterQuery = true,", '\t\t\tType = "Text",',
        "\t\t\tIsParameterQueryRequired = true", "\t\t]", f"\tlineageTag: {guid('expression', 'DataSource')}", "",
        "\tannotation PBI_ResultType = Text", "",
    ]))
    write(d / "relationships.tmdl", "\n".join(
        f"relationship {guid('rel', f, c, t)}\n\tfromColumn: {f}.{c}\n\ttoColumn: {t}.{c}\n" for f, c, t in RELATIONSHIPS))
    for t in TABLES:
        write(d / "tables" / f"{t}.tmdl", table_tmdl(t))
    write(d / "tables" / "Measures.tmdl", measures_tmdl())


# ==================================================================== report
def lit(value) -> dict:
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (int, float)):
        text = f"{value}D"
    else:
        text = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": text}}}


def col(entity: str, prop: str, source: str | None = None) -> dict:
    ref = {"Source": source} if source else {"Entity": entity}
    return {"Column": {"Expression": {"SourceRef": ref}, "Property": prop}}


def meas(name: str, source: str | None = None) -> dict:
    ref = {"Source": source} if source else {"Entity": "Measures"}
    return {"Measure": {"Expression": {"SourceRef": ref}, "Property": name}}


def proj(field: dict, label: str | None = None) -> dict:
    kind = "Column" if "Column" in field else "Measure"
    entity = field[kind]["Expression"]["SourceRef"]["Entity"]
    p = {"field": field, "queryRef": f"{entity}.{field[kind]['Property']}", "nativeQueryRef": field[kind]["Property"]}
    if kind == "Column":
        p["active"] = True
    if label:
        p["displayName"] = label
    return p


def roles(**kw) -> dict:
    return {role: {"projections": [proj(f) if "field" not in f else f for f in fields]} for role, fields in kw.items()}


def sort_by(field: dict, descending: bool = True) -> dict:
    return {"sort": [{"field": field, "direction": "Descending" if descending else "Ascending"}], "isDefaultSort": False}


def gradient(measure: str) -> dict:
    return {"solid": {"color": {"expr": {"FillRule": {
        "Input": meas(measure),
        "FillRule": {"linearGradient2": {
            "min": {"color": {"Literal": {"Value": "'#F0EFEC'"}}},
            "max": {"color": {"Literal": {"Value": "'#256ABF'"}}},
            "nullColoringStrategy": {"strategy": {"Literal": {"Value": "'asZero'"}}},
        }},
    }}}}}


def top_n(entity: str, prop: str, measure: str, n: int, bottom: bool = False) -> dict:
    return {"filters": [{
        "name": short("topn", entity, prop, measure),
        "field": col(entity, prop),
        "type": "TopN",
        "filter": {
            "Version": 2,
            "From": [
                {"Name": "subquery", "Type": 2, "Expression": {"Subquery": {"Query": {
                    "Version": 2,
                    "From": [{"Name": "c", "Entity": entity, "Type": 0}, {"Name": "m", "Entity": "Measures", "Type": 0}],
                    "Select": [{**col(entity, prop, "c"), "Name": "field"}],
                    "OrderBy": [{"Direction": 1 if bottom else 2, "Expression": meas(measure, "m")}],
                    "Top": n,
                }}}},
                {"Name": "c", "Entity": entity, "Type": 0},
            ],
            "Where": [{"Condition": {"In": {"Expressions": [col(entity, prop, "c")],
                                            "Table": {"SourceRef": {"Source": "subquery"}}}}}],
        },
        "howCreated": "User",
    }]}


def equals_filter(entity: str, prop: str, literal: str) -> dict:
    return {"Version": 2, "From": [{"Name": "t", "Entity": entity, "Type": 0}],
            "Where": [{"Condition": {"In": {"Expressions": [col(entity, prop, "t")],
                                            "Values": [[{"Literal": {"Value": literal}}]]}}}]}


class Page:
    def __init__(self, key: str, title: str):
        self.key, self.title, self.name, self.visuals = key, title, short("page", key), []

    def add(self, kind: str, x, y, w, h, *, query=None, title=None, objects=None, filters=None, sort=None, vco=None):
        name = short(self.key, kind, str(len(self.visuals)))
        visual: dict = {"visualType": kind}
        if query:
            visual["query"] = {"queryState": query}
            if sort:
                visual["query"]["sortDefinition"] = sort
        if objects:
            visual["objects"] = objects
        container = dict(vco or {})
        if title:
            container["title"] = [{"properties": {"show": lit(True), "text": lit(title)}}]
        elif kind not in ("textbox",):
            container.setdefault("title", [{"properties": {"show": lit(False)}}])
        if container:
            visual["visualContainerObjects"] = container
        visual["drillFilterOtherVisuals"] = True
        z = 1000 * (len(self.visuals) + 1)
        doc = {"$schema": S + "visualContainer/2.0.0/schema.json", "name": name,
               "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z}, "visual": visual}
        if filters:
            doc["filterConfig"] = filters
        self.visuals.append(doc)

    # ---- helpers for the recurring pieces
    def heading(self, text: str, sub: str):
        self.add("textbox", 24, 10, 760, 60, objects={"general": [{"properties": {"paragraphs": [
            {"textRuns": [{"value": text, "textStyle": {"fontFamily": "Segoe UI Semibold", "fontSize": "18pt", "color": "#0b0b0b"}}]},
            {"textRuns": [{"value": sub, "textStyle": {"fontFamily": "Segoe UI", "fontSize": "10pt", "color": "#52514e"}}]},
        ]}}]}, vco={"background": [{"properties": {"show": lit(False)}}]})

    def cards(self, measures: list[str], y: int = 78):
        n, gap, left, width = len(measures), 12, 24, 1232
        w = (width - gap * (n - 1)) / n
        for i, m in enumerate(measures):
            self.add("card", left + i * (w + gap), y, w, 92, query=roles(Values=[meas(m)]),
                     objects={"labels": [{"properties": {"fontSize": lit(22)}}]})

    def slicer(self, entity, prop, x, w, mode="Dropdown", preset: str | None = None):
        general = []
        if preset:
            general = [{"properties": {"filter": {"filter": equals_filter(entity, prop, "'" + preset + "'")}}}]
        objects = {"data": [{"properties": {"mode": lit(mode)}}]}
        if general:
            objects["general"] = general
        if mode == "Dropdown" and preset:
            objects["selection"] = [{"properties": {"singleSelect": lit(True)}}]
        self.add("slicer", x, 10, w, 60, query=roles(Values=[col(entity, prop)]), objects=objects)


def build_pages() -> list[Page]:
    country, region = col("Country", "country"), col("Country", "region")
    year, pillar = col("Years", "year"), col("Scores", "pillar")
    theme, indicator = col("Indicator", "theme"), col("Indicator", "indicator")

    p1 = Page("overview", "Overview")
    p1.heading("Sovereign ESG scores", "World Bank ESG data · 193 countries · score 0 to 100, higher is better · latest year in the selection")
    p1.slicer("Years", "year", 800, 220, mode="Between")
    p1.slicer("Country", "region", 1032, 224)
    p1.cards(["Country Count", "Indicator Count", "Reported Values", "Coverage %", "ESG Score"])
    p1.add("filledMap", 24, 182, 600, 520, title="ESG score by country",
           query=roles(Category=[country], Tooltips=[meas("ESG Score")]),
           objects={"dataPoint": [{"properties": {"fill": gradient("ESG Score")},
                                   "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}}]})
    p1.add("clusteredBarChart", 636, 182, 620, 254, title="Top 10 countries", query=roles(Category=[country], Y=[meas("ESG Score")]),
           sort=sort_by(meas("ESG Score")), filters=top_n("Country", "country", "ESG Score", 10),
           objects={"labels": [{"properties": {"show": lit(True)}}]})
    p1.add("lineChart", 636, 448, 620, 254, title="Average ESG score by region",
           query=roles(Category=[year], Y=[meas("ESG Score")], Series=[region]), sort=sort_by(year, descending=False))

    p2 = Page("profile", "Country profile")
    p2.heading("Country ESG profile", "Pick one country · scores are percentiles among all countries in the latest year")
    p2.slicer("Country", "country", 960, 296, preset="United States")
    p2.cards(["ESG Score", "ESG Rank Label", "Environment Score", "Social Score", "Governance Score", "ESG Score 5Y Change",
              "Region ESG Score", "ESG vs Region"])
    p2.add("lineChart", 24, 182, 560, 520, title="Pillar scores over time",
           query=roles(Category=[year], Y=[meas("Pillar Score")], Series=[pillar]), sort=sort_by(year, descending=False))
    p2.add("tableEx", 596, 182, 660, 520, title="Indicators: value, year reported and percentile score",
           query=roles(Values=[col("Indicator", "pillar"), indicator, meas("Indicator Value"), meas("Value Reported In"), meas("Indicator Score")]),
           sort=sort_by(meas("Indicator Score")),
           filters={"filters": [{"name": short("scored-only"), "field": col("Indicator", "in_score"), "type": "Categorical",
                                 "filter": equals_filter("Indicator", "in_score", "true"), "howCreated": "User"}]})

    p3 = Page("compare", "Compare")
    p3.heading("Comparing countries and regions", "Each dot is a country · hover for its name and scores")
    p3.slicer("Years", "year", 800, 220, mode="Between")
    p3.slicer("Country", "region", 1032, 224)
    p3.add("scatterChart", 24, 84, 700, 618, title="Governance against social outcomes",
           query=roles(Category=[country], Series=[region], X=[meas("Governance Score")], Y=[meas("Social Score")]))
    p3.add("pivotTable", 736, 84, 520, 250, title="Average score by region and pillar",
           query=roles(Rows=[region], Columns=[pillar], Values=[meas("Pillar Score")]),
           objects={"values": [{"properties": {"backColor": gradient("Pillar Score")},
                                "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": "Measures.Pillar Score"}}],
                    "subTotals": [{"properties": {"rowSubtotals": lit(False), "columnSubtotals": lit(False)}}]})
    p3.add("clusteredBarChart", 736, 346, 520, 356, title="Biggest 5-year gains in ESG score",
           query=roles(Category=[country], Y=[meas("ESG Score 5Y Change")]), sort=sort_by(meas("ESG Score 5Y Change")),
           filters=top_n("Country", "country", "ESG Score 5Y Change", 10), objects={"labels": [{"properties": {"show": lit(True)}}]})

    p4 = Page("gaps", "Data gaps")
    p4.heading("Data gaps: how complete and how current is the data?", "Reported values only · carried-forward values are not counted as coverage")
    p4.slicer("Country", "region", 1032, 224)
    p4.cards(["Coverage %", "Carried Forward %", "Stale Series %", "Series Never Reported", "Avg Years Since Update"])
    p4.add("pivotTable", 24, 182, 780, 520, title="Coverage by theme and year (share of countries reporting)",
           query=roles(Rows=[theme], Columns=[year], Values=[meas("Coverage %")]),
           objects={"values": [{"properties": {"backColor": gradient("Coverage %")},
                                "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": "Measures.Coverage %"}}],
                    "subTotals": [{"properties": {"rowSubtotals": lit(False), "columnSubtotals": lit(False)}}]})
    p4.add("clusteredBarChart", 816, 182, 440, 254, title="Least current indicators (average years since update)",
           query=roles(Category=[indicator], Y=[meas("Avg Years Since Update")]), sort=sort_by(meas("Avg Years Since Update")),
           filters=top_n("Indicator", "indicator", "Avg Years Since Update", 10), objects={"labels": [{"properties": {"show": lit(True)}}]})
    p4.add("clusteredBarChart", 816, 448, 440, 254, title="Countries with least data",
           query=roles(Category=[country], Y=[meas("Coverage %")]), sort=sort_by(meas("Coverage %"), descending=False),
           filters=top_n("Country", "country", "Coverage %", 10, bottom=True), objects={"labels": [{"properties": {"show": lit(True)}}]})
    return [p1, p2, p3, p4]


def build_report() -> None:
    rep = OUT / f"{NAME}.Report"
    dump(rep / ".platform", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": NAME},
        "config": {"version": "2.0", "logicalId": guid("report")},
    })
    dump(rep / "definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    shutil.copy(ROOT / "powerbi" / "base" / "CY24SU10.json", _mk(rep / "StaticResources" / "SharedResources" / "BaseThemes") / "CY24SU10.json")
    theme_file = "SovereignESGTracker.json"
    shutil.copy(ROOT / "powerbi" / "theme.json", _mk(rep / "StaticResources" / "RegisteredResources") / theme_file)

    d = rep / "definition"
    dump(d / "version.json", {"$schema": S + "versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
    dump(d / "report.json", {
        "$schema": S + "report/1.3.0/schema.json",
        "themeCollection": {
            "baseTheme": {"name": "CY24SU10", "reportVersionAtImport": "5.61", "type": "SharedResources"},
            "customTheme": {"name": theme_file, "reportVersionAtImport": "5.61", "type": "RegisteredResources"},
        },
        "layoutOptimization": "None",
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": theme_file, "path": theme_file, "type": "CustomTheme"}]},
        ],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultFilterActionIsDataFilter": True, "defaultDrillFilterOtherVisuals": True,
                     "allowChangeFilterTypes": True, "allowInlineExploration": True, "useEnhancedTooltips": True},
    })
    pages = build_pages()
    dump(d / "pages" / "pages.json", {"$schema": S + "pagesMetadata/1.0.0/schema.json",
                                      "pageOrder": [p.name for p in pages], "activePageName": pages[0].name})
    for p in pages:
        dump(d / "pages" / p.name / "page.json", {
            "$schema": S + "page/1.4.0/schema.json", "name": p.name, "displayName": p.title,
            "displayOption": "FitToPage", "height": 720, "width": 1280,
            "objects": {"background": [{"properties": {"color": {"solid": {"color": lit("#F9F9F7")}}, "transparency": lit(0)}}]},
        })
        for v in p.visuals:
            dump(d / "pages" / p.name / "visuals" / v["name"] / "visual.json", v)


def _mk(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


if __name__ == "__main__":
    if OUT.exists():
        shutil.rmtree(OUT)
    build_model()
    build_report()
    dump(OUT / f"{NAME}.pbip", {"version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                               "settings": {"enableAutoRecovery": True}})
    write(OUT / ".gitignore", "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")
    files = [p for p in OUT.rglob("*") if p.is_file()]
    print(f"wrote {len(files)} files to {OUT.relative_to(ROOT)}")
