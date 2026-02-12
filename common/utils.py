import socket

def send_notification(message):
    """Stub — notifications are not currently implemented."""
    pass

import os

def get_local_ip():
    env_ip = os.environ.get('SERVER_EXTERNAL_IP')
    if env_ip:
        return env_ip
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# ...
        # Doesn't need to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
        s.close()
    except Exception:
        IP = '127.0.0.1'
    return IP
