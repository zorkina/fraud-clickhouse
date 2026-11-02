import csv
import hashlib
import math
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIELDS = ['transaction_time', 'merch', 'cat_id', 'amount', 'name_1', 'name_2', 'gender',
          'us_state', 'lat', 'lon', 'merchant_lat', 'merchant_lon', 'target']


def fingerprint(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def records(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        missing = sorted(set(FIELDS) - set(reader.fieldnames or []))
        if missing:
            raise ValueError(f'Нет обязательных столбцов: {missing}. Нужен размеченный train.csv.')
        for number, row in enumerate(reader, 1):
            try:
                if any(row.get(key) is None for key in FIELDS):
                    raise ValueError('неполная строка')
                when = datetime.fromisoformat(row['transaction_time'])
                if when.tzinfo is not None:
                    raise ValueError('ожидается исходное время без часового пояса')
                value = Decimal(row['amount'])
                if not value.is_finite() or value < 0 or value != value.quantize(Decimal('0.01')):
                    raise ValueError('сумма должна быть конечной, неотрицательной и с точностью до сотых')
                if value >= Decimal('10000000000000000'):
                    raise ValueError('сумма не помещается в Decimal(18,2)')
                if row['target'].strip() not in ('0', '1'):
                    raise ValueError('target должен быть 0 или 1')
                coords = [float(row[key]) for key in ('lat', 'lon', 'merchant_lat', 'merchant_lon')]
                if any(not math.isfinite(x) or abs(x) > limit for x, limit in zip(coords, (90,180,90,180))):
                    raise ValueError('некорректные координаты')
                if any(not row[key].strip() for key in ('merch','cat_id','name_1','name_2','gender','us_state')):
                    raise ValueError('пустое категориальное поле')
                if row['gender'].strip().upper() not in ('M','F'):
                    raise ValueError('неизвестное значение gender')
                yield {
                    'row_id': number, 'transaction_time': when, 'merch': row['merch'],
                    'cat_id': row['cat_id'], 'amount': value, 'name_1': row['name_1'],
                    'name_2': row['name_2'], 'gender': row['gender'], 'us_state': row['us_state'],
                    **dict(zip(('lat','lon','merchant_lat','merchant_lon'), coords)),
                    'target': int(row['target']),
                }
            except (ValueError, InvalidOperation) as error:
                raise ValueError(f'Строка {number + 1}: {error}') from error


def source_stats(path):
    count = frauds = cents = 0
    for row in records(path):
        count += 1
        frauds += row['target']
        cents += int(row['amount'] * 100)
    if count == 0:
        raise ValueError('CSV не содержит транзакций')
    return {'rows':count, 'fraud_count':frauds, 'amount_cents':cents, 'sha256':fingerprint(path)}
