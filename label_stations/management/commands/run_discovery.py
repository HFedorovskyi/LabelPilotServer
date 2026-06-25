import os
import socket
import json
import time
import threading
import uuid
from django.core.management.base import BaseCommand
from django.conf import settings
from label_stations.models import LabelsStations
from common.utils import get_local_ip

DISCOVERY_PORT = 5555
BROADCAST_IP = '255.255.255.255'

class Command(BaseCommand):
    help = 'Runs the UDP Discovery Service for finding Stations'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS(f'Starting Discovery Service on port {DISCOVERY_PORT}...'))
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            sock.bind(('', DISCOVERY_PORT))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error binding to port {DISCOVERY_PORT}: {e}"))
            return

        # Advertise the server over mDNS so LAN clients can use http://labelpilot.local:8000
        self.start_mdns()

        # Start Receive Thread
        receive_thread = threading.Thread(target=self.listen_for_stations, args=(sock,), daemon=True)
        receive_thread.start()

        # Start Broadcast Loop
        self.broadcast_loop(sock)

    def start_mdns(self):
        """Advertise the server over mDNS so LAN clients can reach http://<host>.local:<port>
        without renaming the PC or editing client hosts files. Best-effort and non-fatal:
        skips silently if zeroconf is unavailable or the network blocks mDNS (UDP 5353)."""
        try:
            from zeroconf import Zeroconf, ServiceInfo
        except ImportError:
            self.stdout.write("zeroconf not installed - skipping mDNS (.local) advertising")
            return
        try:
            ip = get_local_ip()
            host = os.getenv("MDNS_HOSTNAME", "labelpilot").strip().lower()
            port = int(os.getenv("PORT", "8000"))
            info = ServiceInfo(
                "_http._tcp.local.",
                "LabelPilot Server._http._tcp.local.",
                addresses=[socket.inet_aton(ip)],
                port=port,
                properties={b"path": b"/"},
                server=f"{host}.local.",
            )
            self._zeroconf = Zeroconf()            # keep a ref so it isn't garbage-collected
            self._zeroconf.register_service(info)
            self.stdout.write(self.style.SUCCESS(f"mDNS: advertising http://{host}.local:{port}/ -> {ip}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"mDNS registration failed (non-fatal): {e}"))

    def broadcast_loop(self, sock):
        while True:
            try:
                # Cleanup offline stations
                self.cleanup_offline_stations()

                # Get local IP (best guess)
                local_ip = get_local_ip()
                
                msg = json.dumps({
                    "type": "LABELPILOT_SERVER",
                    "ip": local_ip,
                    "port": 8000, # Assuming standard Django dev port, can be configurable
                    "timestamp": time.time()
                }).encode('utf-8')
                
                sock.sendto(msg, (BROADCAST_IP, DISCOVERY_PORT))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Broadcast error: {e}"))
            
            time.sleep(3)

    def cleanup_offline_stations(self):
        from django.utils import timezone
        from datetime import timedelta
        
        threshold = timezone.now() - timedelta(seconds=30)
        # Mark as offline if changed_at is older than threshold AND currently online
        updated_count = LabelsStations.objects.filter(
            is_online=True, 
            changed_at__lt=threshold
        ).update(is_online=False)
        
        if updated_count > 0:
            print(f"[INFO] Marked {updated_count} stations as offline.")

    def listen_for_stations(self, sock):
        while True:
            try:
                data, addr = sock.recvfrom(1024)
                try:
                    msg = json.loads(data.decode('utf-8'))
                    if msg.get('type') == 'LABELPILOT_STATION':
                        station_ip = msg.get('ip') or addr[0]
                        self.handle_station_discovery(msg, station_ip)
                except json.JSONDecodeError:
                    pass
            except Exception as e:
                print(f"Receive error: {e}")

    def handle_station_discovery(self, msg, ip):
        # Update or Create Station in DB
        
        station_id = msg.get('id') or msg.get('uuid')
        name = msg.get('name', f"Station {ip}")
        port = msg.get('port', 5000)
        
        # station_uuid is a UUIDField. An announcement may carry a NON-UUID id — e.g. a
        # client in built-in demo mode broadcasts 'demo-0000-...'. Using it in a query (or
        # create) raises ValidationError, which previously crashed this handler BEFORE the
        # IP fallback and spammed the log every 3s. Treat any non-UUID id as "no id": match
        # the station by IP instead (so the real station still goes online), and mint a
        # fresh uuid if we must create.
        valid_uuid = False
        if station_id:
            try:
                uuid.UUID(str(station_id))
                valid_uuid = True
            except (ValueError, AttributeError, TypeError):
                valid_uuid = False

        station = None
        if valid_uuid:
            station = LabelsStations.objects.filter(station_uuid=station_id).first()
        if not station:
            # Fallback to IP search (also how a non-UUID/demo announce is reconciled).
            station = LabelsStations.objects.filter(station_ip=ip).first()

        if station:
            station.station_ip = ip
            station.station_name = name
            station.station_port = port
            station.is_online = True
            station.save()
        else:
            # Create new -- but only if the seat limit allows it (no license -> unlimited).
            from licensing import seat_available
            if not seat_available(LabelsStations.objects.count()):
                print(f"[LICENSE] Seat limit reached - not registering new station from {ip} ({name}).")
                return
            generated_uuid = station_id if valid_uuid else uuid.uuid4()
            try:
                LabelsStations.objects.create(
                    station_ip=ip,
                    station_name=name,
                    station_port=port,
                    station_uuid=generated_uuid,
                    is_online=True
                )
            except Exception as e:
                print(f"[ERROR] Failed to register station from {ip} ({name}): {e}")


