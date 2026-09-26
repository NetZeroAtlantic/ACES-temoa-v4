# temoa/components/emissions.py
"""
Defines the components of the Temoa model related to emissions accounting.

This module is responsible for:
-  Defining index sets for emission-related parameters and constraints.
-  Defining the constraint rule for 'linked technologies', a special case where
    an emission commodity (e.g., captured CO2) is also treated as a physical
    input to a downstream process (e.g., synthetic fuel production).
"""

from __future__ import annotations

from logging import getLogger
from typing import TYPE_CHECKING

from pyomo.core import quicksum
from pyomo.environ import Constraint, value

if TYPE_CHECKING:
    from temoa.core.model import TemoaModel
    from temoa.types import ExprLike
    from temoa.types.core_types import (
        Commodity,
        Period,
        Region,
        Season,
        Technology,
        TimeOfDay,
        Vintage,
    )

logger = getLogger(__name__)


# ============================================================================
# PYOMO INDEX SET FUNCTIONS
# ============================================================================


def emission_activity_indices(
    model: TemoaModel,
) -> set[tuple[Region, Commodity, Commodity, Technology, Vintage, Commodity]]:
    return {
        (r, e, i, t, v, o)
        for r, i, t, v, o in model.efficiency.sparse_keys()
        for e in model.commodity_emissions
        if r in model.regional_indices
    }


def linked_tech_constraint_indices(
    model: TemoaModel,
) -> set[tuple[Region, Period, Season, TimeOfDay, Technology, Vintage, Commodity]]:
    return {
        (r, p, s, d, t, v, e)
        for r, t, e in model.linked_techs.sparse_keys()
        for p in model.time_optimize
        if (r, p, t) in model.process_vintages
        for v in model.process_vintages[r, p, t]
        if model.active_activity_rptv and (r, p, t, v) in model.active_activity_rptv
        for s in model.time_season
        for d in model.time_of_day
    }


# ============================================================================
# PYOMO CONSTRAINT RULES
# ============================================================================


def linked_emissions_tech_constraint(
    model: TemoaModel,
    r: Region,
    p: Period,
    s: Season,
    d: TimeOfDay,
    t: Technology,
    v: Vintage,
    e: Commodity,
) -> ExprLike:
    r"""
    This constraint can be used for carbon capture technologies that produce
    CO2 as an emissions commodity, but the CO2 also serves as a physical
    input commodity to a downstream process, such as synthetic fuel production.
    To accomplish this, a dummy technology is linked to the CO2-producing
    technology, converting the emissions activity into a physical commodity
    amount as follows:

    .. math::
       :label: linked_emissions_tech

            - \sum_{I, O} \textbf{FO}_{r, p, s, d, i, t, v, o} \cdot EAC_{r, e, i, t, v, o}
            = \sum_{I, O} \textbf{FO}_{r, p, s, d, i, \hat{t}, v, o}

            \forall \{r, p, s, d, t, v, e\} \in \Theta_{\text{linked\_techs}}

    where :math:`\hat{t} = LT_{r,t,e}` is the linked technology for primary technology
    :math:`t` and emissions commodity :math:`e`. For annual technologies
    (:math:`t \in T^a` or :math:`\hat{t} \in T^a`), the corresponding
    :math:`\textbf{FOA}` variable scaled by :math:`DSD` (for end use demand techs)
    or :math:`SEG` (for all other annual techs) is used instead.

    The relationship between the primary and linked technologies is given
    in the :code:`linked_techs` table. It is implicit that
    the primary region corresponds to the linked technology as well. The lifetimes
    of the primary and linked technologies should be specified and identical.
    """

    if t in model.tech_annual:
        primary_flow = quicksum(
            (
                value(model.demand_specific_distribution[r, p, s, d, S_o])
                if S_o in model.commodity_demand
                else value(model.segment_fraction[s, d])
            )
            * model.v_flow_out_annual[r, p, S_i, t, v, S_o]
            * value(model.emission_activity[r, e, S_i, t, v, S_o])
            for S_i in model.process_inputs[r, p, t, v]
            for S_o in model.process_outputs_by_input[r, p, t, v, S_i]
        )
    else:
        primary_flow = quicksum(
            model.v_flow_out[r, p, s, d, S_i, t, v, S_o]
            * value(model.emission_activity[r, e, S_i, t, v, S_o])
            for S_i in model.process_inputs[r, p, t, v]
            for S_o in model.process_outputs_by_input[r, p, t, v, S_i]
        )

    linked_t = value(model.linked_techs[r, t, e])

    # linked_flow = sum(
    #     M.v_flow_out[r, p, s, d, S_i, linked_t, v, S_o]
    #     for S_i in M.processInputs[r, p, linked_t, v]
    #     for S_o in M.process_outputs_by_input[r, p, linked_t, v, S_i]
    # )

    if linked_t in model.tech_annual:
        linked_flow = quicksum(
            (
                value(model.demand_specific_distribution[r, p, s, d, S_o])
                if S_o in model.commodity_demand
                else value(model.segment_fraction[s, d])
            )
            * model.v_flow_out_annual[r, p, S_i, linked_t, v, S_o]
            for S_i in model.process_inputs[r, p, linked_t, v]
            for S_o in model.process_outputs_by_input[r, p, linked_t, v, S_i]
        )
    else:
        linked_flow = quicksum(
            model.v_flow_out[r, p, s, d, S_i, linked_t, v, S_o]
            for S_i in model.process_inputs[r, p, linked_t, v]
            for S_o in model.process_outputs_by_input[r, p, linked_t, v, S_i]
        )

    return -primary_flow == linked_flow


