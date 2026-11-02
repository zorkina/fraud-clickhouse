import fcntl
import json
from pathlib import Path
from scripts.client import connect
from scripts.data import FIELDS, records, source_stats

DDL = '''
CREATE TABLE transactions_db.transactions_loading (
    row_id UInt64,
    transaction_time DateTime('UTC'),
    merch String,
    cat_id String,
    amount Float64,
    name_1 String,
    name_2 String,
    gender String,
    us_state String,
    lat Float64,
    lon Float64,
    merchant_lat Float64,
    merchant_lon Float64,
    target UInt8
) ENGINE = MergeTree ORDER BY row_id
'''


def table_stats(client, table):
    return client.query(f'''
        SELECT count(), uniqExact(row_id), sum(toUInt64(target)),
               sum(toDecimal64(toString(amount), 2))
        FROM transactions_db.{table}
    ''').first_row


def verify(stats, expected):
    count, unique, frauds, amount = stats
    if (count, unique, frauds, int(amount * 100)) != (
        expected['rows'], expected['rows'], expected['fraud_count'], expected['amount_cents']
    ):
        raise RuntimeError('Число строк, уникальность или контрольные суммы загрузки не совпали')


def _load(path):
    expected = source_stats(path)
    client = connect()
    client.command('CREATE DATABASE IF NOT EXISTS transactions_db ENGINE = Atomic')
    exists = int(client.command('EXISTS TABLE transactions_db.transactions'))
    marker = 'source_sha256=' + expected['sha256']
    if exists:
        comment = client.command("SELECT comment FROM system.tables WHERE database='transactions_db' AND name='transactions'")
        if comment != marker:
            raise RuntimeError('transactions_db.transactions уже содержит другой источник. Данные не изменены.')
        verify(table_stats(client, 'transactions'), expected)
    else:
        client.command('DROP TABLE IF EXISTS transactions_db.transactions_loading')
        client.command(DDL + " COMMENT '" + marker + "'")
        columns = ['row_id'] + FIELDS
        batch = []
        for row in records(path):
            values = [row[key] for key in columns]
            values[columns.index('amount')] = float(row['amount'])
            batch.append(values)
            if len(batch) == 10000:
                client.insert('transactions_db.transactions_loading', batch, column_names=columns)
                batch.clear()
        if batch:
            client.insert('transactions_db.transactions_loading', batch, column_names=columns)
        verify(table_stats(client, 'transactions_loading'), expected)
        client.command('RENAME TABLE transactions_db.transactions_loading TO transactions_db.transactions')
    Path('evidence').mkdir(exist_ok=True)
    Path('evidence/source.json').write_text(json.dumps(expected,indent=2)+'\n')
    print(f"Источник: {expected['rows']} строк, меток фрода: {expected['fraud_count']}")
    client.close()


def load(path):
    with Path('data/.load.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _load(path)


if __name__ == '__main__':
    load(Path('data/train.csv'))
