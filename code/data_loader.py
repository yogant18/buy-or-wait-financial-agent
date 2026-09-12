"""
data_loader.py — Load all dataset CSVs with proper type parsing.
"""
import pandas as pd
from pathlib import Path


def load_all_data(dataset_dir="dataset"):
    """Load all dataset CSV files and return as a dictionary of DataFrames."""
    base = Path(dataset_dir)
    data = {}

    # ── Requests ──
    data['requests'] = pd.read_csv(base / "requests.csv")
    data['requests']['request_date'] = pd.to_datetime(
        data['requests']['request_date']).dt.date
    data['requests']['desired_completion_date'] = pd.to_datetime(
        data['requests']['desired_completion_date']).dt.date
    data['requests']['allows_partial_payment'] = data['requests'][
        'allows_partial_payment'].map({'true': True, 'false': False})
    data['requests']['requested_amount'] = pd.to_numeric(
        data['requests']['requested_amount'])

    # ── Financial Profiles ──
    data['profiles'] = pd.read_csv(base / "financial_profiles.csv")
    data['profiles']['current_available_balance'] = pd.to_numeric(
        data['profiles']['current_available_balance'])
    data['profiles']['minimum_balance_to_keep'] = pd.to_numeric(
        data['profiles']['minimum_balance_to_keep'])
    data['profiles']['max_installment_months'] = pd.to_numeric(
        data['profiles']['max_installment_months'], errors='coerce')

    # ── Financial Events ──
    data['events'] = pd.read_csv(base / "financial_events.csv")
    data['events']['event_date'] = pd.to_datetime(
        data['events']['event_date']).dt.date
    data['events']['settlement_date'] = pd.to_datetime(
        data['events']['settlement_date'], errors='coerce')
    # Keep settlement_date as Timestamp for NaT handling, convert to date only where valid
    data['events']['amount'] = pd.to_numeric(
        data['events']['amount'], errors='coerce')
    data['events']['minimum_allowed_amount'] = pd.to_numeric(
        data['events']['minimum_allowed_amount'], errors='coerce')

    # ── Exchange Rates ──
    data['exchange_rates'] = pd.read_csv(base / "exchange_rates.csv")
    data['exchange_rates']['rate_date'] = pd.to_datetime(
        data['exchange_rates']['rate_date']).dt.date
    data['exchange_rates']['rate'] = pd.to_numeric(
        data['exchange_rates']['rate'])

    # ── Payment Options ──
    data['payment_options'] = pd.read_csv(base / "request_payment_options.csv")
    data['payment_options']['first_payment_date'] = pd.to_datetime(
        data['payment_options']['first_payment_date']).dt.date
    data['payment_options']['payment_amount'] = pd.to_numeric(
        data['payment_options']['payment_amount'])
    data['payment_options']['number_of_payments'] = pd.to_numeric(
        data['payment_options']['number_of_payments'], errors='coerce').astype('Int64')
    data['payment_options']['payment_frequency_days'] = pd.to_numeric(
        data['payment_options']['payment_frequency_days'], errors='coerce').astype('Int64')
    data['payment_options']['financing_fee'] = pd.to_numeric(
        data['payment_options']['financing_fee'], errors='coerce').fillna(0)
    data['payment_options']['total_payable_amount'] = pd.to_numeric(
        data['payment_options']['total_payable_amount'])

    # ── Messages ──
    data['messages'] = pd.read_csv(base / "messages.csv")
    data['messages']['sent_at'] = pd.to_datetime(data['messages']['sent_at'])

    # ── Images ──
    data['images'] = pd.read_csv(base / "images.csv")

    # ── Sample Requests (for validation only) ──
    data['sample_requests'] = pd.read_csv(base / "sample_requests.csv")

    return data


def parse_pipe_list(value):
    """Parse a pipe-separated string into a list. Returns empty list for NaN/blank."""
    if pd.isna(value) or str(value).strip() == '':
        return []
    return [v.strip() for v in str(value).split('|')]
