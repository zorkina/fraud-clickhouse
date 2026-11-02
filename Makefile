.PHONY: start test lint docs stop

start:
	bash dbt/start.sh

test:
	cd dbt && docker compose run --rm tools dbt test

lint:
	bash dbt/lint.sh

docs:
	cd dbt && docker compose run --rm tools dbt docs generate
	cd dbt && docker compose up -d docs

stop:
	cd dbt && docker compose down
