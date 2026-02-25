import subprocess

print("Starting ML API in unsupervised real-time mode...")
subprocess.run(["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9092"])
