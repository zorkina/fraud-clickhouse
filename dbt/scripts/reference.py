import math
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

MARTS = {
    'mart_daily_state_metrics': ('transaction_date', 'us_state'),
    'mart_fraud_by_category': ('category',),
    'mart_fraud_by_state': ('us_state',),
    'mart_customer_risk_profile': (),
    'mart_hourly_fraud_pattern': ('day_of_week', 'transaction_hour'),
    'mart_merchant_analytics': ('merchant',),
}


def new_group():
    return {'n': 0, 'frauds': 0, 'cents': 0, 'fraud_cents': 0, 'large': 0,
            'customers': set(), 'merchants': set(), 'dates': set(), 'amounts': [],
            'first': None, 'last': None, 'maximum': 0}


def update(group, row, customer, config, collect_amounts=False):
    when = row['transaction_time']
    cents = int(row['amount'] * 100)
    group['n'] += 1
    group['frauds'] += row['target']
    group['cents'] += cents
    group['fraud_cents'] += cents * row['target']
    group['large'] += row['amount'] >= config['large_amount']
    group['customers'].add(customer)
    group['merchants'].add(row['merch'].strip())
    group['dates'].add(when.date())
    group['first'] = min(group['first'], when) if group['first'] else when
    group['last'] = max(group['last'], when) if group['last'] else when
    group['maximum'] = max(group['maximum'], cents)
    if collect_amounts:
        group['amounts'].append(cents)


def percentage(numerator, denominator):
    return 100.0 * numerator / denominator if denominator else 0.0


def basic(group):
    return {
        'transactions_count': group['n'], 'fraud_count': group['frauds'],
        'fraud_rate': percentage(group['frauds'], group['n']),
        'total_amount': Decimal(group['cents']) / 100,
        'fraud_amount': Decimal(group['fraud_cents']) / 100,
    }


def percentile(values, q):
    ordered = sorted(values)
    if not ordered:
        raise ValueError('Перцентиль пустой группы не определен')
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    return (ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)) / 100.0


def build_reference(rows, config, states):
    groups = {name: defaultdict(new_group) for name in MARTS}
    total_count = total_frauds = 0
    for row in rows:
        when = row['transaction_time']
        state = row['us_state'].strip().upper()
        if state not in states:
            raise ValueError(f'Неизвестный код штата: {state}')
        customer = (row['name_1'].strip().upper(), row['name_2'].strip().upper(),
                    row['gender'].strip().upper(), state, row['lat'], row['lon'])
        keys = {
            'mart_daily_state_metrics': (when.date(), state),
            'mart_fraud_by_category': row['cat_id'].strip().lower(),
            'mart_fraud_by_state': state,
            'mart_customer_risk_profile': customer,
            'mart_hourly_fraud_pattern': (when.isoweekday(), when.hour),
            'mart_merchant_analytics': row['merch'].strip(),
        }
        for name, key in keys.items():
            update(groups[name][key], row, customer, config, name == 'mart_daily_state_metrics')
        total_count += 1
        total_frauds += row['target']
    output = {name: [] for name in MARTS}
    baseline = percentage(total_frauds, total_count)
    for name, keyed in groups.items():
        for key, group in keyed.items():
            result = basic(group)
            if name == 'mart_daily_state_metrics':
                result = {
                    'transaction_date': key[0], 'us_state': key[1],
                    'transactions_count': group['n'], 'total_amount': Decimal(group['cents']) / 100,
                    'average_amount': group['cents'] / 100.0 / group['n'],
                    'p95_amount': percentile(group['amounts'], 0.95),
                    'large_transactions_count': group['large'],
                    'large_transactions_pct': percentage(group['large'], group['n']),
                }
            elif name == 'mart_fraud_by_category':
                result.update(category=key, fraud_amount_pct=percentage(group['fraud_cents'], group['cents']))
            elif name == 'mart_fraud_by_state':
                result.update(us_state=key, state_name=states[key],
                              unique_customers=len(group['customers']), unique_merchants=len(group['merchants']))
            elif name == 'mart_customer_risk_profile':
                high = group['n'] >= config['customer_high_min_transactions'] and result['fraud_rate'] >= config['customer_high_fraud_rate']
                result.update(first_transaction_at=group['first'], last_transaction_at=group['last'],
                              active_days=len(group['dates']), average_amount=group['cents'] / 100.0 / group['n'],
                              max_amount=Decimal(group['maximum']) / 100,
                              insufficient_history=int(group['n'] < config['customer_high_min_transactions']),
                              risk_level='HIGH' if high else 'MEDIUM' if group['frauds'] else 'LOW')
            elif name == 'mart_hourly_fraud_pattern':
                high = (group['n'] >= config['hourly_min_transactions'] and group['frauds'] > 0
                        and result['fraud_rate'] >= config['hourly_risk_lift'] * baseline)
                result.update(day_of_week=key[0], transaction_hour=key[1], baseline_fraud_rate=baseline,
                              risk_lift=result['fraud_rate'] / baseline if baseline else 0.0, is_high_risk=int(high))
            elif name == 'mart_merchant_analytics':
                flag = group['n'] >= config['merchant_min_transactions'] and result['fraud_rate'] >= config['merchant_fraud_rate']
                result.update(merchant=key, unique_customers=len(group['customers']),
                              average_amount=group['cents'] / 100.0 / group['n'],
                              first_transaction_date=group['first'].date(), last_transaction_date=group['last'].date(),
                              is_suspicious=int(flag))
            output[name].append(result)
    return output


def normalized(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat(sep=' ')
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value.normalize(), 'f')
    return value


def sort_key(row):
    return tuple(str(normalized(row[key])) for key in sorted(row) if key not in ('customer_id', 'average_amount', 'fraud_rate'))


def compare_rows(name, expected, actual):
    if len(expected) != len(actual):
        raise AssertionError(f'{name}: ожидалось {len(expected)} групп, получено {len(actual)}')
    keys = MARTS[name]
    if keys:
        by_key = {tuple(normalized(row[key]) for key in keys): row for row in actual}
        if len(by_key) != len(actual):
            raise AssertionError(f'{name}: повторяющийся ключ витрины')
        pairs = []
        for row in expected:
            key = tuple(normalized(row[field]) for field in keys)
            if key not in by_key:
                raise AssertionError(f'{name}: отсутствует группа {key}')
            pairs.append((row, by_key[key]))
    else:
        if len({row['customer_id'] for row in actual}) != len(actual):
            raise AssertionError('Повторяющийся customer_id')
        pairs = zip(sorted(expected, key=sort_key), sorted(actual, key=sort_key))
    for reference, result in pairs:
        for field, value in reference.items():
            found = result.get(field)
            if isinstance(value, float):
                equal = found is not None and math.isfinite(float(found)) and math.isclose(value, float(found), rel_tol=1e-9, abs_tol=1e-8)
            else:
                equal = normalized(value) == normalized(found)
            if not equal:
                raise AssertionError(f'{name}.{field}: ожидалось {value!r}, получено {found!r}')
