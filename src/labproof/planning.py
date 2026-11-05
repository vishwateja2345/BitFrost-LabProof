"""Bounded Bayesian experiment planning over a declared synthetic hypothesis model.

Pure host code: no I/O, execution, network or model calls. A recommendation only ranks
experiments the caller already declared; it never creates or authorizes an operation.
"""
from dataclasses import dataclass
import math

from .contracts import ID_RE, require

MAX_HYPOTHESES = 8
MAX_EXPERIMENTS = 12
MAX_OUTCOMES = 6
MAX_HORIZON = 2
MAX_COST = 1000.0
MAX_TOTAL_COST = MAX_COST * MAX_EXPERIMENTS
DECISION_THRESHOLD = 0.8
REQUEST_VERSION = "planning-request-1"
RESULT_VERSION = "planning-result-1"
MODES = ("fixed", "random", "greedy", "lookahead")
CLI_MODES = ("greedy", "lookahead")
LIMITATIONS = (
    "Hypotheses, likelihoods and trust rates are declared model inputs, not learned or validated against real targets.",
    "A posterior is a model-conditional belief, never a finding; static signals alone cannot confirm anything.",
    "Trust flags come from the host's registry, never from observation text, and no observation text is read.",
    "Selecting an experiment authorizes nothing: operations stay confined to the caller's reviewed catalogue.",
)


@dataclass(frozen=True, slots=True)
class Experiment:
    id: str
    cost: float
    taintable: bool
    outcomes: tuple[str, ...]
    likelihood: tuple[tuple[float, ...], ...]  # [hypothesis][outcome], rows sum to 1


@dataclass(frozen=True, slots=True)
class Model:
    hypotheses: tuple[str, ...]
    prior: tuple[float, ...]
    experiments: tuple[Experiment, ...]


@dataclass(frozen=True, slots=True)
class Policy:
    mode: str = "greedy"
    cost_weight: float = 0.035
    horizon: int = 2
    untrusted_reliability: float = 0.0  # chance an untrusted-flagged observation is genuine
    taint_rate: float = 0.0  # assumed chance a taintable experiment returns untrusted output
    order: tuple[str, ...] = ()  # fixed mode only


HYPOTHESES = ("none", "object_authorization", "html_reflection", "error_disclosure", "unavailable")
PROBES = tuple(zip(("probe_authorization", "probe_reflection", "probe_disclosure", "probe_availability"), range(1, 5)))


def default_model(probe_hit=0.89, probe_false=0.07, static_accuracy=0.79, inventory_accuracy=0.61):
    """The synthetic fault-attribution model over LabProof's seeded check classes."""
    n = len(HYPOTHESES)
    experiments = [Experiment(name, 1.0, False, ("positive", "negative"),
                              tuple((probe_hit, 1.0 - probe_hit) if h == target else (probe_false, 1.0 - probe_false) for h in range(n)))
                   for name, target in PROBES]
    for name, cost, accuracy, taintable in (("static_signal", 0.5, static_accuracy, True), ("inventory_signal", 1.5, inventory_accuracy, False)):
        experiments.append(Experiment(name, cost, taintable, HYPOTHESES,
                                      tuple(tuple(accuracy if o == h else (1.0 - accuracy) / (n - 1) for o in range(n)) for h in range(n))))
    return Model(HYPOTHESES, tuple(1.0 / n for _ in range(n)), tuple(experiments))


def example_request():
    return {"schema_version": REQUEST_VERSION, "model": model_dict(default_model()), "observations": [],
            "policy": {"mode": "lookahead", "cost_weight": 0.035, "horizon": 2, "untrusted_reliability": 0.25, "taint_rate": 0.3},
            "budget": {"experiments": 3, "cost": 3.0}}


def _number(value, label, low, high):
    require(type(value) in (int, float) and low <= value <= high, "Invalid " + label)
    return float(value)


