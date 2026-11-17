"""Direct lay search without a demand-GCD restriction."""
from time import monotonic
from functools import reduce
from math import gcd, isqrt
from ortools.sat.python import cp_model


def flexible_plan(inputs, quantities, capacity, expand, deadline):
    from .planner import Lay, validate_plan
    # Every non-final lay consumes at least min_plies garments.
    slots = (sum(quantities)-1)//inputs.min_plies+1
    slot_limit = min(80, isqrt(60000 // len(quantities)))
    # A conservative starting plan: balance normal per-size lays, then
    # combine small sizes in the single permitted final remainder lay.
    seed=[]
    small=[q for q in quantities if q<inputs.min_plies]
    remainder_unit=reduce(gcd,small) if small else 0
    tail=tuple(q//remainder_unit if q<inputs.min_plies else 0 for q in quantities) if small else None
    for i,q in enumerate(quantities):
        if q<inputs.min_plies:
            continue
        n=(q+inputs.max_plies-1)//inputs.max_plies
        if len(seed)+n > 10000:
            return None, 'MODEL_TOO_LARGE', False
        base,extra=divmod(q,n)
        if base<inputs.min_plies:
            seed=[]
            break
        marker=expand(tuple(int(j==i) for j in range(len(quantities))))
        seed.extend(Lay(marker,base+(t<extra)) for t in range(n))
    seed.sort(key=lambda lay:-lay.plies)
    if small and sum(tail)<=capacity:
        seed.append(Lay(expand(tail),remainder_unit))
    try:
        validate_plan(inputs,seed)
    except ValueError:
        seed=None
    # Build a useful incumbent before spending the budget on the large model.
    # In particular, a GCD below min_plies must not force one marker per size.
    from .shared_seed import shared_seed
    now = monotonic()
    shared = shared_seed(inputs, quantities, capacity, expand,
                         min(deadline, now + min(1.0, max(0.0, deadline-now) / 2)))
    def score(lays):
        return len({lay.marker for lay in lays}), len(lays)
    if shared is not None and (seed is None or score(shared) < score(seed)):
        seed = shared
    # The theoretical lay bound can be much larger than a real valid plan.
    # Preserve a validated incumbent instead of rejecting it at the model guard.
    restricted = slots > slot_limit
    if restricted:
        if seed is None:
            return None, 'MODEL_TOO_LARGE', False
        if len(seed) > slot_limit:
            return seed, 'FEASIBLE', False
        slots = slot_limit
    if seed is not None and monotonic() >= deadline:
        return seed, 'FEASIBLE', False
    model=cp_model.CpModel()
    active=[model.new_bool_var(f'a{t}') for t in range(slots)]
    plies=[model.new_int_var(0,inputs.max_plies,f'p{t}') for t in range(slots)]
    counts=[[model.new_int_var(0,min(capacity,q),f'c{t}_{i}') for i,q in enumerate(quantities)] for t in range(slots)]
    for t in range(slots):
        model.add(plies[t]>=active[t])
        model.add(plies[t]<=inputs.max_plies*active[t])
        model.add(sum(counts[t])>=active[t])
        model.add(sum(counts[t])<=capacity*active[t])
        if t+1<slots:
            model.add(active[t]>=active[t+1])
            model.add(plies[t]>=plies[t+1])
            model.add(plies[t]>=inputs.min_plies).only_enforce_if(active[t+1])
    for i,q in enumerate(quantities):
        cut=[]
        for t in range(slots):
            v=model.new_int_var(0,q,f'cut{t}_{i}')
            model.add_multiplication_equality(v,[counts[t][i],plies[t]])
            cut.append(v)
        model.add(sum(cut)==q)
    first=[]
    for t in range(slots):
        previous=[]
        for u in range(t):
            same_columns=[]
            for i in range(len(quantities)):
                equal=model.new_bool_var(f'e{t}_{u}_{i}')
                model.add(counts[t][i]==counts[u][i]).only_enforce_if(equal)
                model.add(counts[t][i]!=counts[u][i]).only_enforce_if(equal.Not())
                same_columns.append(equal)
            same=model.new_bool_var(f'same{t}_{u}')
            model.add_bool_and(same_columns).only_enforce_if(same)
            model.add_bool_or([v.Not() for v in same_columns]).only_enforce_if(same.Not())
            previous.append(same)
        new=model.new_bool_var(f'new{t}')
        model.add(new<=active[t])
        for same in previous:
            model.add(new+same<=1)
        model.add(new>=active[t]-sum(previous))
        first.append(new)
    model.minimize(sum(first)*(slots+1)+sum(active))
    if seed is not None:
        incumbent=len({lay.marker for lay in seed})
        model.add(sum(first)*(slots+1)+sum(active)<=incumbent*(slots+1)+len(seed))
        # Counts in this model only cover positive-demand size columns.
        columns=[i for i,q in enumerate(inputs.quantities) if q>0]
        for t in range(slots):
            lay=seed[t] if t<len(seed) else None
            model.add_hint(active[t],int(lay is not None))
            model.add_hint(plies[t],lay.plies if lay else 0)
            for i,column in enumerate(columns):
                model.add_hint(counts[t][i],lay.marker[column] if lay else 0)
    solver=cp_model.CpSolver()
    solver.parameters.max_time_in_seconds=max(.001,deadline-monotonic())
    solver.parameters.num_search_workers=8
    status=solver.solve(model)
    if status not in (cp_model.OPTIMAL,cp_model.FEASIBLE):
        if seed is not None:
            return seed, 'FEASIBLE', False
        return None, 'INFEASIBLE' if status==cp_model.INFEASIBLE and not restricted else 'UNKNOWN', False
    lays=[Lay(expand(tuple(solver.value(c) for c in counts[t])),solver.value(plies[t])) for t in range(slots) if solver.value(active[t])]
    validate_plan(inputs,lays)
    proven = status==cp_model.OPTIMAL and not restricted
    return lays, 'OPTIMAL' if proven else 'FEASIBLE', proven
