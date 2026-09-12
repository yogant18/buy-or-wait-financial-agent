"""
financial_engine.py — Core deterministic financial logic.

Handles: currency conversion, recurrence detection, 90-day balance forecast,
safe-amount calculation, payment plan evaluation, spending changes, and plan ranking.
"""
import datetime
import math
import pandas as pd
import logging
from collections import defaultdict
from data_loader import parse_pipe_list

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Currency conversion
# ═══════════════════════════════════════════════════════════════════════

def convert_currency(amount, from_cur, to_cur, settlement_date, rates_df):
    """Convert amount from one currency to another using the exchange rate table."""
    if from_cur == to_cur or amount == 0:
        return amount

    rate = _find_rate(from_cur, to_cur, settlement_date, rates_df)
    if rate is not None:
        return amount * rate

    # Try inverse
    rate = _find_rate(to_cur, from_cur, settlement_date, rates_df)
    if rate is not None:
        return amount / rate

    # Try chaining through intermediaries
    for mid in ['USD', 'EUR']:
        if mid == from_cur or mid == to_cur:
            continue
        r1 = _get_rate_or_inverse(from_cur, mid, settlement_date, rates_df)
        r2 = _get_rate_or_inverse(mid, to_cur, settlement_date, rates_df)
        if r1 is not None and r2 is not None:
            return amount * r1 * r2

    logger.warning(f"No rate found for {from_cur}->{to_cur} on {settlement_date}")
    return amount  # fallback: no conversion


def _find_rate(from_cur, to_cur, target_date, rates_df):
    """Find the exchange rate for the given pair closest to target_date."""
    mask = (rates_df['from_currency'] == from_cur) & (rates_df['to_currency'] == to_cur)
    matching = rates_df[mask]
    if matching.empty:
        return None
    diffs = matching['rate_date'].apply(lambda d: abs((d - target_date).days))
    idx = diffs.idxmin()
    return float(matching.loc[idx, 'rate'])


def _get_rate_or_inverse(from_cur, to_cur, date, rates_df):
    r = _find_rate(from_cur, to_cur, date, rates_df)
    if r is not None:
        return r
    r = _find_rate(to_cur, from_cur, date, rates_df)
    if r is not None:
        return 1.0 / r
    return None


# ═══════════════════════════════════════════════════════════════════════
# Recurrence detection
# ═══════════════════════════════════════════════════════════════════════

def detect_recurring_events(user_events, request_date):
    """Detect recurring monthly patterns from historical settled events.

    Returns a list of dicts describing each recurring pattern:
    {
        'description', 'category', 'direction', 'amount', 'currency',
        'day_of_month', 'flexibility', 'event_ids', 'minimum_allowed_amount',
        'latest_event_id'
    }
    """
    # Only consider settled events before request_date for pattern detection
    hist = user_events[
        (user_events['status'] == 'settled') &
        (user_events['event_date'] < request_date) &
        (user_events['direction'].isin(['debit', 'credit']))
    ].copy()

    if hist.empty:
        return []

    patterns = []
    # Group by (description, category, direction) for consistent matching
    for (desc, cat, direction), group in hist.groupby(['description', 'category', 'direction']):
        if len(group) < 2:
            continue

        sorted_group = group.sort_values('event_date')
        dates = sorted_group['event_date'].tolist()

        # Compute intervals
        intervals = []
        for i in range(1, len(dates)):
            delta = (dates[i] - dates[i-1]).days
            intervals.append(delta)

        if not intervals:
            continue

        avg_interval = sum(intervals) / len(intervals)

        # Monthly: avg interval 25-35 days, at least 2 occurrences
        if 25 <= avg_interval <= 35 and len(dates) >= 2:
            latest = sorted_group.iloc[-1]
            # Day of month from most recent events
            recent_days = [d.day for d in dates[-3:]]
            dom = max(set(recent_days), key=recent_days.count)

            patterns.append({
                'description': desc,
                'category': cat,
                'direction': direction,
                'amount': float(latest['amount']) if pd.notna(latest['amount']) else 0,
                'currency': str(latest['currency']),
                'day_of_month': dom,
                'flexibility': str(latest['flexibility']),
                'event_ids': sorted_group['event_id'].tolist(),
                'latest_event_id': str(latest['event_id']),
                'minimum_allowed_amount': float(latest['minimum_allowed_amount']) if pd.notna(latest['minimum_allowed_amount']) else 0,
            })

    return patterns