def _ids(value, label, low, high):
    require(type(value) is list and low <= len(value) <= high, "Invalid " + label)
    require(all(type(v) is str and ID_RE.fullmatch(v) for v in value) and len(set(value)) == len(value), "Invalid " + label + " identifiers")
    return tuple(value)


def build_model(value):
    require(type(value) is dict and set(value) == {"hypotheses", "prior", "experiments"}, "Invalid planning model")
    names = _ids(value["hypotheses"], "hypotheses", 2, MAX_HYPOTHESES)
    require(type(value["prior"]) is list and len(value["prior"]) == len(names), "Invalid prior")
    prior = tuple(_number(p, "prior probability", 0.0, 1.0) for p in value["prior"])
    require(math.isclose(sum(prior), 1.0, abs_tol=1e-9), "Prior must sum to 1")
    raw = value["experiments"]
    require(type(raw) is list and 1 <= len(raw) <= MAX_EXPERIMENTS, "Invalid experiments")
    experiments = []
    for entry in raw:
        require(type(entry) is dict and set(entry) == {"id", "cost", "taintable", "outcomes", "likelihood"}, "Invalid experiment")
        require(type(entry["id"]) is str and ID_RE.fullmatch(entry["id"]), "Invalid experiment identifier")
        require(type(entry["taintable"]) is bool, "Invalid taintable flag")
        outcomes = _ids(entry["outcomes"], "outcomes", 2, MAX_OUTCOMES)
        table = entry["likelihood"]
        require(type(table) is dict and set(table) == set(names), "Likelihood must cover exactly the declared hypotheses")
        rows = []
        for name in names:
            row = table[name]
            require(type(row) is list and len(row) == len(outcomes), "Likelihood row does not match outcomes")
            row = tuple(_number(p, "likelihood", 0.0, 1.0) for p in row)
            require(math.isclose(sum(row), 1.0, abs_tol=1e-9), "Likelihood rows must sum to 1")
            rows.append(row)
        experiments.append(Experiment(entry["id"], _number(entry["cost"], "cost", 1e-6, MAX_COST), entry["taintable"], outcomes, tuple(rows)))
    require(len({e.id for e in experiments}) == len(experiments), "Duplicate experiment identifiers")
    return Model(names, prior, tuple(experiments))


def model_dict(model):
    return {"hypotheses": list(model.hypotheses), "prior": list(model.prior),
            "experiments": [{"id": e.id, "cost": e.cost, "taintable": e.taintable, "outcomes": list(e.outcomes),
                             "likelihood": {h: list(row) for h, row in zip(model.hypotheses, e.likelihood)}}
                            for e in model.experiments]}


def build_policy(value):
    fields = {"mode", "cost_weight", "horizon", "untrusted_reliability", "taint_rate"}
    require(type(value) is dict and set(value) == fields, "Invalid planning policy")
    require(value["mode"] in CLI_MODES, "Policy mode must be greedy or lookahead")
    require(type(value["horizon"]) is int and 1 <= value["horizon"] <= MAX_HORIZON, "Invalid lookahead horizon")
    return Policy(value["mode"], _number(value["cost_weight"], "cost weight", 0.0, 10.0), value["horizon"],
                  _number(value["untrusted_reliability"], "untrusted reliability", 0.0, 1.0),
                  _number(value["taint_rate"], "taint rate", 0.0, 1.0))


def entropy(belief):
    return -sum(p * math.log2(p) for p in belief if p > 0)


def _rows(experiment, reliability, trusted):
    """P(outcome | hypothesis) as seen through the source's provenance channel."""
    if trusted:
        return experiment.likelihood
    noise = (1.0 - reliability) / len(experiment.outcomes)
    return tuple(tuple(reliability * p + noise for p in row) for row in experiment.likelihood)


def observe(model, belief, index, outcome, trusted, reliability):
    """Bayes update; an untrusted observation passes through the reliability channel."""
    weights = [b * row[outcome] for b, row in zip(belief, _rows(model.experiments[index], reliability, trusted))]
    total = sum(weights)
    require(total > 0, "Observation is impossible under every hypothesis with nonzero belief")
    return tuple(w / total for w in weights)


def _branches(belief, experiment, taint_rate, reliability):
    """(probability, posterior) for every (trust flag, outcome) that can occur."""
    taint = taint_rate if experiment.taintable else 0.0
    result = []
    for trusted, flag_probability in ((True, 1.0 - taint), (False, taint)):
        if flag_probability <= 0.0:
            continue
        rows = _rows(experiment, reliability, trusted)
        for o in range(len(experiment.outcomes)):
            q = sum(b * row[o] for b, row in zip(belief, rows))
            if q > 0.0:
                result.append((flag_probability * q, tuple(b * row[o] / q for b, row in zip(belief, rows))))
    return result


def expected_gain(belief, experiment, taint_rate=0.0, reliability=0.0):
    """Expected entropy reduction in bits, averaged over trust flag and outcome."""
    after = sum(p * entropy(child) for p, child in _branches(belief, experiment, taint_rate, reliability))
    return max(entropy(belief) - after, 0.0)


def _value(model, belief, remaining, left, cost_left, depth, policy, memo):
    """Expectimax utility with an explicit option to stop (utility zero)."""
    if depth == 0 or left <= 0:
        return 0.0
    key = (tuple(round(b, 10) for b in belief), remaining, left, depth,
           None if cost_left is None else round(cost_left, 9))
    if key not in memo:
        best, here = 0.0, entropy(belief)
        for i in remaining:
            experiment = model.experiments[i]
            if cost_left is not None and experiment.cost > cost_left + 1e-9:
                continue
            branches = _branches(belief, experiment, policy.taint_rate, policy.untrusted_reliability)
            score = here - sum(p * entropy(c) for p, c in branches) - policy.cost_weight * experiment.cost
            if depth > 1:
                rest = tuple(j for j in remaining if j != i)
                next_cost = None if cost_left is None else cost_left - experiment.cost
                score += sum(p * _value(model, c, rest, left - 1, next_cost, depth - 1, policy, memo) for p, c in branches)
            best = max(best, score)
        memo[key] = best
    return memo[key]


def _feasible(model, done, left, cost_left):
    if left <= 0:
        return []
    return [i for i, e in enumerate(model.experiments)
            if i not in done and (cost_left is None or e.cost <= cost_left + 1e-9)]


def rank(model, belief, done, policy, left, cost_left=None):
    """Feasible experiments best first: (index, expected gain, utility, score)."""
    rows, memo = [], {}
    horizon = min(policy.horizon, MAX_HORIZON) if policy.mode == "lookahead" else 1
    for i in _feasible(model, done, left, cost_left):
        experiment = model.experiments[i]
        branches = _branches(belief, experiment, policy.taint_rate, policy.untrusted_reliability)
        gain = max(entropy(belief) - sum(p * entropy(c) for p, c in branches), 0.0)
        utility = gain - policy.cost_weight * experiment.cost
        score = utility
        if horizon > 1 and left > 1:
            rest = tuple(j for j in range(len(model.experiments)) if j not in done and j != i)
            next_cost = None if cost_left is None else cost_left - experiment.cost
            score += sum(p * _value(model, c, rest, left - 1, next_cost, horizon - 1, policy, memo) for p, c in branches)
        rows.append((i, gain, utility, score))
    # Rounding keeps ordering stable across platforms whose libm differs in the last bit.
    rows.sort(key=lambda row: (-round(row[3], 9), model.experiments[row[0]].id))
    return rows


def choose(model, belief, done, policy, left, cost_left=None, rng=None):
    """Index of the next feasible experiment under the policy, or None when none fits."""
    require(policy.mode in MODES, "Unknown planning mode")
    candidates = _feasible(model, done, left, cost_left)
    if not candidates:
        return None
    if policy.mode == "random":
        require(rng is not None, "Random policy requires an explicit RNG")
        return candidates[int(rng.random() * len(candidates))]
    if policy.mode == "fixed":
        ids = [e.id for e in model.experiments]
        order = [ids.index(name) for name in policy.order if name in ids]
        order += [i for i in range(len(ids)) if i not in order]
        return next(i for i in order if i in candidates)
    return rank(model, belief, done, policy, left, cost_left)[0][0]


