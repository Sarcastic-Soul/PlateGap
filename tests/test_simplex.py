"""Differential test: our pure-Python simplex against scipy.optimize.linprog.

scipy is a development dependency only. It never ships to Lambda -- it exists
so that the hand-rolled solver can be held to a reference implementation on a
few hundred randomly generated instances every time the code changes.

Three things are checked on each instance:

1. Feasibility status agrees.
2. Optimal objective values agree.
3. Our duals agree with scipy's marginals, and satisfy complementary
   slackness against our own primal solution.

Point 3 is the one that matters for PlateGap, because the duals are what the
product actually shows the user.
"""

import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver import simplex  # noqa: E402

scipy_linprog = pytest.importorskip("scipy.optimize").linprog

OBJECTIVE_TOL = 1e-6
DUAL_TOL = 1e-5


def _scipy_solve(c, A_ub, b_ub, A_eq, b_eq):
    return scipy_linprog(
        c,
        A_ub=A_ub or None,
        b_ub=b_ub or None,
        A_eq=A_eq or None,
        b_eq=b_eq or None,
        bounds=[(0, None)] * len(c),
        method="highs",
    )


def _random_instance(rng, n_vars, n_ub, n_eq, force_feasible=True):
    """Build a random LP.

    When `force_feasible`, right-hand sides are derived from a known feasible
    point so the instance is guaranteed solvable -- otherwise most random
    instances come back infeasible and the interesting paths go untested.
    """
    c = [round(rng.uniform(0.1, 10.0), 3) for _ in range(n_vars)]
    witness = [round(rng.uniform(0.0, 5.0), 3) for _ in range(n_vars)]

    A_ub, b_ub = [], []
    for _ in range(n_ub):
        row = [round(rng.uniform(-3.0, 5.0), 3) for _ in range(n_vars)]
        A_ub.append(row)
        value = sum(a * x for a, x in zip(row, witness))
        b_ub.append(round(value + rng.uniform(0.5, 6.0), 3) if force_feasible
                    else round(rng.uniform(-5.0, 10.0), 3))

    A_eq, b_eq = [], []
    for _ in range(n_eq):
        row = [round(rng.uniform(-3.0, 5.0), 3) for _ in range(n_vars)]
        A_eq.append(row)
        value = sum(a * x for a, x in zip(row, witness))
        b_eq.append(round(value, 3) if force_feasible
                    else round(rng.uniform(-5.0, 10.0), 3))

    return c, A_ub, b_ub, A_eq, b_eq


def _assert_matches_scipy(c, A_ub, b_ub, A_eq, b_eq):
    ours = simplex.solve(c, A_ub, b_ub, A_eq, b_eq)
    theirs = _scipy_solve(c, A_ub, b_ub, A_eq, b_eq)

    if theirs.status == 2:  # infeasible
        assert ours.status == simplex.INFEASIBLE, (
            "scipy says infeasible, we say %s" % ours.status)
        return
    if theirs.status == 3:  # unbounded
        assert ours.status == simplex.UNBOUNDED, (
            "scipy says unbounded, we say %s" % ours.status)
        return

    assert theirs.status == 0, "scipy returned an unexpected status"
    assert ours.status == simplex.OPTIMAL, (
        "scipy solved it, we returned %s" % ours.status)

    assert ours.objective == pytest.approx(theirs.fun, abs=OBJECTIVE_TOL, rel=1e-7), (
        "objective mismatch: ours %.10g, scipy %.10g" % (ours.objective, theirs.fun))

    # Primal feasibility of our own answer, checked independently of scipy.
    for row, rhs in zip(A_ub, b_ub):
        assert sum(a * x for a, x in zip(row, ours.x)) <= rhs + 1e-6
    for row, rhs in zip(A_eq, b_eq):
        assert sum(a * x for a, x in zip(row, ours.x)) == pytest.approx(rhs, abs=1e-6)
    assert all(x >= -1e-9 for x in ours.x)

    if A_ub:
        for i, (mine, reference) in enumerate(
                zip(ours.duals_ub, theirs.ineqlin.marginals)):
            assert mine == pytest.approx(reference, abs=DUAL_TOL), (
                "inequality dual %d: ours %.8g, scipy %.8g" % (i, mine, reference))
    if A_eq:
        for i, (mine, reference) in enumerate(
                zip(ours.duals_eq, theirs.eqlin.marginals)):
            assert mine == pytest.approx(reference, abs=DUAL_TOL), (
                "equality dual %d: ours %.8g, scipy %.8g" % (i, mine, reference))

    return ours


def test_trivial_origin_is_optimal():
    result = simplex.solve([1.0, 2.0], [[1.0, 1.0]], [5.0])
    assert result.status == simplex.OPTIMAL
    assert result.objective == pytest.approx(0.0)
    assert result.x == pytest.approx([0.0, 0.0])


