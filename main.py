"""Start the Part C terminal with the demonstration services."""
from controller import Controller
from model.demo import DemoServices
from model.record_manager import RecordManager

def main():
    records = RecordManager()
    services = DemoServices(records)
    print("PIM | System Ready")
    return Controller(records, services.search, services).run()

if __name__ == "__main__":
    raise SystemExit(main())