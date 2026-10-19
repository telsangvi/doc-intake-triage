.PHONY: install demo eval tune ft retrieve test api docker clean

install:
	pip install -r requirements.txt

# Process the sample documents and print a review queue.
demo:
	python -m src.cli run data/samples

# Run the evaluation harness against the labelled gold set.
eval:
	python -m src.cli eval

# Grid-search the routing thresholds.
tune:
	python -m src.cli tune

# Write a fine-tune dataset (does not launch a job).
ft:
	python -m src.cli export-ft

# Inspect the policy retrieval index.
retrieve:
	python -m src.cli retrieve "income evidence"

test:
	pytest -q

# Start the API + review-queue UI at http://127.0.0.1:8000
api:
	uvicorn src.api:app --reload

docker:
	docker compose up --build

clean:
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache
