"""Two-phase simplex with dual extraction. Pure Python, no dependencies.

Solves the linear program

    minimize    c . x
    subject to  A_ub . x <= b_ub
                A_eq . x == b_eq
                x >= 0

and returns both the primal solution and the dual values, because in PlateGap
the duals *are* the product: the dual on a nutrient floor is the marginal
out-of-pocket cost of requiring one more unit of that nutrient.

Why hand-rolled rather than scipy: this runs in a Lambda whose Python runtime
ships boto3 and nothing else. Vendoring scipy would mean a layer or a container
image for a problem that is a few dozen variables wide. `tests/test_simplex.py`
checks this implementation against `scipy.optimize.linprog` on randomly
generated instances, so the shortcut costs us nothing in confidence.

Implementation notes
--------------------
Dense tableau, two-phase. Every constraint row gets a *marker column* whose
column vector is the unit vector e_i -- the slack for a `<=` row, the artificial
for a `>=` or `==` row. Artificial columns are kept (but barred from re-entering
the basis) through phase two purely so that every row, whatever its kind, has a
marker column to read its dual off. See `_extract_duals`.

Dantzig's rule picks the entering column, falling back to Bland's rule once the
iteration count suggests we may be cycling on a degenerate vertex.
"""

from __future__ import annotations

TOL = 1e-9
MAX_ITERATIONS = 20000
BLAND_AFTER = 2000

OPTIMAL = "optimal"
INFEASIBLE = "infeasible"
UNBOUNDED = "unbounded"
ITERATION_LIMIT = "iteration_limit"

LE = "<="
GE = ">="
EQ = "=="


class LPResult:
    """Outcome of a solve.

    Attributes:
        status: one of OPTIMAL, INFEASIBLE, UNBOUNDED, ITERATION_LIMIT.
        x: primal solution, length n. None unless status is OPTIMAL.
        objective: optimal value of c . x. None unless status is OPTIMAL.
        duals_ub: one dual per A_ub row, in scipy's marginal convention --
            d(objective)/d(b_i), so <= 0 for a binding `<=` row.
        duals_eq: one dual per A_eq row, same convention.
        iterations: total pivots across both phases.
    """

    __slots__ = ("status", "x", "objective", "duals_ub", "duals_eq", "iterations")

    def __init__(self, status, x=None, objective=None, duals_ub=None,
                 duals_eq=None, iterations=0):
        self.status = status
        self.x = x
        self.objective = objective
        self.duals_ub = duals_ub or []
        self.duals_eq = duals_eq or []
        self.iterations = iterations

    def __repr__(self):
        if self.status != OPTIMAL:
            return "LPResult(status=%r)" % self.status
        return "LPResult(status='optimal', objective=%.6g, iterations=%d)" % (
            self.objective, self.iterations)


class _Tableau:
    """Dense simplex tableau.

    Row i of `rows` holds the coefficients of constraint i followed by its
    right-hand side. `cost` holds the reduced costs d_j = c_j - z_j followed by
    the negated objective value. `basis[i]` is the column currently basic in
    row i.
    """

    __slots__ = ("rows", "cost", "basis", "n_cols", "n_rows")

    def __init__(self, rows, basis, n_cols):
        self.rows = rows
        self.basis = basis
        self.n_cols = n_cols
        self.n_rows = len(rows)
        self.cost = [0.0] * (n_cols + 1)

    def set_objective(self, costs):
        """Install `costs` and price it out against the current basis.

        Leaves `cost[j]` holding the reduced cost of column j, and `cost[-1]`
        holding minus the current objective value.
        """
        self.cost = list(costs) + [0.0]
        for i, basic_col in enumerate(self.basis):
            cb = costs[basic_col]
            if cb == 0.0:
                continue
            row = self.rows[i]
            for j in range(self.n_cols + 1):
                self.cost[j] -= cb * row[j]

    def pivot(self, r, c):
        """Make column c basic in row r."""
        rows = self.rows
        pivot_row = rows[r]
        pivot_value = pivot_row[c]
        inv = 1.0 / pivot_value
        for j in range(self.n_cols + 1):
            pivot_row[j] *= inv
        # Exact 1.0 guards against drift accumulating on repeated pivots.
        pivot_row[c] = 1.0

        for i, row in enumerate(rows):
            if i == r:
                continue
            factor = row[c]
            if factor == 0.0:
                continue
            for j in range(self.n_cols + 1):
                row[j] -= factor * pivot_row[j]
            row[c] = 0.0

        factor = self.cost[c]
        if factor != 0.0:
            cost = self.cost
            for j in range(self.n_cols + 1):
                cost[j] -= factor * pivot_row[j]
            cost[c] = 0.0

        self.basis[r] = c

    def choose_entering(self, forbidden, use_bland):
        """Index of a column with negative reduced cost, or None if optimal."""
        cost = self.cost
        if use_bland:
            for j in range(self.n_cols):
                if not forbidden[j] and cost[j] < -TOL:
                    return j
            return None

        best_j, best_value = None, -TOL
        for j in range(self.n_cols):
            if forbidden[j]:
                continue
            if cost[j] < best_value:
                best_value, best_j = cost[j], j
        return best_j

    def choose_leaving(self, c, use_bland):
        """Row to pivot on for entering column c, or None if unbounded.

        Ties in the minimum ratio are broken toward the smallest basic column
        index, which is Bland's rule and is what stops us cycling.
        """
        best_r = None
        best_ratio = None
        for i, row in enumerate(self.rows):
            coefficient = row[c]
            if coefficient <= TOL:
                continue
            ratio = row[self.n_cols] / coefficient
            if best_ratio is None or ratio < best_ratio - TOL:
                best_ratio, best_r = ratio, i
            elif abs(ratio - best_ratio) <= TOL and best_r is not None:
                if use_bland and self.basis[i] < self.basis[best_r]:
                    best_r = i
                elif not use_bland and self.basis[i] < self.basis[best_r]:
                    best_r = i
        return best_r

    def run(self, forbidden, iterations_so_far=0):
        """Pivot to optimality. Returns (status, iterations)."""
        iterations = 0
        while True:
            total = iterations_so_far + iterations
            if total >= MAX_ITERATIONS:
                return ITERATION_LIMIT, iterations
            use_bland = total >= BLAND_AFTER

            c = self.choose_entering(forbidden, use_bland)
            if c is None:
                return OPTIMAL, iterations

            r = self.choose_leaving(c, use_bland)
            if r is None:
                return UNBOUNDED, iterations

            self.pivot(r, c)
            iterations += 1


def _build(c, A_ub, b_ub, A_eq, b_eq):
    """Assemble the phase-one tableau.

    Returns (tableau, n, marker_ub, marker_eq, artificial_columns, signs)
    where the marker lists give, for each original constraint row, the column
    whose coefficient vector is e_i -- the columns duals are read from -- and
    `signs` records whether a row was negated during normalisation, since
    negating a row also negates its marginal.
    """
    n = len(c)
    rows_spec = []  # (coefficients, rhs, kind)
    for coefficients, rhs in zip(A_ub, b_ub):
        rows_spec.append((list(coefficients), float(rhs), LE))
    for coefficients, rhs in zip(A_eq, b_eq):
        rows_spec.append((list(coefficients), float(rhs), EQ))

    # A negative right-hand side is made positive by negating the row, which
    # flips the sense of an inequality. `sign` remembers that we did it: the
    # marginal of a negated row is the negation of the marginal we will read
    # out of the tableau.
    normalised = []
    signs = []
    for coefficients, rhs, kind in rows_spec:
        sign = 1.0
        if rhs < 0:
            coefficients = [-a for a in coefficients]
            rhs = -rhs
            sign = -1.0
            if kind == LE:
                kind = GE
            elif kind == GE:
                kind = LE
        normalised.append((coefficients, rhs, kind))
        signs.append(sign)

    n_rows = len(normalised)
    n_slack = sum(1 for _, _, kind in normalised if kind in (LE, GE))
    n_artificial = sum(1 for _, _, kind in normalised if kind in (GE, EQ))
    n_cols = n + n_slack + n_artificial

    rows = [[0.0] * (n_cols + 1) for _ in range(n_rows)]
    basis = [-1] * n_rows
    artificial_columns = []
    markers = [-1] * n_rows

    slack_cursor = n
    artificial_cursor = n + n_slack

    for i, (coefficients, rhs, kind) in enumerate(normalised):
        row = rows[i]
        for j, a in enumerate(coefficients):
            row[j] = float(a)
        row[n_cols] = rhs

        if kind == LE:
            row[slack_cursor] = 1.0
            basis[i] = slack_cursor
            markers[i] = slack_cursor  # slack column is +e_i
            slack_cursor += 1
        elif kind == GE:
            row[slack_cursor] = -1.0  # surplus
            slack_cursor += 1
            row[artificial_cursor] = 1.0
            basis[i] = artificial_cursor
            markers[i] = artificial_cursor  # artificial column is +e_i
            artificial_columns.append(artificial_cursor)
            artificial_cursor += 1
        else:  # EQ
            row[artificial_cursor] = 1.0
            basis[i] = artificial_cursor
            markers[i] = artificial_cursor
            artificial_columns.append(artificial_cursor)
            artificial_cursor += 1

    tableau = _Tableau(rows, basis, n_cols)
    n_ub = len(A_ub)
    return (tableau, n, markers[:n_ub], markers[n_ub:], artificial_columns,
            signs[:n_ub], signs[n_ub:])


def _drive_out_artificials(tableau, artificial_set):
    """Pivot artificial variables out of the basis where the row allows it.

    A row that cannot be cleared is linearly dependent on the others; it is
    dropped, which is harmless because it carries no information.
    """
    for i in range(tableau.n_rows - 1, -1, -1):
        if tableau.basis[i] not in artificial_set:
            continue
        row = tableau.rows[i]
        replacement = None
        for j in range(tableau.n_cols):
            if j in artificial_set:
                continue
            if abs(row[j]) > TOL:
                replacement = j
                break
        if replacement is not None:
            tableau.pivot(i, replacement)
        else:
            tableau.rows.pop(i)
            tableau.basis.pop(i)
            tableau.n_rows -= 1


def _extract_duals(tableau, markers, signs):
    """Read one dual per row off its marker column.

    Each marker column has coefficient vector e_i, so its reduced cost is
    d = c_marker - z_marker = 0 - y_i = -y_i. Reporting in scipy's marginal
    convention -- d(objective)/d(b_i), non-positive for a binding `<=` row --
    means negating that, and negating again for any row that normalisation
    flipped, because scaling a row by -1 scales its marginal by -1 too.
    """
    return [-sign * tableau.cost[m] for m, sign in zip(markers, signs)]


def solve(c, A_ub=None, b_ub=None, A_eq=None, b_eq=None):
    """Minimize c . x subject to A_ub x <= b_ub, A_eq x == b_eq, x >= 0.

    Args:
        c: objective coefficients, length n.
        A_ub, b_ub: inequality rows and right-hand sides. May be None.
        A_eq, b_eq: equality rows and right-hand sides. May be None.

    Returns:
        LPResult. Duals follow scipy's marginal convention, so a binding `<=`
        row has a dual <= 0 and relaxing its right-hand side by one unit changes
        the objective by that amount.
    """
    A_ub = [list(row) for row in (A_ub or [])]
    b_ub = list(b_ub or [])
    A_eq = [list(row) for row in (A_eq or [])]
    b_eq = list(b_eq or [])
    c = [float(v) for v in c]

    if len(A_ub) != len(b_ub) or len(A_eq) != len(b_eq):
        raise ValueError("constraint matrix and right-hand side lengths differ")

    n = len(c)
    for row in A_ub + A_eq:
        if len(row) != n:
            raise ValueError("constraint row width does not match len(c)")

    if not A_ub and not A_eq:
        # Unconstrained below zero: optimal at the origin unless some cost is
        # negative, in which case that variable runs away.
        if any(v < -TOL for v in c):
            return LPResult(UNBOUNDED)
        return LPResult(OPTIMAL, [0.0] * n, 0.0, [], [], 0)

    (tableau, n, marker_ub, marker_eq, artificial_columns,
     signs_ub, signs_eq) = _build(c, A_ub, b_ub, A_eq, b_eq)
    artificial_set = set(artificial_columns)

    # Phase one: minimise the sum of the artificial variables.
    phase_one_costs = [0.0] * tableau.n_cols
    for j in artificial_columns:
        phase_one_costs[j] = 1.0
    tableau.set_objective(phase_one_costs)

    forbidden = [False] * tableau.n_cols
    status, iterations = tableau.run(forbidden)
    if status == ITERATION_LIMIT:
        return LPResult(ITERATION_LIMIT, iterations=iterations)

    infeasibility = -tableau.cost[tableau.n_cols]
    if infeasibility > 1e-7:
        return LPResult(INFEASIBLE, iterations=iterations)

    _drive_out_artificials(tableau, artificial_set)

    # Phase two: the real objective. Artificial columns stay in the tableau so
    # that equality and `>=` rows still have a marker column to read a dual
    # from, but they are barred from re-entering the basis.
    phase_two_costs = [0.0] * tableau.n_cols
    for j in range(n):
        phase_two_costs[j] = c[j]
    tableau.set_objective(phase_two_costs)

    for j in artificial_columns:
        forbidden[j] = True

    status, more_iterations = tableau.run(forbidden, iterations)
    iterations += more_iterations
    if status == UNBOUNDED:
        return LPResult(UNBOUNDED, iterations=iterations)
    if status == ITERATION_LIMIT:
        return LPResult(ITERATION_LIMIT, iterations=iterations)

    x = [0.0] * n
    for i, basic_col in enumerate(tableau.basis):
        if basic_col < n:
            x[basic_col] = tableau.rows[i][tableau.n_cols]

    objective = sum(c[j] * x[j] for j in range(n))

    duals_ub = _extract_duals(tableau, marker_ub, signs_ub)
    duals_eq = _extract_duals(tableau, marker_eq, signs_eq)

    return LPResult(OPTIMAL, x, objective, duals_ub, duals_eq, iterations)
