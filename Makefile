.PHONY: help build up down restart logs migrate shell test lint check-env

help:
	@echo "Available commands:"
	@echo "  build       Build docker images"
	@echo "  up          Start services"
	@echo "  down        Stop services"
	@echo "  restart     Restart services"
	@echo "  logs        Show logs"
	@echo "  migrate     Run migrations"
	@echo "  shell       Open django shell"
	@echo "  test        Run tests"
	@echo "  lint        Run ruff and bandit"
	@echo "  check-env   Run environment validation script"

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f

migrate:
	docker-compose exec web python manage.py migrate

shell:
	docker-compose exec web python manage.py shell

test:
	docker-compose exec web coverage run manage.py test accounts organization enrollment academics -v 2
	docker-compose exec web coverage report

lint:
	ruff check .
	bandit -r . -x ./tests

check-env:
	python scripts/validate_env.py