def test_textbook_diet_problem():
    """Two foods, two nutrient floors. Hand-checkable."""
    # minimise 2*x0 + 3*x1  s.t.  x0 + 2*x1 >= 10,  3*x0 + x1 >= 12
    # expressed as <= by negation
    c = [2.0, 3.0]
    A_ub = [[-1.0, -2.0], [-3.0, -1.0]]
    b_ub = [-10.0, -12.0]
    result = _assert_matches_scipy(c, A_ub, b_ub, [], [])
    assert result.status == simplex.OPTIMAL
    # Both floors bind, so both duals are strictly negative.
    assert all(d < 0 for d in result.duals_ub)


def test_detects_infeasible():
    # x >= 5 and x <= 1 simultaneously.
    result = simplex.solve([1.0], [[-1.0], [1.0]], [-5.0, 1.0])
    assert result.status == simplex.INFEASIBLE


def test_detects_unbounded():
    # minimise -x with nothing bounding x above.
    result = simplex.solve([-1.0], [[-1.0]], [0.0])
    assert result.status == simplex.UNBOUNDED


def test_equality_constraints_carry_duals():
    c = [1.0, 1.0, 1.0]
    A_eq = [[1.0, 1.0, 0.0], [0.0, 1.0, 1.0]]
    b_eq = [4.0, 6.0]
    result = _assert_matches_scipy(c, [], [], A_eq, b_eq)
    assert len(result.duals_eq) == 2


def test_degenerate_instance_does_not_cycle():
    """A deliberately degenerate LP -- several constraints meet at one vertex."""
    c = [1.0, 1.0]
    A_ub = [[1.0, 1.0], [1.0, 1.0], [2.0, 2.0], [-1.0, 0.0]]
    b_ub = [4.0, 4.0, 8.0, 0.0]
    result = simplex.solve(c, A_ub, b_ub)
    assert result.status == simplex.OPTIMAL
    assert result.iterations < simplex.MAX_ITERATIONS


@pytest.mark.parametrize("seed", range(120))
def test_random_inequality_instances(seed):
    rng = random.Random(seed)
    c, A_ub, b_ub, _, _ = _random_instance(
        rng, rng.randint(2, 12), rng.randint(1, 10), 0)
    _assert_matches_scipy(c, A_ub, b_ub, [], [])


@pytest.mark.parametrize("seed", range(60))
def test_random_mixed_instances(seed):
    rng = random.Random(10_000 + seed)
    c, A_ub, b_ub, A_eq, b_eq = _random_instance(
        rng, rng.randint(3, 10), rng.randint(1, 6), rng.randint(1, 3))
    _assert_matches_scipy(c, A_ub, b_ub, A_eq, b_eq)


@pytest.mark.parametrize("seed", range(40))
def test_random_possibly_infeasible_instances(seed):
    """Right-hand sides are not derived from a witness, so many of these are
    infeasible. Agreement on *status* is the point."""
    rng = random.Random(20_000 + seed)
    c, A_ub, b_ub, A_eq, b_eq = _random_instance(
        rng, rng.randint(2, 8), rng.randint(2, 8), rng.randint(0, 2),
        force_feasible=False)
    _assert_matches_scipy(c, A_ub, b_ub, A_eq, b_eq)


@pytest.mark.parametrize("seed", range(40))
def test_complementary_slackness(seed):
    """For every inequality row, either it binds or its dual is zero.

    This is checked against our own primal and dual output, with no reference
    implementation involved -- it is an internal consistency property that must
    hold for any correct solve.
    """
    rng = random.Random(30_000 + seed)
    c, A_ub, b_ub, _, _ = _random_instance(
        rng, rng.randint(3, 10), rng.randint(2, 8), 0)
    result = simplex.solve(c, A_ub, b_ub)
    if result.status != simplex.OPTIMAL:
        pytest.skip("instance not optimal")

    for row, rhs, dual in zip(A_ub, b_ub, result.duals_ub):
        slack = rhs - sum(a * x for a, x in zip(row, result.x))
        assert slack >= -1e-6, "primal infeasible"
        assert dual <= 1e-6, "a <= row should have a non-positive marginal"
        assert abs(slack * dual) < 1e-5, (
            "complementary slackness violated: slack %.8g, dual %.8g" % (slack, dual))


def test_nutrient_shaped_instance_matches_scipy():
    """The shape PlateGap actually solves: free-but-capped goods alongside
    priced goods, with nutrient floors."""
    # x0, x1 are mess servings (cost 0, capped); x2, x3 are purchases (priced).
    c = [0.0, 0.0, 8.0, 12.0]
    A_ub = [
        # nutrient floors, negated into <= form
        [-6.0, -3.0, -13.0, -2.0],   # protein >= 55
        [-1.2, -0.8, -1.0, -4.5],    # iron >= 18
        # serving caps on the free items
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
    ]
    b_ub = [-55.0, -18.0, 3.0, 2.0]
    result = _assert_matches_scipy(c, A_ub, b_ub, [], [])
    assert result.objective > 0, "the free items alone should not suffice"