# ═══════════════════════════════════════════════════════════════════════
# Apply message amendments to recurring patterns / future events
# ═══════════════════════════════════════════════════════════════════════

def apply_amendments(patterns, future_events, amendments, request_date, user_events, home_currency, rates_df):
    """Apply message-derived amendments to recurring patterns and future events.

    Modifies patterns in-place and may add/remove future events.
    Returns (amended_patterns, amended_future_events, internal_transfer_event_ids).
    """
    internal_transfer_eids = set()
    salary_overrides = {}      # {None: new_amount} or specific override
    salary_date_override = None
    salary_ended = False
    remaining_salary = None
    rent_increase_pct = None
    invoice_events = []

    for a in amendments:
        atype = a['type']
        details = a.get('details', {})

        if atype == 'INTERNAL_TRANSFER':
            # Mark related events as internal transfers to ignore
            internal_transfer_eids.add(a.get('related_event_id', ''))
            # Also find matching events around the message time
            continue

        elif atype == 'SALARY_INCREASE':
            salary_overrides['amount'] = details.get('amount', 0)
            salary_overrides['currency'] = details.get('currency', home_currency)
            salary_overrides['effective_date'] = details.get('effective_date')

        elif atype in ('SALARY_REDUCTION', 'TEMPORARY_SALARY'):
            salary_overrides['amount'] = details.get('amount', 0)
            salary_overrides['currency'] = details.get('currency', home_currency)
            salary_overrides['effective_date'] = None  # next payroll only

        elif atype == 'SALARY_DATE_CHANGE':
            salary_date_override = details.get('new_date')

        elif atype in ('EMPLOYMENT_ENDED', 'CONTRACT_ENDED'):
            salary_ended = True

        elif atype == 'INCOME_ENDED_REMAINING':
            remaining_salary = {
                'amount': details.get('remaining_amount', 0),
                'currency': details.get('currency', home_currency),
            }

        elif atype == 'SALARY_RESUMES':
            salary_overrides['amount'] = details.get('amount', 0)
            salary_overrides['currency'] = details.get('currency', home_currency)
            salary_overrides['effective_date'] = details.get('effective_date')

        elif atype == 'SALARY_WITH_ARREARS':
            salary_overrides['amount'] = details.get('regular_amount', 0)
            salary_overrides['currency'] = details.get('currency', home_currency)
            salary_overrides['arrears'] = details.get('arrears_amount', 0)

        elif atype == 'FIRST_SALARY':
            salary_overrides['amount'] = details.get('amount', 0)
            salary_overrides['currency'] = details.get('currency', home_currency)
            salary_overrides['effective_date'] = details.get('credit_date')

        elif atype == 'FOREIGN_SALARY':
            salary_overrides['amount'] = details.get('amount', 0)
            salary_overrides['currency'] = details.get('currency', home_currency)
            salary_overrides['effective_date'] = details.get('settlement_date')
            salary_overrides['is_foreign'] = True

        elif atype == 'BASE_SALARY_CONFIRMED':
            salary_overrides['amount'] = details.get('amount', 0)
            salary_overrides['currency'] = details.get('currency', home_currency)

        elif atype == 'RENT_INCREASE':
            rent_increase_pct = details.get('percentage', 12) / 100.0

        elif atype == 'INVOICE_CONFIRMED':
            amt = details.get('amount', 0)
            cur = details.get('currency', home_currency)
            sdate = details.get('settlement_date')
            if sdate and amt > 0:
                converted = convert_currency(amt, cur, home_currency, sdate, rates_df)
                invoice_events.append({
                    'date': sdate,
                    'amount': converted,
                    'direction': 'credit',
                    'description': 'Confirmed invoice payment',
                    'category': 'salary',
                    'is_recurring': False,
                    'flexibility': 'fixed',
                })

    # ── Apply salary amendments to patterns ──
    amended_patterns = []
    for p in patterns:
        if p['category'] == 'salary' and p['direction'] == 'credit':
            if salary_ended:
                # Remove all salary projections
                continue
            if remaining_salary:
                p = dict(p)
                amt = remaining_salary['amount']
                cur = remaining_salary['currency']
                if cur != home_currency:
                    # Will convert per occurrence
                    p['amount'] = amt
                    p['currency'] = cur
                else:
                    p['amount'] = amt
            elif salary_overrides:
                p = dict(p)
                amt = salary_overrides.get('amount', p['amount'])
                cur = salary_overrides.get('currency', p['currency'])
                p['amount'] = amt
                p['currency'] = cur
                if salary_date_override:
                    p['day_of_month'] = salary_date_override.day
        elif p['category'] == 'rent' and p['direction'] == 'debit' and rent_increase_pct:
            p = dict(p)
            p['amount'] = p['amount'] * (1 + rent_increase_pct)

        amended_patterns.append(p)

    # ── Handle first salary / salary date override for future events ──
    amended_future = list(future_events)

    if salary_overrides and not salary_ended:
        eff = salary_overrides.get('effective_date')
        # Override amount in future salary events
        for fe in amended_future:
            if fe.get('category') == 'salary' and fe.get('direction') == 'credit':
                if eff and fe['date'] >= eff:
                    cur = salary_overrides.get('currency', home_currency)
                    fe['amount'] = convert_currency(
                        salary_overrides['amount'], cur, home_currency,
                        fe['date'], rates_df
                    )
                    if salary_overrides.get('arrears', 0) > 0 and fe['date'] == eff:
                        fe['amount'] += convert_currency(
                            salary_overrides['arrears'], cur, home_currency,
                            fe['date'], rates_df
                        )
                elif not eff:
                    # Apply to next salary event
                    cur = salary_overrides.get('currency', home_currency)
                    fe['amount'] = convert_currency(
                        salary_overrides['amount'], cur, home_currency,
                        fe['date'], rates_df
                    )

        if salary_date_override:
            for fe in amended_future:
                if fe.get('category') == 'salary' and fe.get('direction') == 'credit':
                    fe['date'] = salary_date_override

    if salary_ended:
        amended_future = [fe for fe in amended_future
                          if not (fe.get('category') == 'salary' and fe.get('direction') == 'credit')]

    # Add invoice events
    for ie in invoice_events:
        amended_future.append(ie)

    return amended_patterns, amended_future, internal_transfer_eids


