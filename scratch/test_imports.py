import sys
import os

# Добавляем bot в пути импорта
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "bot")))

try:
    print("Importing app.cabinet.routes...")
    import app.cabinet.routes
    print("SUCCESS: All routes imported successfully! No syntax errors.")
except Exception as e:
    print("ERROR during import:")
    import traceback
    traceback.print_exc()
    sys.exit(1)
