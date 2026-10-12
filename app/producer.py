import argparse
import fcntl
import json
import os
import time
import uuid
from pathlib import Path

from app.csv_data import read_records, scan_source


def encode_record(record):
    return json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def inspect_topic(bootstrap, topic, source):
    from confluent_kafka import Consumer, TopicPartition

    consumer = Consumer({
        "bootstrap.servers": bootstrap,
        "group.id": "inspect-" + uuid.uuid4().hex,
        "enable.auto.commit": False,
        "enable.auto.offset.store": False,
    })
    try:
        metadata = consumer.list_topics(topic, timeout=30).topics.get(topic)
        if metadata is None or metadata.error:
            raise RuntimeError("Не найден топик transactions_ch")
        if len(metadata.partitions) != 1:
            raise RuntimeError("Для этого запуска нужна одна партиция Kafka")
        low, high = consumer.get_watermark_offsets(TopicPartition(topic, 0), timeout=30, cached=False)
        if low != 0 or high > source["rows"]:
            raise RuntimeError("Топик содержит другой набор данных. Повторная отправка остановлена")
        if not high:
            return 0, None
        consumer.assign([TopicPartition(topic, 0, high - 1)])
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            message = consumer.poll(1)
            if message is None:
                continue
            if message.error():
                raise RuntimeError(str(message.error()))
            if message.offset() != high - 1:
                raise RuntimeError("Не совпал последний offset Kafka")
            headers = dict(message.headers() or [])
            if headers.get("source_sha256") != source["sha256"].encode("ascii"):
                raise RuntimeError("В Kafka уже есть данные из другого файла")
            record = json.loads(message.value())
            if record.get("row_id") != high:
                raise RuntimeError("В Kafka нарушена последовательность row_id")
            return high, record
        raise TimeoutError("Не удалось прочитать последнее сообщение Kafka")
    finally:
        consumer.close()


def send(path, source=None):
    from confluent_kafka import Producer

    source = source or scan_source(path)
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    topic = os.getenv("KAFKA_TOPIC", "transactions_ch")
    Path("results").mkdir(exist_ok=True)
    with Path("results/.producer.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Отправка уже запущена в другом процессе") from exc
        existing, tail = inspect_topic(bootstrap, topic, source)
        producer = Producer({
            "bootstrap.servers": bootstrap,
            "enable.idempotence": True,
            "acks": "all",
            "compression.type": "gzip",
            "linger.ms": 20,
            "batch.size": 262144,
            "queue.buffering.max.messages": 10000,
            "delivery.timeout.ms": 120000,
        })
        errors = []
        acknowledged = 0

        def delivered(error, message):
            nonlocal acknowledged
            if error:
                if len(errors) < 3:
                    errors.append(str(error))
            else:
                acknowledged += 1

        if existing:
            print(f"В Kafka уже {existing} строк, повторно их не отправляю", flush=True)
        sent = 0
        try:
            for record in read_records(path):
                row_id = record["row_id"]
                if row_id <= existing:
                    if row_id == existing and record != tail:
                        raise RuntimeError("Последняя строка Kafka не совпала с CSV")
                    continue
                payload = encode_record(record)
                while True:
                    if errors:
                        raise RuntimeError("Ошибка доставки: " + "; ".join(errors))
                    try:
                        producer.produce(
                            topic, partition=0, key=str(row_id).encode("ascii"), value=payload,
                            headers={"source_sha256": source["sha256"].encode("ascii")}, on_delivery=delivered,
                        )
                        break
                    except BufferError:
                        producer.poll(0.1)
                sent += 1
                producer.poll(0)
                if row_id % 50000 == 0:
                    print(f"Передано в очередь: {row_id}/{source['rows']}", flush=True)
            remaining = producer.flush(150)
            if remaining or errors or acknowledged != sent:
                raise RuntimeError(f"Не все сообщения подтверждены: {acknowledged}/{sent}; {errors}")
        finally:
            producer.flush(5)
        high, _ = inspect_topic(bootstrap, topic, source)
        if high != source["rows"]:
            raise RuntimeError(f"В Kafka {high} строк вместо {source['rows']}")
        print(f"Kafka: {high} сообщений, все подтверждены брокером", flush=True)
        return high


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/test.csv")
    arguments = parser.parse_args()
    send(Path(arguments.csv))


if __name__ == "__main__":
    main()
