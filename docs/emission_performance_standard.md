# Emission performance standards

The emission-performance policy component supports capacity-based standards such as the
Canadian Clean Electricity Regulations (CER). A standard limits emissions attributed to a set
of covered technology/output pairs:

```text
direct emissions + linked upstream emissions + linked downstream emissions
    <= intensity * available capacity * capacity_to_activity
```

The `intensity` value must use the same emission-per-activity basis as `emission_activity`. For
example, when emissions are measured in `kt` and activity in `PJ`, `30 t/GWh` is
`8.333333333 kt/PJ`.

## Tables

`emission_performance_standard` defines the policy limit by policy, region, period, and emission
commodity. `policy_technology` identifies every covered technology together with the output to
which the policy applies. `policy_emission_link` adds emissions from another technology/output
pair.

Direct `emission_activity` rows on the covered technology/output are included automatically and
do not need a policy link.

For linked emissions:

- When `linked_output_comm` is an input to the covered technology/output, the link is upstream.
  Temoa applies the linked emission rate to the covered process's fuel requirement. This avoids
  charging the policy for unrelated consumption of a shared upstream commodity.
- Otherwise, the link is downstream and Temoa includes emissions from the linked technology's
  actual output flow. A negative `emission_activity` therefore represents capture or removal.
- `allocation` defaults to `1.0` and can assign a fraction of a linked contribution when needed.

## CCS example

```sql
INSERT INTO emission_performance_standard
    (policy, region, period, emis_comm, intensity, units)
VALUES ('CER', 'NB', 2035, 'CO2', 8.333333333, 'kt/PJ');

INSERT INTO policy_technology
    (policy, region, tech, output_comm)
VALUES ('CER', 'NB', 'E_NGACC-CCS', 'ELCG');

-- Upstream gas-supply emissions: E_NG is an input to E_NGACC-CCS.
INSERT INTO policy_emission_link
    (policy, region, tech, output_comm, linked_tech, linked_output_comm)
VALUES ('CER', 'NB', 'E_NGACC-CCS', 'ELCG', 'IMP_NG_ELC', 'E_NG');

-- In the current Joint Atlantic database, captured CO2 is already represented
-- by a negative emission_activity on E_NGACC-CCS/ELCG. It is included directly,
-- so no downstream policy_emission_link row is needed for this generator.
```

The linked technology/output must have a matching `emission_activity` row for the standard's
emission commodity. An upstream link must resolve to one unique active emission rate in each
policy period; otherwise model validation stops with an error.

A covered technology/output that is inactive in a policy period is reported as a warning and
contributes zero in that period. An active covered process must have either a direct
`emission_activity` or at least one `policy_emission_link`; otherwise validation stops with an
error because its policy emissions cannot be determined.

For an existing v4 database, create the tables with
`scripts/add_emission_performance_policy.sql` before inserting policy data.
