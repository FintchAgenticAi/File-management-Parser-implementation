run:
	$env:PROCESSING_MANAGER_URL = "http://127.0.0.1:8001"
	$env:PYTHONPATH = "Source code"
	& ".venv\Scripts\python.exe" -m uvicorn app.main:app --app-dir "Source code" --host 127.0.0.1 --port 8000
