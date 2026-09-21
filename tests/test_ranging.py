"""Sensitivity ranges, checked by re-solving rather than by trusting algebra.

`simplex.solve` reports, for every cost and every right-hand side, the interval
it can move through before the answer changes shape. scipy's `linprog` has no
ranging output to compare against, so the reference here is the solver itself,
run again on a perturbed program:

* Inside a cost range, the old x must still be optimal: the re-solved objective
  equals the new cost vector priced against the old x.
* Inside a right-hand-side range, the objective must move by exactly
  dual * delta.
* Just outside either range, on an instance where the range is known to be
  tight, the claim must fail. Without this half, a solver that reported
  (-inf, inf) for everything would pass.

The ranges are guaranteed rather than tight on a degenerate vertex, so the
"outside" checks run only where the vertex is non-degenerate in the relevant
sense, and the "inside" checks run everywhere.
"""

import math
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solver import simplex  # noqa: E402

from test_simplex import _random_instance  # noqa: E402

TOL = 1e-6
# How far past a range edge the "outside" checks step, as a fraction of the
# value being moved. Big enough to clear floating point, small enough that the
# step does not jump over the next breakpoint as well.
STEP = 1e-3


def _objective_at(c, x):
    return sum(ci * xi for ci, xi in zip(c, x))


def _primal_nondegenerate(result, A_ub, b_ub, n):
    """Every basic variable strictly positive.

    Approximated from the outside: count variables and slacks that are
    strictly positive. A non-degenerate vertex has exactly one per row.
    """
    positive = sum(1 for v in result.x if v > 1e-7)
    for row, b in zip(A_ub, b_ub):
        slack = b - sum(a * x for a, x in zip(row, result.x))
        if slack > 1e-7:
            positive += 1
    return positive == len(A_ub)


def _diet_instance(rng):
    """The shape PlateGap solves: free-but-capped goods, priced goods, floors.

    Generic random instances with positive costs are mostly solved at the
    origin, where every range is trivially wide. Floors that the free goods
    cannot meet alone force purchases, which is where ranges get interesting.
    """
    n_free, n_paid = rng.randint(1, 5), rng.randint(2, 6)
    n = n_free + n_paid
    c = [0.0] * n_free + [round(rng.uniform(0.5, 20.0), 3) for _ in range(n_paid)]
    caps = [round(rng.uniform(0.5, 4.0), 3) for _ in range(n)]
    witness = [cap * rng.uniform(0.3, 0.9) for cap in caps]

    A_ub, b_ub = [], []
    for _ in range(rng.randint(2, 6)):
        row = [round(rng.uniform(0.0, 8.0), 3) if rng.random() < 0.7 else 0.0
               for _ in range(n)]
        floor = sum(a * x for a, x in zip(row, witness)) * rng.uniform(0.5, 0.95)
        A_ub.append([-a for a in row])
        b_ub.append(-round(floor, 3))
    for j, cap in enumerate(caps):
        row = [0.0] * n
        row[j] = 1.0
        A_ub.append(row)
        b_ub.append(cap)
    return c, A_ub, b_ub


def _instance(seed, base):
    rng = random.Random(base + seed)
    if seed % 2:
        c, A_ub, b_ub = _diet_instance(rng)
        return c, A_ub, b_ub, [], []
    return _random_instance(rng, rng.randint(2, 9), rng.randint(2, 8), 0)


def _inside_points(low, high, value):
    """A few points inside [low, high], clipped to something finite."""
    lo = low if math.isfinite(low) else value - 10.0 * (abs(value) + 1.0)
    hi = high if math.isfinite(high) else value + 10.0 * (abs(value) + 1.0)
    return [lo + (hi - lo) * t for t in (0.02, 0.5, 0.98)]