# ═══════════════════════════════════════════════════════════════════════
# 90-day balance forecast
# ═══════════════════════════════════════════════════════════════════════

def build_forecast(current_balance, user_events, recurring_patterns,
                   request_date, home_currency, rates_df,
                   amendments, internal_transfer_eids):
    """Build a day-by-day 90-day balance forecast.

    Returns:
        daily_balances: dict[date, float] - balance at end of each day
        all_projected: list of dicts - all projected events in the window
    """
    end_date = request_date + datetime.timedelta(days=90)

    # ── 1. Collect explicit future events (pending/scheduled) ──
    future_events = []
    for _, evt in user_events.iterrows():
        sd = evt['settlement_date']
        if pd.isna(sd):
            continue
        sd = sd.date() if hasattr(sd, 'date') else sd
        if sd <= request_date or sd > end_date:
            continue
        if evt['status'] in ('cancelled', 'failed'):
            continue
        if evt['direction'] == 'non_cash':
            continue
        if evt['status'] == 'unrealized':
            continue
        # Pending credits → IGNORE (spec rule)
        if evt['status'] == 'pending' and evt['direction'] == 'credit':
            continue
        # Internal transfers → IGNORE
        if str(evt['event_id']) in internal_transfer_eids:
            continue

        amount = float(evt['amount']) if pd.notna(evt['amount']) else 0
        if amount == 0:
            continue

        # Convert to home currency
        ecur = str(evt['currency'])
        if ecur != home_currency:
            amount = convert_currency(amount, ecur, home_currency, sd, rates_df)

        future_events.append({
            'date': sd,
            'amount': amount,
            'direction': str(evt['direction']),
            'description': str(evt['description']),
            'event_id': str(evt['event_id']),
            'category': str(evt['category']),
            'is_recurring': False,
            'flexibility': str(evt['flexibility']),
            'minimum_allowed_amount': float(evt['minimum_allowed_amount']) if pd.notna(evt['minimum_allowed_amount']) else 0,
        })

    # ── 2. Apply amendments ──
    amended_patterns, future_events, _ = apply_amendments(
        recurring_patterns, future_events, amendments, request_date,
        user_events, home_currency, rates_df
    )

    # ── 3. Project recurring events into the 90-day window ──
    # Avoid double-counting with explicit future events
    explicit_dates_by_cat = defaultdict(set)
    for fe in future_events:
        explicit_dates_by_cat[(fe['category'], fe['direction'])].add(fe['date'])

    projected_recurring = []
    for pat in amended_patterns:
        dom = pat['day_of_month']
        # Generate dates from request_date+1 to end_date
        cur_date = request_date + datetime.timedelta(days=1)
        while cur_date <= end_date:
            if cur_date.day == dom:
                # Check no explicit event on this date for same category
                key = (pat['category'], pat['direction'])
                if cur_date not in explicit_dates_by_cat[key]:
                    amt = pat['amount']
                    ecur = pat['currency']
                    if ecur != home_currency:
                        amt = convert_currency(amt, ecur, home_currency, cur_date, rates_df)

                    projected_recurring.append({
                        'date': cur_date,
                        'amount': amt,
                        'direction': pat['direction'],
                        'description': pat['description'],
                        'event_id': pat.get('latest_event_id', ''),
                        'category': pat['category'],
                        'is_recurring': True,
                        'flexibility': pat['flexibility'],
                        'minimum_allowed_amount': pat.get('minimum_allowed_amount', 0),
                    })
            cur_date += datetime.timedelta(days=1)

    # ── 4. Combine and build daily balances ──
    all_events = future_events + projected_recurring
    all_events.sort(key=lambda e: e['date'])

    events_by_date = defaultdict(list)
    for e in all_events:
        events_by_date[e['date']].append(e)

    daily_balances = {}
    balance = current_balance
    for day_offset in range(91):
        day = request_date + datetime.timedelta(days=day_offset)
        for evt in events_by_date.get(day, []):
            if evt['direction'] == 'credit':
                balance += evt['amount']
            elif evt['direction'] == 'debit':
                balance -= evt['amount']
        daily_balances[day] = balance

    return daily_balances, all_events


