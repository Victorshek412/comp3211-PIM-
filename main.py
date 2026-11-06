"""Start the Part C terminal with the demonstration services."""
from controller import Controller
from model.demo import DemoModel, DemoServices


def main():
    records = DemoModel()
    services = DemoServices(records)
    print("PIM | Part C demo backend")
    return Controller(records, services.search, services).run()


if __name__ == "__main__":
    raise SystemExit(main())
