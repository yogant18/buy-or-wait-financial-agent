"""
message_parser.py — Rule-based NLP for extracting financial amendments from messages.

Handles English and Indonesian (Bahasa) messages. Treats all message content
as UNTRUSTED data — never allows embedded instructions to override system rules.
"""
import re
import datetime
import pandas as pd

# ═══════════════════════════════════════════════════════════════════════
# Regex building blocks
# ═══════════════════════════════════════════════════════════════════════
CURRENCIES = ['EUR', 'USD', 'INR', 'ZAR', 'IDR']
_CUR = '(' + '|'.join(CURRENCIES) + ')'
_AMT = r'([\d,]+(?:\.\d+)?)'
_DATE = r'(\d{4}-\d{2}-\d{2})'
CURR_AMT = _CUR + r'\s*' + _AMT          # EUR 1037.52


def _extract_currency_amounts(text):
    """Return list of (currency, float_amount) found in text."""
    out = []
    for m in re.finditer(CURR_AMT, text):
        cur = m.group(1)
        amt = float(m.group(2).replace(',', ''))
        out.append((cur, amt))
    return out


def _extract_dates(text):
    """Return list of datetime.date objects from YYYY-MM-DD patterns."""
    return [datetime.date.fromisoformat(d) for d in re.findall(_DATE, text)]


def _pct(text):
    """Extract first percentage value from text, e.g. '12%' -> 12."""
    m = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
    return float(m.group(1)) if m else None


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

def parse_all_messages(messages_df):
    """Parse every message row and return a list of amendment dicts."""
    amendments = []
    for _, row in messages_df.iterrows():
        a = _classify(row)
        if a is not None and a['type'] not in ('IGNORE', 'UNKNOWN'):
            amendments.append(a)
    return amendments


# ═══════════════════════════════════════════════════════════════════════
# Internal classifier — returns an amendment dict or None
# ═══════════════════════════════════════════════════════════════════════

