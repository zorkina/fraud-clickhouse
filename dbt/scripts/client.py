import os


def connect():
    import clickhouse_connect
    return clickhouse_connect.get_client(
        host=os.getenv('CH_HOST','127.0.0.1'),
        port=int(os.getenv('CH_PORT','8124')),
        username=os.getenv('CH_USER','student'),
        password=os.getenv('CH_PASSWORD','fraud_local'),
        database='default',
        connect_timeout=10,
        send_receive_timeout=300,
        settings={'max_threads':2},
    )
