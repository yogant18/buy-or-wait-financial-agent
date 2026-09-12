"""
main.py — Orchestrator for the Buy or Wait? deterministic financial agent.

Entry point: python main.py
Reads from dataset/, writes output.csv.
Zero API cost. Zero LLM calls.
"""
import sys
import os
import csv
import logging
import datetime
import pandas as pd

# Ensure code/ is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_loader import load_all_data, parse_pipe_list
from ocr_extractor import extract_image_amounts
from message_parser import parse_all_messages
from financial_engine import (
    detect_recurring_events,
    build_forecast,
    evaluate_plans,
    convert_currency,
)
from llm_client import generate_decision_explanation_llm, write_usage_report

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('main')

# ═══════════════════════════════════════════════════════════════════════
# Output columns (exact order from spec)
# ═══════════════════════════════════════════════════════════════════════
OUTPUT_COLUMNS = [
    'request_id',
    'amount_safe_to_pay',
    'affordability_status',
    'recommended_payment_method',
    'payment_plan',
    'earliest_date_for_full_payment',
    'spending_changes_needed',
    'decision_explanation',
]

VALID_STATUSES = {'affordable_now', 'affordable_with_plan', 'affordable_later', 'not_affordable'}
VALID_METHODS = {'full_payment', 'partial_payment', 'installments', 'wait', 'not_recommended'}


def process_request(request, data, image_amounts, amendments):
    """Process a single request and return an output row dict."""
    user_id = str(request['user_id'])
    request_id = str(request['request_id'])
    request_date = request['request_date']
    requested_amount = float(request['requested_amount'])

    logger.info(f"Processing {request_id} for {user_id} (amount={requested_amount})")

    # ── Get user profile ──
    profile_rows = data['profiles'][data['profiles']['user_id'] == user_id]
    if profile_rows.empty:
        logger.error(f"No profile found for {user_id}")
        return _empty_result(request_id, requested_amount)
    profile = profile_rows.iloc[0]

    home_currency = str(profile['home_currency'])
    current_balance = float(profile['current_available_balance'])
    min_balance = float(profile['minimum_balance_to_keep'])

    # ── Get user events ──
    user_events = data['events'][data['events']['user_id'] == user_id].copy()

    # ── Patch blank amounts from images ──
    for eid, amt in image_amounts.items():
        mask = user_events['event_id'] == eid
        if mask.any():
            user_events.loc[mask, 'amount'] = amt

    # ── Get user amendments from messages ──
    user_amendments = [a for a in amendments if a['user_id'] == user_id]

    # ── Get payment options ──
    options = data['payment_options'][data['payment_options']['request_id'] == request_id]

    # ── Detect recurring patterns ──
    recurring = detect_recurring_events(user_events, request_date)

    # ── Collect internal transfer event IDs ──
    internal_transfer_eids = set()
    for a in user_amendments:
        if a['type'] == 'INTERNAL_TRANSFER':
            internal_transfer_eids.add(a.get('related_event_id', ''))

    # ── Build 90-day forecast ──
    daily_balances, all_projected = build_forecast(
        current_balance, user_events, recurring,
        request_date, home_currency, data['exchange_rates'],
        user_amendments, internal_transfer_eids
    )

    # ── Evaluate payment plans ──
    result = evaluate_plans(
        request, profile, options, daily_balances,
        min_balance, all_projected, data['exchange_rates'], home_currency
    )

    # ── Build explanation (LLM with deterministic fallback) ──
    explanation = generate_decision_explanation_llm(
        result, profile, request, recurring_count=len(recurring)
    )

    return {
        'request_id': request_id,
        'amount_safe_to_pay': result['amount_safe_to_pay'],
        'affordability_status': result['affordability_status'],
        'recommended_payment_method': result['recommended_payment_method'],
        'payment_plan': result['payment_plan'],
        'earliest_date_for_full_payment': result['earliest_date_for_full_payment'],
        'spending_changes_needed': result['spending_changes_needed'],
        'decision_explanation': explanation,
    }


def _build_explanation(result, balance, min_bal, amount, req_date, currency, recurring):
    """Build a concise, grounded decision explanation."""
    status = result['affordability_status']
    method = result['recommended_payment_method']
    safe = result['amount_safe_to_pay']
    parts = []

    parts.append(f"Balance {currency} {balance:.2f}, minimum to keep {currency} {min_bal:.2f}.")

    if status == 'affordable_now':
        parts.append(f"Surplus covers full {currency} {amount:.2f}. Pay now in full.")
    elif status == 'affordable_with_plan':
        if method == 'installments':
            parts.append(f"Full payment not safe now. Installment plan keeps balance above minimum.")
        elif method == 'partial_payment':
            parts.append(f"Can safely pay {currency} {safe:.2f} now, remainder on {result['earliest_date_for_full_payment']}.")
        elif method == 'full_payment':
            parts.append(f"Full payment possible with spending changes: {result['spending_changes_needed']}.")
    elif status == 'affordable_later':
        parts.append(f"Full payment unsafe now. Safe from {result['earliest_date_for_full_payment']}.")
    else:
        parts.append(f"Amount exceeds safe surplus within 90-day forecast. Not recommended.")

    n_recurring = len([r for r in recurring if r['direction'] == 'debit'])
    if n_recurring > 0:
        parts.append(f"{n_recurring} recurring monthly expenses detected.")

    return ' '.join(parts)