def _process_output_emissions(
    model: TemoaModel,
    r: Region,
    p: Period,
    e: Commodity,
    t: Technology,
    o: Commodity,
) -> ExprLike:
    """Return emissions from one technology/output pair in one model period."""
    activity_indices = [
        (i, v)
        for er, ee, i, et, v, eo in model.emission_activity.sparse_keys()
        if er == r
        and ee == e
        and et == t
        and eo == o
        and (r, p, t, v) in model.active_activity_rptv
    ]

    if t in model.tech_annual:
        return quicksum(
            model.v_flow_out_annual[r, p, i, t, v, o]
            * value(model.emission_activity[r, e, i, t, v, o])
            for i, v in activity_indices
        )

    return quicksum(
        model.v_flow_out[r, p, s, d, i, t, v, o] * value(model.emission_activity[r, e, i, t, v, o])
        for i, v in activity_indices
        for s in model.time_season
        for d in model.time_of_day
    )


def _is_upstream_link(
    model: TemoaModel,
    r: Region,
    p: Period,
    covered_t: Technology,
    covered_o: Commodity,
    linked_o: Commodity,
) -> bool:
    """Return whether the linked output is an input to the covered process."""
    return any(
        linked_o in model.process_inputs_by_output.get((r, p, covered_t, v, covered_o), set())
        for v in model.process_vintages.get((r, p, covered_t), set())
    )


def _covered_process_is_active(
    model: TemoaModel,
    r: Region,
    p: Period,
    t: Technology,
    o: Commodity,
) -> bool:
    """Return whether a covered technology/output has an active process path."""
    return (r, p, t) in model.process_vintages and any(
        o in model.process_outputs.get((r, p, t, v), set()) for v in model.process_vintages[r, p, t]
    )


def _upstream_link_emissions(
    model: TemoaModel,
    r: Region,
    p: Period,
    e: Commodity,
    covered_t: Technology,
    covered_o: Commodity,
    linked_t: Technology,
    linked_o: Commodity,
) -> ExprLike:
    """Apply a linked upstream emission rate to the covered process's fuel use."""
    rates = {
        float(value(model.emission_activity[r, e, i, linked_t, v, linked_o]))
        for er, ee, i, et, v, eo in model.emission_activity.sparse_keys()
        if er == r
        and ee == e
        and et == linked_t
        and eo == linked_o
        and (r, p, linked_t, v) in model.active_activity_rptv
    }
    # Validation guarantees that an upstream link has exactly one applicable rate.
    rate = next(iter(rates)) if rates else 0.0
    paths = [
        (v, linked_o)
        for v in model.process_vintages.get((r, p, covered_t), set())
        if linked_o in model.process_inputs_by_output.get((r, p, covered_t, v, covered_o), set())
    ]

    if covered_t in model.tech_annual:
        return quicksum(
            model.v_flow_out_annual[r, p, i, covered_t, v, covered_o]
            / value(model.efficiency[r, i, covered_t, v, covered_o])
            * rate
            for v, i in paths
        )

    return quicksum(
        model.v_flow_out[r, p, s, d, i, covered_t, v, covered_o]
        / value(model.efficiency[r, i, covered_t, v, covered_o])
        * rate
        for v, i in paths
        for s in model.time_season
        for d in model.time_of_day
    )


def _linked_output_emissions(
    model: TemoaModel,
    r: Region,
    p: Period,
    e: Commodity,
    covered_t: Technology,
    covered_o: Commodity,
    linked_t: Technology,
    linked_o: Commodity,
) -> ExprLike:
    """Account for an upstream rate or an actual downstream linked flow."""
    if _is_upstream_link(model, r, p, covered_t, covered_o, linked_o):
        return _upstream_link_emissions(model, r, p, e, covered_t, covered_o, linked_t, linked_o)
    return _process_output_emissions(model, r, p, e, linked_t, linked_o)


