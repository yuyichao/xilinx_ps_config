#!/usr/bin/julia

def find_divisors(base, target, rng1, rng2):
    lb1, ub1 = rng1
    lb2, ub2 = rng2

    ratio = base / target

    best_div1 = ub1
    best_div2 = ub2
    best_diff = abs(target - base / ub1 / ub2)

    def try_divs(div1, div2):
        nonlocal best_div1
        nonlocal best_div2
        nonlocal best_diff
        diff = abs(target - base / div1 / div2)
        if diff < best_diff:
            best_div1 = div1
            best_div2 = div2
            best_diff = diff

    for div1 in range(lb1, ub1 + 1):
        div2 = int(ratio / div1)
        if div2 < lb2:
            div2 = lb2
        if div2 <= ub2:
            try_divs(div1, div2)
        if div2 + 1 <= ub2:
            try_divs(div1, div2 + 1)

    return best_div1, best_div2, best_diff / target
