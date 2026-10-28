run: for file manager
	cd "C:\Users\USER\Desktop\project\file_management"
>> $env:PROCESSING_MANAGER_URL = "http://127.0.0.1:8002"
>> $env:PYTHONPATH = "Source code"
>> .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir "Source code" --host 127.0.0.1 --port 8001 --reload


run: for data processing manager
Set-Location "C:\Users\USER\Desktop\project\data_processing_manager"; .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir "source code" --host 127.0.0.1 --port 8002Set-Location "C:\Users\USER\Desktop\project\data_processing_manager"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir "source code" --host 127.0.0.1 --port 8002