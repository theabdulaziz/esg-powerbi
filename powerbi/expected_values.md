# Expected values

Use this to check the report after you build it. These numbers were computed outside Power BI
from the same six tables. If a card shows something different, the measure, a relationship or a
data type is wrong.

## With no filters at all

| Measure | Expected |
|---|---:|
| Country Count | 193 |
| Indicator Count | 67 |
| Reported Values | 156,606 |
| Possible Values | 258,620 |
| Coverage % | 60.6% |
| Carried Forward % | 16.8% |
| Selected Year | 2019 |
| ESG Score | 49.7 |
| Environment Score | 51.9 |
| Social Score | 48.0 |
| Governance Score | 49.6 |
| Ranked Countries | 181 |
| Series With Data | 10,868 |
| Series Never Reported | 2,063 |
| Stale Series | 1,257 |
| Stale Series % | 11.6% |
| Avg Years Since Update | 1.9 |

## With the Country slicer set to United States

| Measure | Expected |
|---|---:|
| ESG Score | 62.8 |
| Environment Score | 44.2 |
| Social Score | 61.4 |
| Governance Score | 82.8 |
| ESG Rank Label | 31 of 181 |
| ESG Score 5Y Change | +1.3 |
| Region ESG Score (Americas) | 50.6 |
| ESG vs Region | +12.2 |
| World ESG Score | 49.7 |

With the Indicator slicer also set to "CO2 emissions (metric tons per capita)":

| Measure | Expected |
|---|---:|
| Indicator Value | 15.24 |
| Indicator Score | 5.3 |
| Value Reported In | 2018 |

## Top five countries by ESG Score, 2019

| Rank | Country | ESG Score |
|---:|---|---:|
| 1 | Switzerland | 79.6 |
| 2 | Sweden | 78.4 |
| 3 | Iceland | 76.4 |
| 4 | Finland | 74.7 |
| 5 | Norway | 74.4 |

## Average ESG Score by region, 2019

| Region | ESG Score | Countries scored |
|---|---:|---:|
| Africa | 39.7 | 53 |
| Americas | 50.6 | 33 |
| Asia | 47.5 | 47 |
| Europe | 64.1 | 39 |
| Oceania | 53.5 | 9 |
