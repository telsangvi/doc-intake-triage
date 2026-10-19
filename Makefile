.PHONY: install demo eval test api clean

install:
	pip install -r requirements.txt

# Process the sample documents and print a review queue.
demo:
	python -m src.cli run data/samples

# Run the evaluation harness against the labelled gold set.
eval:
	python -m src.cli eval

test:
	pytest -q

# Start the API + review-queue UI at http://127.0.0.1:8000
api:
	uvicorn src.api:app --reload

clean:
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
