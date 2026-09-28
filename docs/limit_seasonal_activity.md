# Seasonal output-activity limits

The `limit_seasonal_activity` table limits a technology's **output activity** in
a model season. The entered `daily_limit` is an average rate per day; Temoa
converts it to the seasonal quantity represented by the temporal structure:

```text
seasonal output <= daily_limit * days_per_period * season_fraction
```

For example, a limit of `0.481 PJ/day` in a season representing 25% of a
365-day period permits `0.481 * 365 * 0.25 = 43.89125 PJ` in that season.
The same conversion works when a season represents more than one day.

Required fields are `region`, `period`, `season`, `tech_or_group`,
`output_comm`, `operator`, and `daily_limit`. `units` and `notes` are optional.
The output commodity makes the limit unambiguous for multi-output technologies.
Technology groups and regional groups are supported.

For time-sliced technologies, Temoa sums `v_flow_out` over every time-of-day
slice in the selected season. For annual technologies, annual output is
allocated using `segment_fraction_per_season`. Efficiency is not applied,
because this is an output limit rather than an input/fuel-use limit.

This represents a seasonal average daily availability. Enforcing a maximum on
each individual calendar day requires a temporal mode with explicit modeled
days and a separate per-day constraint.