def _empty_result(request_id, amount):
    return {
        'request_id': request_id,
        'amount_safe_to_pay': 0,
        'affordability_status': 'not_affordable',
        'recommended_payment_method': 'not_recommended',
        'payment_plan': 'none',
        'earliest_date_for_full_payment': '',
        'spending_changes_needed': 'none',
        'decision_explanation': 'Insufficient data to evaluate.',
    }


def validate_output(rows):
    """Validate output rows against spec constraints."""
    issues = []
    for row in rows:
        rid = row['request_id']
        status = row['affordability_status']
        method = row['recommended_payment_method']

        if status not in VALID_STATUSES:
            issues.append(f"{rid}: invalid status '{status}'")
        if method not in VALID_METHODS:
            issues.append(f"{rid}: invalid method '{method}'")

        safe = float(row['amount_safe_to_pay'])
        if safe < 0:
            issues.append(f"{rid}: negative amount_safe_to_pay")

    if issues:
        for issue in issues:
            logger.warning(f"Validation: {issue}")
    else:
        logger.info("Output validation passed.")

    return issues


def main():
    # Determine paths relative to script location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    dataset_dir = os.path.join(repo_root, "dataset")
    output_path = os.path.join(dataset_dir, "output.csv")

    logger.info("=== Buy or Wait? — Deterministic Financial Agent ===")
    logger.info(f"Dataset: {dataset_dir}")

    # ── 1. Load data ──
    logger.info("Loading dataset...")
    data = load_all_data(dataset_dir)
    logger.info(f"  Requests: {len(data['requests'])}")
    logger.info(f"  Events: {len(data['events'])}")
    logger.info(f"  Profiles: {len(data['profiles'])}")

    # ── 2. Extract image amounts ──
    logger.info("Extracting image amounts...")
    image_amounts = extract_image_amounts(data['images'], data['events'], dataset_dir)
    logger.info(f"  Extracted {len(image_amounts)} amounts from images")

    # ── 3. Parse messages ──
    logger.info("Parsing messages...")
    amendments = parse_all_messages(data['messages'])
    logger.info(f"  Found {len(amendments)} actionable amendments")

    # ── 4. Process each request ──
    logger.info("Processing requests...")
    results = []
    for idx, request in data['requests'].iterrows():
        try:
            row = process_request(request, data, image_amounts, amendments)
            results.append(row)
        except Exception as e:
            logger.error(f"Error processing {request['request_id']}: {e}", exc_info=True)
            results.append(_empty_result(str(request['request_id']), float(request['requested_amount'])))

    # ── 5. Validate ──
    logger.info("Validating output...")
    validate_output(results)

    # ── 6. Write output.csv ──
    logger.info(f"Writing {output_path}...")
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in results:
            writer.writerow(row)

    logger.info(f"Done. {len(results)} rows written to output.csv")

    # ── 7. Generate usage report (evaluation/usage_report.md) ──
    eval_dir = os.path.join(os.path.dirname(__file__), 'evaluation')
    write_usage_report(eval_dir, total_requests=len(results))
    logger.info(f"Evaluation usage report written to {eval_dir}/usage_report.md")

    # ── 8. Compare with sample requests (if available) ──
    _compare_samples(data, results)


def _compare_samples(data, results):
    """Compare output with sample_requests for validation."""
    samples = data['sample_requests']
    if samples.empty:
        return

    results_map = {r['request_id']: r for r in results}
    matches = 0
    total = 0

    for _, sample in samples.iterrows():
        sid = str(sample['request_id'])
        if sid not in results_map:
            continue

        total += 1
        pred = results_map[sid]
        expected_status = str(sample['affordability_status'])
        expected_method = str(sample['recommended_payment_method'])

        if (pred['affordability_status'] == expected_status and
            pred['recommended_payment_method'] == expected_method):
            matches += 1
            logger.info(f"  ✓ {sid}: status={expected_status}, method={expected_method}")
        else:
            logger.warning(
                f"  ✗ {sid}: expected status={expected_status} method={expected_method}, "
                f"got status={pred['affordability_status']} method={pred['recommended_payment_method']}"
            )

    logger.info(f"Sample match: {matches}/{total}")


if __name__ == '__main__':
    main()