@pytest.mark.parametrize("seed", range(80))
def test_old_solution_stays_optimal_across_each_cost_range(seed):
    c, A_ub, b_ub, _, _ = _instance(seed, 50_000)
    result = simplex.solve(c, A_ub, b_ub)
    if result.status != simplex.OPTIMAL:
        pytest.skip("instance not optimal")
    assert len(result.cost_ranges) == len(c)

    for k, (low, high) in enumerate(result.cost_ranges):
        assert low <= c[k] + TOL <= high + 2 * TOL, "range excludes the current cost"
        for value in _inside_points(low, high, c[k]):
            moved = list(c)
            moved[k] = value
            again = simplex.solve(moved, A_ub, b_ub)
            assert again.status == simplex.OPTIMAL
            assert again.objective == pytest.approx(
                _objective_at(moved, result.x), abs=1e-6, rel=1e-7), (
                "x stopped being optimal at c[%d] = %r, inside [%r, %r]"
                % (k, value, low, high))


@pytest.mark.parametrize("seed", range(80))
def test_cost_ranges_are_tight_on_a_nondegenerate_vertex(seed):
    c, A_ub, b_ub, _, _ = _instance(seed, 60_000)
    result = simplex.solve(c, A_ub, b_ub)
    if result.status != simplex.OPTIMAL:
        pytest.skip("instance not optimal")
    if not _primal_nondegenerate(result, A_ub, b_ub, len(c)):
        pytest.skip("degenerate vertex: ranges are guaranteed, not tight")

    checked = 0
    for k, (low, high) in enumerate(result.cost_ranges):
        for edge, direction in ((low, -1.0), (high, 1.0)):
            if not math.isfinite(edge):
                continue
            moved = list(c)
            moved[k] = edge + direction * STEP * (abs(edge) + 1.0)
            again = simplex.solve(moved, A_ub, b_ub)
            if again.status != simplex.OPTIMAL:
                continue  # stepping past the edge made it unbounded: also a change
            assert again.objective < _objective_at(moved, result.x) - 1e-9, (
                "x is still optimal past the reported edge of c[%d]" % k)
            checked += 1
    if not checked:
        pytest.skip("no finite edges on this instance")


@pytest.mark.parametrize("seed", range(80))
def test_objective_moves_by_the_dual_across_each_rhs_range(seed):
    c, A_ub, b_ub, _, _ = _instance(seed, 70_000)
    result = simplex.solve(c, A_ub, b_ub)
    if result.status != simplex.OPTIMAL:
        pytest.skip("instance not optimal")
    assert len(result.rhs_ranges_ub) == len(b_ub)

    for i, span in enumerate(result.rhs_ranges_ub):
        low, high = span
        assert low <= b_ub[i] + TOL <= high + 2 * TOL
        for value in _inside_points(low, high, b_ub[i]):
            moved = list(b_ub)
            moved[i] = value
            again = simplex.solve(c, A_ub, moved)
            assert again.status == simplex.OPTIMAL, (
                "b[%d] = %r is inside [%r, %r] but the program went %s"
                % (i, value, low, high, again.status))
            expected = result.objective + result.duals_ub[i] * (value - b_ub[i])
            assert again.objective == pytest.approx(expected, abs=1e-6, rel=1e-7), (
                "the dual on row %d stopped applying at %r, inside [%r, %r]"
                % (i, value, low, high))


def _dual_nondegenerate(result, c, A_ub, b_ub):
    """Every non-basic column has a strictly positive reduced cost.

    Read from the outside: a variable at zero whose cost range starts exactly
    at its cost has reduced cost zero, and a binding row with a zero dual has
    a slack whose reduced cost is zero. Either means another optimal vertex
    shares this one's duals, and the value function need not bend there.
    """
    for k, value in enumerate(result.x):
        if value <= 1e-7 and result.cost_ranges[k][0] > c[k] - 1e-7:
            return False
    for row, b, dual in zip(A_ub, b_ub, result.duals_ub):
        slack = b - sum(a * x for a, x in zip(row, result.x))
        if slack <= 1e-7 and abs(dual) <= 1e-7:
            return False
    return True