# ═══════════════════════════════════════════════════════════════════════
# Safe amount and earliest full payment
# ═══════════════════════════════════════════════════════════════════════

def compute_safe_amount(daily_balances, min_balance, requested_amount):
    """Compute the maximum amount safely payable on request_date.

    If we pay X on request_date, all subsequent balances decrease by X.
    We need min(daily_balances) - X >= min_balance.
    """
    if not daily_balances:
        return 0.0
    min_projected = min(daily_balances.values())
    surplus = min_projected - min_balance
    safe = min(requested_amount, max(0, surplus))
    return round(safe, 2)


def compute_earliest_full_payment(daily_balances, min_balance, requested_amount, request_date):
    """Find the earliest date D where paying requested_amount keeps balance safe.

    For date D: min(balance[d] for d >= D) - requested_amount >= min_balance
    """
    sorted_dates = sorted(daily_balances.keys())
    if not sorted_dates:
        return None

    # Compute suffix minimums (min balance from day D onward)
    n = len(sorted_dates)
    suffix_min = [0.0] * n
    suffix_min[n-1] = daily_balances[sorted_dates[n-1]]
    for i in range(n-2, -1, -1):
        suffix_min[i] = min(daily_balances[sorted_dates[i]], suffix_min[i+1])

    for i, day in enumerate(sorted_dates):
        if suffix_min[i] - requested_amount >= min_balance:
            return day

    return None


# ═══════════════════════════════════════════════════════════════════════
# Plan safety check
# ═══════════════════════════════════════════════════════════════════════

def is_plan_safe(payments, daily_balances, min_balance):
    """Check if a payment plan keeps all daily balances above minimum.

    payments: list of (date, amount) tuples
    daily_balances: dict[date, float] - balances WITHOUT this plan's payments
    """
    if not payments:
        return True

    sorted_dates = sorted(daily_balances.keys())
    payment_by_date = defaultdict(float)
    for pdate, pamount in payments:
        payment_by_date[pdate] += pamount

    cumulative = 0.0
    for day in sorted_dates:
        if day in payment_by_date:
            cumulative += payment_by_date[day]
        adjusted = daily_balances[day] - cumulative
        if adjusted < min_balance - 0.005:  # small tolerance for floating point
            return False

    return True


