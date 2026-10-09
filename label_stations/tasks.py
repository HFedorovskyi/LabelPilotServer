# Celery removed. The former periodic task `update_client_status` (marking stale
# stations offline) is already handled inside the discovery loop:
# label_stations/management/commands/run_discovery.py -> cleanup_offline_stations().
