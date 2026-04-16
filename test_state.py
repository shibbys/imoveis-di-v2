from scrapers.runner import get_live_state, _live_logs, _running
print(f"Running: {_running}")
print(f"Live logs: {_live_logs}")
print(f"State: {get_live_state()}")