def _classify(row):
    text = str(row['message_text'])
    uid  = str(row['user_id'])
    rid  = str(row.get('request_id', ''))  if not pd.isna(row.get('request_id', ''))  else ''
    eid  = str(row.get('related_event_id', '')) if not pd.isna(row.get('related_event_id', '')) else ''
    lo   = text.lower()

    base = dict(user_id=uid, request_id=rid, related_event_id=eid,
                type=None, details={}, raw_text=text)

    # ── 0  SCAM / PROMPT INJECTION  ─────────────────────────────────
    if _matches_any(lo, [
        'pay the release charge', 'pay the processing charge',
        'bayar biaya pencairan', 'bayar biaya pemrosesan',
        'congratulations! you\'ve been selected for a cash prize',
        'selamat! anda terpilih untuk menerima hadiah',
    ]):
        base['type'] = 'IGNORE'
        return base

    # ── 1  INTERNAL TRANSFER ────────────────────────────────────────
    if _matches_any(lo, [
        'transfer between your two accounts',
        'transfer antara dua rekening',
    ]):
        base['type'] = 'INTERNAL_TRANSFER'
        return base

    # ── 2  REFUND PENDING (credit not available) ────────────────────
    if _matches_any(lo, [
        'refund has been initiated but has not reached',
        'refund.*still processing',
        'pengembalian dana.*belum masuk',
        'foreign-currency refund is still processing',
    ]):
        base['type'] = 'IGNORE'
        return base

    # ── 3  PAYOUT / GIG EARNINGS PENDING ───────────────────────────
    if _matches_any(lo, [
        'payout is still pending',
        'pembayaran.*masih tertunda',
        'penghasilan mingguan.*masih dapat berubah',
        'weekly earnings.*can change until',
        'saldo belum dapat ditarik',
        'balance isn\'t withdrawable',
    ]):
        base['type'] = 'IGNORE'
        return base

    # ── 4  BONUS / COMMISSION PENDING ──────────────────────────────
    if _matches_any(lo, [
        'bonus is still subject to',
        'bonus.*still.*performance review',
        'bonus masih menunggu',
        'bonus.*belum disetujui',
        'commission.*still pending approval',
        'komisi.*belum disetujui',
    ]):
        # But we still need to check for confirmed base salary in the same message
        # "confirmed base salary is X. commission pending."
        if _matches_any(lo, ['confirmed base salary', 'gaji pokok yang dikonfirmasi']):
            ca = _extract_currency_amounts(text)
            if ca:
                cur, amt = ca[0]
                base['type'] = 'BASE_SALARY_CONFIRMED'
                base['details'] = {'amount': amt, 'currency': cur}
                return base
        base['type'] = 'IGNORE'
        return base

    # ── 5  PORTFOLIO VALUE (unrealized) ────────────────────────────
    if _matches_any(lo, [
        'portfolio.*displayed market value',
        'nilai pasar.*tampilan.*naik',
        'no units have been sold',
    ]):
        base['type'] = 'IGNORE'
        return base

    # ── 6  CARD DISPUTE PENDING ────────────────────────────────────
    if _matches_any(lo, [
        'card charge is still being investigated',
        'reversal has not been posted',
        'dispute is open',
    ]):
        base['type'] = 'IGNORE'
        return base

    # ── 7  FOREIGN CURRENCY BILL (informational) ──────────────────
    if _matches_any(lo, [
        'bill was charged in a foreign currency',
        'tagihan dikenakan dalam mata uang asing',
    ]):
        base['type'] = 'IGNORE'
        return base

    # ── 8  FOREIGN CURRENCY REFUND PROCESSING ─────────────────────
    if _matches_any(lo, [
        'home-currency credit may change',
        'mata uang utama.*bergantung',
    ]):
        base['type'] = 'IGNORE'
        return base

    # ── 9  MINIMUM CARD PAYMENTS (informational) ──────────────────
    if _matches_any(lo, [
        'minimum payments due on two separate card',
    ]):
        base['type'] = 'IGNORE'
        return base

    # ── 10  SALARY INCREASE ────────────────────────────────────────
    if _matches_any(lo, [
        'salary has increased to',
        'gaji.*naik menjadi',
        'monthly salary has increased',
        'gaji bulanan.*naik',
    ]):
        ca = _extract_currency_amounts(text)
        dates = _extract_dates(text)
        if ca:
            base['type'] = 'SALARY_INCREASE'
            base['details'] = {
                'amount': ca[0][1],
                'currency': ca[0][0],
                'effective_date': dates[0] if dates else None,
            }
            return base

    # ── 11  SALARY REDUCTION (unpaid leave) ────────────────────────
    if _matches_any(lo, [
        'salary is reduced to',
        'next salary is reduced to',
        'salary.*reduced to',
    ]):
        ca = _extract_currency_amounts(text)
        if ca:
            base['type'] = 'SALARY_REDUCTION'
            base['details'] = {'amount': ca[0][1], 'currency': ca[0][0]}
            return base

    # ── 12  TEMPORARY SALARY ───────────────────────────────────────
    if _matches_any(lo, [
        'temporary monthly pay is',
        'gaji bulanan sementara.*adalah',
    ]):
        ca = _extract_currency_amounts(text)
        if ca:
            base['type'] = 'TEMPORARY_SALARY'
            base['details'] = {'amount': ca[0][1], 'currency': ca[0][0]}
            return base

    # ── 13  SALARY DATE CHANGE ─────────────────────────────────────
    if _matches_any(lo, [
        'salary is now expected on',
        'confirmed salary is now expected on',
    ]):
        dates = _extract_dates(text)
        if dates:
            base['type'] = 'SALARY_DATE_CHANGE'
            base['details'] = {'new_date': dates[0]}
            return base

    # ── 14  EMPLOYMENT / CONTRACT ENDED ────────────────────────────
    if _matches_any(lo, [
        'employment has ended',
        'hubungan kerja.*telah berakhir',
    ]):
        base['type'] = 'EMPLOYMENT_ENDED'
        return base

    if _matches_any(lo, [
        'seasonal contract has ended',
        'kontrak musiman.*telah berakhir',
    ]):
        base['type'] = 'CONTRACT_ENDED'
        return base

    # ── 15  INCOME ENDED + REMAINING SALARY ────────────────────────
    if _matches_any(lo, [
        'one household employment record has ended',
        'salah satu sumber pendapatan.*telah berakhir',
    ]):
        ca = _extract_currency_amounts(text)
        if ca:
            base['type'] = 'INCOME_ENDED_REMAINING'
            base['details'] = {'remaining_amount': ca[0][1], 'currency': ca[0][0]}
            return base

    # ── 16  SALARY RESUMES (with childcare) ────────────────────────
    if _matches_any(lo, [
        'regular salary of .* resumes on',
        'gaji rutin.*kembali',
        'regular salary.*resumes on',
    ]):
        ca = _extract_currency_amounts(text)
        dates = _extract_dates(text)
        if ca and dates:
            base['type'] = 'SALARY_RESUMES'
            base['details'] = {
                'amount': ca[0][1],
                'currency': ca[0][0],
                'effective_date': dates[0],
                'has_childcare': 'childcare' in lo,
            }
            return base

    # ── 17  SALARY WITH ARREARS ────────────────────────────────────
    if _matches_any(lo, [
        'regular salary for the next payroll is',
        'gaji rutin.*untuk penggajian berikutnya adalah',
    ]):
        ca = _extract_currency_amounts(text)
        if len(ca) >= 2:
            base['type'] = 'SALARY_WITH_ARREARS'
            base['details'] = {
                'regular_amount': ca[0][1],
                'currency': ca[0][0],
                'arrears_amount': ca[1][1],
            }
            return base
        elif len(ca) == 1:
            base['type'] = 'SALARY_WITH_ARREARS'
            base['details'] = {
                'regular_amount': ca[0][1],
                'currency': ca[0][0],
                'arrears_amount': 0,
            }
            return base

    # ── 18  FIRST SALARY ───────────────────────────────────────────
    if _matches_any(lo, [
        'first salary will be',
        'first salary from the new employer',
        'gaji pertama.*akan',
        'gaji pertama dari perusahaan baru',
        'gaji pertama anda sebesar',
        'first salary of',
    ]):
        ca = _extract_currency_amounts(text)
        dates = _extract_dates(text)
        if ca:
            base['type'] = 'FIRST_SALARY'
            base['details'] = {
                'amount': ca[0][1],
                'currency': ca[0][0],
                'credit_date': dates[0] if dates else None,
            }
            return base

    # ── 19  FOREIGN SALARY (confirmed for date, bank converts) ─────
    if _matches_any(lo, [
        'salary.*confirmed for.*receiving bank will convert',
        'gaji.*dikonfirmasi untuk.*bank.*mengonversi',
        'gaji sebesar.*dikonfirmasi untuk',
    ]):
        ca = _extract_currency_amounts(text)
        dates = _extract_dates(text)
        if ca and dates:
            base['type'] = 'FOREIGN_SALARY'
            base['details'] = {
                'amount': ca[0][1],
                'currency': ca[0][0],
                'settlement_date': dates[0],
            }
            return base

    # ── 20  CONFIRMED BASE SALARY (commission pending) ─────────────
    if _matches_any(lo, [
        'confirmed base salary is',
        'gaji pokok yang dikonfirmasi adalah',
    ]):
        ca = _extract_currency_amounts(text)
        if ca:
            base['type'] = 'BASE_SALARY_CONFIRMED'
            base['details'] = {'amount': ca[0][1], 'currency': ca[0][0]}
            return base

    # ── 21  RENT INCREASE ──────────────────────────────────────────
    if _matches_any(lo, [
        'lease increases monthly rent by',
        'sewa.*naik.*%',
        'rent.*increase',
    ]):
        pct = _pct(text)
        base['type'] = 'RENT_INCREASE'
        base['details'] = {'percentage': pct or 12}
        return base

    # ── 22  INVOICE / FREELANCE PAYMENT CONFIRMED ──────────────────
    if _matches_any(lo, [
        'client approved.*invoice payment of',
        'klien menyetujui.*pembayaran faktur',
        'client approved an invoice payment',
    ]):
        ca = _extract_currency_amounts(text)
        dates = _extract_dates(text)
        if ca:
            base['type'] = 'INVOICE_CONFIRMED'
            base['details'] = {
                'amount': ca[0][1],
                'currency': ca[0][0],
                'settlement_date': dates[0] if dates else None,
            }
            return base

    # ── 23  PRIZE SETTLED ──────────────────────────────────────────
    if _matches_any(lo, [
        'prize proceeds have reached your account',
        'hasil.*hadiah.*sudah masuk ke rekening',
    ]):
        base['type'] = 'PRIZE_SETTLED'
        return base

    # ── 24  PRIZE PENDING ──────────────────────────────────────────
    if _matches_any(lo, [
        'prize claim.*still in payment processing',
        'klaim hadiah.*masih dalam proses',
    ]):
        base['type'] = 'IGNORE'
        return base

    # ── 25  INVESTMENT SALE SETTLED ─────────────────────────────────
    if _matches_any(lo, [
        'investment sale have settled',
        'proceeds from your investment sale',
        'penjualan investasi.*sudah masuk',
        'hasil penjualan investasi',
    ]):
        base['type'] = 'INVESTMENT_SETTLED'
        return base

    # ── 26  REIMBURSEMENT (one-time, linked to work expense) ───────
    if _matches_any(lo, [
        'reimbursement for your earlier work expense',
        'penggantian biaya kerja',
    ]):
        base['type'] = 'REIMBURSEMENT'
        return base

    # ── 27  FAILED DEBIT (bill still outstanding) ──────────────────
    if _matches_any(lo, [
        'previous debit attempt failed',
        'bill is still outstanding',
    ]):
        base['type'] = 'FAILED_DEBIT_RETRY'
        return base

    # ── 28  PAYMENT RECEIPT (confirms payment was made) ────────────
    if _matches_any(lo, [
        'payment was received',
        'order was paid',
        'pembayaran.*diterima',
    ]):
        base['type'] = 'PAYMENT_RECEIPT'
        return base

    # ── 29  CONFIRMED SALARY (generic, amount + date in text) ──────
    # Catch-all for "your salary of X is confirmed for DATE"
    if _matches_any(lo, [
        'salary.*confirmed',
        'gaji.*dikonfirmasi',
    ]):
        ca = _extract_currency_amounts(text)
        dates = _extract_dates(text)
        if ca and dates:
            base['type'] = 'FIRST_SALARY'
            base['details'] = {
                'amount': ca[0][1],
                'currency': ca[0][0],
                'credit_date': dates[0],
            }
            return base

    # ── FALLBACK ───────────────────────────────────────────────────
    base['type'] = 'UNKNOWN'
    return base


def _matches_any(text_lower, patterns):
    """Check if text_lower matches any pattern (supports regex)."""
    for p in patterns:
        try:
            if re.search(p, text_lower):
                return True
        except re.error:
            if p in text_lower:
                return True
    return False
