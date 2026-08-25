from pyomo.environ import ConcreteModel, Param, RangeSet

from temoa.components.utils import explicit_param_keys


def test_explicit_param_keys_avoids_defaulted_cartesian_product() -> None:
    model = ConcreteModel()
    model.indices = RangeSet(1, 1_000)
    model.sparse_param = Param(
        model.indices,
        model.indices,
        default=1,
        initialize={(1, 1): 2},
    )

    assert set(explicit_param_keys(model.sparse_param)) == {(1, 1)}
    assert model.sparse_param[2, 2] == 1
    assert set(explicit_param_keys(model.sparse_param)) == {(1, 1)}