def top_hypothesis(belief):
    return max(range(len(belief)), key=lambda i: (belief[i], -i))


def decide(model, belief, threshold=DECISION_THRESHOLD):
    top = top_hypothesis(belief)
    return {"hypothesis": model.hypotheses[top], "probability": belief[top], "threshold": threshold,
            "status": "decisive" if belief[top] >= threshold else "inconclusive"}


def _round(value):
    return round(value, 6) + 0.0


def plan_next(request):
    """Validate a planning request and rank the remaining bounded experiments."""
    require(type(request) is dict and set(request) == {"schema_version", "model", "observations", "policy", "budget"}, "Invalid planning request")
    require(request["schema_version"] == REQUEST_VERSION, "Unsupported planning request version")
    model, policy = build_model(request["model"]), build_policy(request["policy"])
    budget = request["budget"]
    require(type(budget) is dict and set(budget) == {"experiments", "cost"}, "Invalid planning budget")
    require(type(budget["experiments"]) is int and 0 <= budget["experiments"] <= MAX_EXPERIMENTS, "Invalid experiment budget")
    total_cost = None if budget["cost"] is None else _number(budget["cost"], "cost budget", 0.0, MAX_TOTAL_COST)
    observations = request["observations"]
    require(type(observations) is list and len(observations) <= budget["experiments"], "Observations exceed the experiment budget")
    index_of = {e.id: i for i, e in enumerate(model.experiments)}
    belief, done, spent, applied = model.prior, set(), 0.0, []
    for entry in observations:
        require(type(entry) is dict and set(entry) == {"experiment_id", "outcome", "trusted"}, "Invalid observation")
        require(type(entry["experiment_id"]) is str and entry["experiment_id"] in index_of, "Unknown experiment in observation")
        i = index_of[entry["experiment_id"]]
        experiment = model.experiments[i]
        require(i not in done, "Each experiment can be observed at most once")
        require(type(entry["outcome"]) is str and entry["outcome"] in experiment.outcomes, "Unknown outcome in observation")
        require(type(entry["trusted"]) is bool, "Observation trust must be a boolean")
        done.add(i)
        spent += experiment.cost
        belief = observe(model, belief, i, experiment.outcomes.index(entry["outcome"]), entry["trusted"], policy.untrusted_reliability)
        applied.append({"experiment_id": experiment.id, "outcome": entry["outcome"], "trusted": entry["trusted"]})
    require(total_cost is None or spent <= total_cost + 1e-9, "Observations exceed the cost budget")
    left = budget["experiments"] - len(observations)
    cost_left = None if total_cost is None else total_cost - spent
    rows = rank(model, belief, done, policy, left, cost_left)
    pick = rows[0] if rows and round(rows[0][3], 9) > 0 else None
    reason = ("recommended: positive expected utility" if pick else
              "no experiment fits the remaining budget" if not rows else "no feasible experiment has positive expected utility")
    decision = decide(model, belief)
    return {"schema_version": RESULT_VERSION, "request": request, "belief_entropy_bits": _round(entropy(belief)),
            "belief": {h: _round(p) for h, p in zip(model.hypotheses, belief)},
            "applied_observations": applied, "decision": decision,
            "ranking": [{"experiment_id": model.experiments[i].id, "cost": model.experiments[i].cost,
                         "expected_gain_bits": _round(g), "utility": _round(u), "score": _round(s)} for i, g, u, s in rows],
            "recommendation": {"experiment_id": None if pick is None else model.experiments[pick[0]].id, "reason": reason},
            "remaining": {"experiments": left, "cost": None if cost_left is None else _round(cost_left)},
            "limitations": list(LIMITATIONS)}