# ═══════════════════════════════════════════════════════════════════════
# Spending changes
# ═══════════════════════════════════════════════════════════════════════

def find_spending_change_candidates(all_projected, profile):
    """Find recurring events that can be stopped or reduced."""
    reducible_cats = parse_pipe_list(profile.get('expense_categories_user_is_willing_to_reduce', ''))
    stoppable_cats = parse_pipe_list(profile.get('expense_categories_user_is_willing_to_stop', ''))
    protected_cats = parse_pipe_list(profile.get('expense_categories_to_protect', ''))

    candidates = []  # list of dicts with 'event_id', 'action', 'savings_per_month', etc.
    seen_event_ids = set()

    for evt in all_projected:
        if not evt.get('is_recurring') or evt['direction'] != 'debit':
            continue
        eid = evt.get('event_id', '')
        cat = evt.get('category', '')
        flex = evt.get('flexibility', 'fixed')

        if cat in protected_cats:
            continue
        if eid in seen_event_ids:
            continue

        can_stop = (flex in ('stoppable', 'reducible_or_stoppable')) and (cat in stoppable_cats)
        can_reduce = (flex in ('reducible', 'reducible_or_stoppable')) and (cat in reducible_cats)

        if can_stop:
            candidates.append({
                'event_id': eid,
                'action': 'stop',
                'category': cat,
                'amount': evt['amount'],
                'savings': evt['amount'],
                'new_amount': 0,
            })
            seen_event_ids.add(eid)

        if can_reduce:
            min_amt = evt.get('minimum_allowed_amount', 0)
            savings = evt['amount'] - min_amt
            if savings > 0:
                candidates.append({
                    'event_id': eid,
                    'action': 'reduce',
                    'category': cat,
                    'amount': evt['amount'],
                    'savings': savings,
                    'new_amount': min_amt,
                })
                if eid not in seen_event_ids:
                    seen_event_ids.add(eid)

    # Sort by savings descending
    candidates.sort(key=lambda c: c['savings'], reverse=True)
    return candidates


def apply_spending_changes_to_balances(daily_balances, all_projected, changes, request_date):
    """Recompute daily balances after applying spending changes.

    changes: list of {'event_id': str, 'action': 'stop'|'reduce', 'new_amount': float}
    """
    adjusted = dict(daily_balances)
    end_date = request_date + datetime.timedelta(days=90)

    change_map = {c['event_id']: c for c in changes}

    for evt in all_projected:
        if not evt.get('is_recurring') or evt['direction'] != 'debit':
            continue
        eid = evt.get('event_id', '')
        if eid not in change_map:
            continue

        ch = change_map[eid]
        evt_date = evt['date']
        if evt_date <= request_date or evt_date > end_date:
            continue

        if ch['action'] == 'stop':
            savings = evt['amount']
        else:  # reduce
            savings = evt['amount'] - ch['new_amount']

        # Add savings back to all days on and after evt_date
        for day in sorted(adjusted.keys()):
            if day >= evt_date:
                adjusted[day] += savings

    return adjusted


def try_spending_changes(payments, daily_balances, min_balance, all_projected, profile, request_date):
    """Try combinations of spending changes (up to 3) to make a plan safe.

    Returns (is_safe, changes_list) where changes_list is a list of change dicts,
    or (False, []) if no combination works.
    """
    candidates = find_spending_change_candidates(all_projected, profile)

    if not candidates:
        return False, []

    # Try single changes first, then pairs, then triples
    from itertools import combinations

    for num_changes in range(1, min(4, len(candidates) + 1)):
        for combo in combinations(candidates, num_changes):
            # Check mutual exclusivity: no stop+reduce on same event_id
            event_ids = [c['event_id'] for c in combo]
            if len(set(event_ids)) != len(event_ids):
                continue

            changes = list(combo)
            adj_balances = apply_spending_changes_to_balances(
                daily_balances, all_projected, changes, request_date
            )
            if is_plan_safe(payments, adj_balances, min_balance):
                return True, changes

    return False, []


# ═══════════════════════════════════════════════════════════════════════
# Plan evaluation and ranking
# ═══════════════════════════════════════════════════════════════════════