def validate_emission_performance_standard(model: TemoaModel) -> bool:
    """Validate policy membership, active paths, and linked emissions records."""
    valid = True
    standards = set(model.emission_performance_standard.sparse_keys())

    for policy, r, p, e in standards:
        covered = {
            (t, o)
            for row_policy, row_r, t, o in model.policy_technology
            if row_policy == policy and row_r == r
        }
        if not covered:
            logger.error(
                'Emission policy %s in %s period %s has no policy_technology rows',
                policy,
                r,
                p,
            )
            valid = False

        links_by_covered = {(t, o): [] for t, o in covered}
        for row in model.policy_emission_link.sparse_keys():
            row_policy, row_r, t, o, linked_t, linked_o = row
            if row_policy == policy and row_r == r:
                links_by_covered.setdefault((t, o), []).append((linked_t, linked_o))

        for t, o in covered:
            if not _covered_process_is_active(model, r, p, t, o):
                logger.warning(
                    'policy_technology row (%s, %s, %s, %s) has no active process in period %s',
                    policy,
                    r,
                    t,
                    o,
                    p,
                )
                continue

            direct_ea = any(
                er == r
                and ee == e
                and et == t
                and eo == o
                and (r, p, t, v) in model.active_activity_rptv
                for er, ee, _i, et, v, eo in model.emission_activity.sparse_keys()
            )
            if not direct_ea and not links_by_covered.get((t, o)):
                logger.error(
                    'Active policy_technology row (%s, %s, %s, %s) has neither a direct '
                    'emission_activity for %s nor a policy_emission_link in period %s',
                    policy,
                    r,
                    t,
                    o,
                    e,
                    p,
                )
                valid = False
            if (r, p, t) not in model.v_capacity_available_by_period_and_tech:
                logger.error(
                    'Covered policy technology %s in %s has no available-capacity variable '
                    'in period %s',
                    t,
                    r,
                    p,
                )
                valid = False

        links = [
            (t, o, linked_t, linked_o, value(model.policy_emission_link[row]))
            for row in model.policy_emission_link.sparse_keys()
            for row_policy, row_r, t, o, linked_t, linked_o in [row]
            if row_policy == policy and row_r == r
        ]
        for t, o, linked_t, linked_o, allocation in links:
            if (t, o) not in covered:
                logger.error(
                    'policy_emission_link for %s/%s is missing a corresponding '
                    'policy_technology row for %s/%s',
                    t,
                    o,
                    policy,
                    r,
                )
                valid = False
                continue
            if not _covered_process_is_active(model, r, p, t, o):
                # The covered contribution is zero, so its linked contribution is also zero.
                continue
            matching_ea = [
                (i, v)
                for er, ee, i, et, v, eo in model.emission_activity.sparse_keys()
                if er == r
                and ee == e
                and et == linked_t
                and eo == linked_o
                and (r, p, linked_t, v) in model.active_activity_rptv
            ]
            if not matching_ea:
                logger.error(
                    'policy_emission_link (%s, %s, %s, %s -> %s, %s) has no matching '
                    'active emission_activity for %s in period %s',
                    policy,
                    r,
                    t,
                    o,
                    linked_t,
                    linked_o,
                    e,
                    p,
                )
                valid = False
            elif _is_upstream_link(model, r, p, t, o, linked_o):
                rates = {
                    float(value(model.emission_activity[r, e, i, linked_t, v, linked_o]))
                    for i, v in matching_ea
                }
                if len(rates) != 1:
                    logger.error(
                        'Upstream policy_emission_link (%s, %s, %s, %s -> %s, %s) '
                        'has multiple active emission rates %s in period %s; the rate cannot '
                        'be mapped unambiguously to covered fuel use',
                        policy,
                        r,
                        t,
                        o,
                        linked_t,
                        linked_o,
                        sorted(rates),
                        p,
                    )
                    valid = False
            if allocation <= 0:
                logger.error('policy_emission_link allocation must be greater than zero')
                valid = False

    return valid


def emission_performance_standard_constraint(
    model: TemoaModel,
    policy: str,
    r: Region,
    p: Period,
    e: Commodity,
) -> ExprLike:
    """Limit direct plus linked emissions per unit of covered available capacity."""
    covered = {
        (t, o)
        for row_policy, row_r, t, o in model.policy_technology
        if row_policy == policy and row_r == r and _covered_process_is_active(model, r, p, t, o)
    }

    if not covered:
        return Constraint.Skip

    direct_emissions = quicksum(_process_output_emissions(model, r, p, e, t, o) for t, o in covered)
    linked_emissions = quicksum(
        _linked_output_emissions(model, r, p, e, t, o, linked_t, linked_o)
        * value(model.policy_emission_link[row])
        for row in model.policy_emission_link.sparse_keys()
        for row_policy, row_r, t, o, linked_t, linked_o in [row]
        if row_policy == policy and row_r == r and (t, o) in covered
    )

    # Count capacity once per technology even if a policy covers several outputs.
    covered_techs = {t for t, _o in covered}
    allowed_emissions = value(model.emission_performance_standard[policy, r, p, e]) * quicksum(
        model.v_capacity_available_by_period_and_tech[r, p, t]
        * value(model.capacity_to_activity[r, t])
        for t in covered_techs
    )

    return direct_emissions + linked_emissions <= allowed_emissions