@pytest.mark.parametrize("seed", range(80))
def test_a_slack_row_is_free_until_exactly_where_it_starts_to_bind(seed):
    """A row with slack has dual zero, and that stays true until the row is
    pulled in to where x already sits. So its range must be exactly
    [activity, +inf) -- any narrower is wrong, any wider is a lie."""
    c, A_ub, b_ub, _, _ = _instance(seed, 80_000)
    result = simplex.solve(c, A_ub, b_ub)
    if result.status != simplex.OPTIMAL:
        pytest.skip("instance not optimal")
    if not _primal_nondegenerate(result, A_ub, b_ub, len(c)):
        pytest.skip("degenerate vertex")

    for i, (low, high) in enumerate(result.rhs_ranges_ub):
        activity = sum(a * x for a, x in zip(A_ub[i], result.x))
        if b_ub[i] - activity <= 1e-7:
            continue
        assert high == math.inf
        assert low == pytest.approx(activity, abs=1e-7, rel=1e-7)


@pytest.mark.parametrize("seed", range(80))
def test_a_binding_row_changes_price_just_past_its_range(seed):
    """Past the edge of a binding row's range, the value function bends, so
    the old dual's linear prediction must now be strictly optimistic. That has
    to hold only when the dual is unique, which is what is checked first."""
    c, A_ub, b_ub, _, _ = _instance(seed, 90_000)
    result = simplex.solve(c, A_ub, b_ub)
    if result.status != simplex.OPTIMAL:
        pytest.skip("instance not optimal")
    if not _dual_nondegenerate(result, c, A_ub, b_ub):
        pytest.skip("dual degenerate: another basis shares these prices")

    checked = 0
    for i, (low, high) in enumerate(result.rhs_ranges_ub):
        if abs(result.duals_ub[i]) <= 1e-7:
            continue
        for edge, direction in ((low, -1.0), (high, 1.0)):
            if not math.isfinite(edge):
                continue
            moved = list(b_ub)
            moved[i] = edge + direction * STEP * (abs(edge) + 1.0)
            again = simplex.solve(c, A_ub, moved)
            checked += 1
            if again.status != simplex.OPTIMAL:
                continue  # infeasible past the edge: the price certainly changed
            predicted = result.objective + result.duals_ub[i] * (moved[i] - b_ub[i])
            assert again.objective > predicted + 1e-9, (
                "row %d moved past its range and the old price still held" % i)
    if not checked:
        pytest.skip("no binding rows with a finite edge")


def test_a_textbook_range():
    """A diet problem small enough to check by hand.

    minimise 2a + 3b  s.t.  a + b >= 4,  a + 3b >= 6,  a, b >= 0.
    Optimum a = 3, b = 1, cost 9. The binding rows cross at that vertex, and
    the vertex stays optimal while c_a / c_b stays between their slopes, 1/3
    and 1: c_a in [1, 3] with c_b = 3, and c_b in [2, 6] with c_a = 2.
    """
    result = simplex.solve([2.0, 3.0], [[-1.0, -1.0], [-1.0, -3.0]], [-4.0, -6.0])
    assert result.x == pytest.approx([3.0, 1.0])
    (a_low, a_high), (b_low, b_high) = result.cost_ranges
    assert (a_low, a_high) == (pytest.approx(1.0), pytest.approx(3.0))
    assert (b_low, b_high) == (pytest.approx(2.0), pytest.approx(6.0))

    # First floor: a + b >= 4 carries dual 1.5 and stays binding from 2 to 6.
    low, high = result.rhs_ranges_ub[0]
    assert (-high, -low) == (pytest.approx(2.0), pytest.approx(6.0))


def test_a_dependent_row_reports_no_range():
    c = [3.0, 2.0, 4.0]
    A_eq = [[1.0, 1.0, 0.0], [0.0, 1.0, 1.0], [1.0, 2.0, 1.0]]
    b_eq = [4.0, 6.0, 10.0]
    result = simplex.solve(c, [[1.0, 0.0, 0.0], [0.0, 0.0, 1.0]], [3.0, 8.0],
                           A_eq, b_eq)
    assert result.status == simplex.OPTIMAL
    assert len(result.rhs_ranges_eq) == 3
    assert sum(1 for r in result.rhs_ranges_eq if r is None) == 1