def build_installment_schedule(option):
    """Build the payment schedule from a payment option row."""
    first_date = option['first_payment_date']
    freq = int(option['payment_frequency_days']) if pd.notna(option['payment_frequency_days']) else 0
    n_payments = int(option['number_of_payments'])
    amount = float(option['payment_amount'])

    payments = []
    for i in range(n_payments):
        pdate = first_date + datetime.timedelta(days=i * freq) if freq > 0 else first_date
        payments.append((pdate, amount))

    return payments


def evaluate_plans(request, profile, payment_options, daily_balances,
                   min_balance, all_projected, rates_df, home_currency):
    """Evaluate all eligible payment plans and return the best one.

    Returns a dict with all output fields.
    """
    requested_amount = float(request['requested_amount'])
    request_date = request['request_date']
    desired_completion = request['desired_completion_date']
    allows_partial = request['allows_partial_payment']

    payment_methods = parse_pipe_list(profile['payment_methods_user_will_consider'])
    max_inst_months = profile['max_installment_months'] if pd.notna(profile['max_installment_months']) else None

    amount_safe = compute_safe_amount(daily_balances, min_balance, requested_amount)
    earliest_full = compute_earliest_full_payment(daily_balances, min_balance, requested_amount, request_date)

    candidates = []

    # ── 1. Full payment options ──
    if 'full_payment' in payment_methods:
        # Find full_payment option from payment_options
        fp_opts = payment_options[payment_options['payment_method'] == 'full_payment']
        for _, opt in fp_opts.iterrows():
            payments = [(opt['first_payment_date'], float(opt['payment_amount']))]
            total = float(opt['total_payable_amount'])

            if is_plan_safe(payments, daily_balances, min_balance):
                candidates.append(_make_candidate(
                    opt, payments, total, desired_completion,
                    needs_changes=False, changes=[]
                ))
            else:
                # Try with spending changes
                safe, changes = try_spending_changes(
                    payments, daily_balances, min_balance,
                    all_projected, profile, request_date
                )
                if safe:
                    candidates.append(_make_candidate(
                        opt, payments, total, desired_completion,
                        needs_changes=True, changes=changes
                    ))

    # ── 2. Installment options ──
    if 'installments' in payment_methods and max_inst_months is not None:
        inst_opts = payment_options[payment_options['payment_method'] == 'installments']
        for _, opt in inst_opts.iterrows():
            n_payments = int(opt['number_of_payments'])
            freq = int(opt['payment_frequency_days']) if pd.notna(opt['payment_frequency_days']) else 30

            # Check max_installment_months
            total_days = (n_payments - 1) * freq
            total_months = total_days / 30.0
            if total_months > max_inst_months:
                continue

            payments = build_installment_schedule(opt)
            total = float(opt['total_payable_amount'])

            if is_plan_safe(payments, daily_balances, min_balance):
                candidates.append(_make_candidate(
                    opt, payments, total, desired_completion,
                    needs_changes=False, changes=[]
                ))
            else:
                safe, changes = try_spending_changes(
                    payments, daily_balances, min_balance,
                    all_projected, profile, request_date
                )
                if safe:
                    candidates.append(_make_candidate(
                        opt, payments, total, desired_completion,
                        needs_changes=True, changes=changes
                    ))

    # ── 3. Partial payment ──
    if 'partial_payment' in payment_methods and allows_partial:
        if 0 < amount_safe < requested_amount and earliest_full is not None:
            if earliest_full <= desired_completion:
                remainder = round(requested_amount - amount_safe, 2)
                payments = [(request_date, amount_safe), (earliest_full, remainder)]
                total = requested_amount

                if is_plan_safe(payments, daily_balances, min_balance):
                    candidates.append({
                        'payment_option_id': '',
                        'payment_method': 'partial_payment',
                        'payments': payments,
                        'total_payable': total,
                        'financing_fee': 0,
                        'completes_by_deadline': True,
                        'needs_changes': False,
                        'changes': [],
                        'num_payments': 2,
                        'first_payment_date': request_date,
                    })

    # ── 4. Wait ──
    if 'full_payment' in payment_methods and earliest_full is not None and earliest_full > request_date:
        payments = [(earliest_full, requested_amount)]
        if is_plan_safe(payments, daily_balances, min_balance):
            completes = earliest_full <= desired_completion
            candidates.append({
                'payment_option_id': '',
                'payment_method': 'wait',
                'payments': payments,
                'total_payable': requested_amount,
                'financing_fee': 0,
                'completes_by_deadline': completes,
                'needs_changes': False,
                'changes': [],
                'num_payments': 1,
                'first_payment_date': earliest_full,
            })

    # ── 5. Rank and select best ──
    if candidates:
        best = _rank_candidates(candidates)
        return _build_result(best, amount_safe, earliest_full, request_date, requested_amount)
    else:
        # Not recommended
        return _build_not_recommended(amount_safe, earliest_full, requested_amount)


def _make_candidate(opt, payments, total, deadline, needs_changes, changes):
    last_date = max(d for d, _ in payments)
    return {
        'payment_option_id': str(opt['payment_option_id']),
        'payment_method': str(opt['payment_method']),
        'payments': payments,
        'total_payable': total,
        'financing_fee': float(opt['financing_fee']),
        'completes_by_deadline': last_date <= deadline,
        'needs_changes': needs_changes,
        'changes': changes,
        'num_payments': len(payments),
        'first_payment_date': payments[0][0],
    }


def _rank_candidates(candidates):
    """Rank using the exact tie-break order from the spec."""
    def sort_key(c):
        # Extract numeric part of payment_option_id for tie-breaking
        pid = c.get('payment_option_id', '')
        pid_num = 0
        if pid:
            import re
            m = re.search(r'(\d+)', pid)
            if m:
                pid_num = int(m.group(1))

        return (
            not c['completes_by_deadline'],     # 1. Completes by deadline (True first)
            c['needs_changes'],                  # 2. No spending changes (False first)
            c['total_payable'],                  # 3. Minimize total paid
            c['first_payment_date'],             # 4. Earlier start
            c['num_payments'],                   # 5. Fewer payments
            pid_num,                             # 6. Lowest payment_option_id
        )

    candidates.sort(key=sort_key)
    return candidates[0]


def _build_result(best, amount_safe, earliest_full, request_date, requested_amount):
    """Build the output row dict from the best candidate."""
    method = best['payment_method']

    # Determine affordability_status
    if method == 'full_payment' and not best['needs_changes']:
        if best['first_payment_date'] == request_date:
            status = 'affordable_now'
        else:
            status = 'affordable_later'
    elif method == 'wait':
        status = 'affordable_later'
    elif method in ('installments', 'partial_payment') or best['needs_changes']:
        status = 'affordable_with_plan'
    else:
        status = 'affordable_with_plan'

    # For affordable_now + full_payment without changes: amount_safe should == requested
    if status == 'affordable_now':
        amount_safe = requested_amount

    # Payment plan string
    if best['payments']:
        plan_parts = [f"{d.isoformat()}:{amt}" for d, amt in best['payments']]
        plan_str = '|'.join(plan_parts)
    else:
        plan_str = 'none'

    # Earliest date
    if status == 'affordable_now':
        earliest_str = request_date.isoformat()
    elif earliest_full:
        earliest_str = earliest_full.isoformat()
    else:
        earliest_str = ''

    # Spending changes
    if best['needs_changes'] and best['changes']:
        change_parts = []
        for ch in best['changes']:
            if ch['action'] == 'stop':
                change_parts.append(f"stop:{ch['event_id']}")
            else:
                change_parts.append(f"reduce_to:{ch['event_id']}:{ch['new_amount']}")
        changes_str = '|'.join(change_parts)
    else:
        changes_str = 'none'

    return {
        'amount_safe_to_pay': amount_safe,
        'affordability_status': status,
        'recommended_payment_method': method,
        'payment_plan': plan_str,
        'earliest_date_for_full_payment': earliest_str,
        'spending_changes_needed': changes_str,
    }


def _build_not_recommended(amount_safe, earliest_full, requested_amount):
    """Build output for not_recommended case."""
    return {
        'amount_safe_to_pay': amount_safe,
        'affordability_status': 'not_affordable',
        'recommended_payment_method': 'not_recommended',
        'payment_plan': 'none',
        'earliest_date_for_full_payment': earliest_full.isoformat() if earliest_full else '',
        'spending_changes_needed': 'none',
    }
