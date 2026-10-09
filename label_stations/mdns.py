"""A small mDNS responder (RFC 6762/6763) so the admin panel opens at http://<host>.local:<port>.

It answers for one host name (A record) and one HTTP service (PTR/SRV/TXT), which is all the
server used python-zeroconf for; zeroconf is LGPL, and its replaceability conflicts with the
signed runtime. No probing or conflict resolution: on a shop-floor LAN there is one server.
"""
import socket
import struct
import threading
import time

MDNS_GROUP = "224.0.0.251"
MDNS_PORT = 5353

TYPE_A = 1
TYPE_PTR = 12
TYPE_TXT = 16
TYPE_SRV = 33
TYPE_ANY = 255
CLASS_IN = 1
CACHE_FLUSH = 0x8000
UNICAST_RESPONSE = 0x8000

HOST_TTL = 120
SERVICE_TTL = 4500
SERVICE_TYPE = "_http._tcp.local"
DISCOVERY_NAME = "_services._dns-sd._udp.local"


def encode_name(name):
    out = bytearray()
    for label in name.rstrip(".").split("."):
        raw = label.encode("utf-8")
        if not raw or len(raw) > 63:
            raise ValueError(f"bad DNS label in {name!r}")
        out += bytes([len(raw)]) + raw
    return bytes(out + b"\x00")


def decode_name(packet, offset):
    """Reads a possibly compressed name; returns (name, offset after it)."""
    labels, end, jumps = [], None, 0
    while True:
        if offset >= len(packet):
            raise ValueError("name runs past the packet")
        length = packet[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet) or jumps > 16:
                raise ValueError("bad compression pointer")
            if end is None:
                end = offset + 2
            offset = ((length & 0x3F) << 8) | packet[offset + 1]
            jumps += 1
            continue
        offset += 1
        if length == 0:
            break
        labels.append(packet[offset:offset + length].decode("utf-8", "replace"))
        offset += length
    return ".".join(labels), (end if end is not None else offset)


def parse_questions(packet):
    """(id, flags, [(name, qtype, unicast)]) of a query; None for anything else."""
    if len(packet) < 12:
        return None
    query_id, flags, qdcount = struct.unpack("!HHH", packet[:6])
    if flags & 0x8000:  # a response, not a query
        return None
    questions, offset = [], 12
    for _ in range(qdcount):
        name, offset = decode_name(packet, offset)
        if offset + 4 > len(packet):
            raise ValueError("question runs past the packet")
        qtype, qclass = struct.unpack("!HH", packet[offset:offset + 4])
        offset += 4
        questions.append((name.lower(), qtype, bool(qclass & UNICAST_RESPONSE)))
    return query_id, flags, questions


class Responder:
    def __init__(self, host, port, instance="LabelPilot Server", ip_lookup=None):
        self.host = f"{host.strip().lower()}.local"
        self.port = int(port)
        self.instance = f"{instance}.{SERVICE_TYPE}"
        self.ip_lookup = ip_lookup
        self.sock = None

    def records(self, ip):
        """Every record we own: (name, type, ttl, cache_flush, rdata)."""
        srv = struct.pack("!HHH", 0, 0, self.port) + encode_name(self.host)
        txt = bytes([len(b"path=/")]) + b"path=/"
        return [
            (self.host, TYPE_A, HOST_TTL, True, socket.inet_aton(ip)),
            (SERVICE_TYPE, TYPE_PTR, SERVICE_TTL, False, encode_name(self.instance)),
            (DISCOVERY_NAME, TYPE_PTR, SERVICE_TTL, False, encode_name(SERVICE_TYPE)),
            (self.instance, TYPE_SRV, HOST_TTL, True, srv),
            (self.instance, TYPE_TXT, SERVICE_TTL, True, txt),
        ]

    def answers_for(self, questions, ip):
        wanted = []
        for name, qtype, _unicast in questions:
            for record in self.records(ip):
                if record[0].lower() == name and qtype in (record[1], TYPE_ANY) and record not in wanted:
                    wanted.append(record)
        # A service answer is useless without the host's address: add it.
        if any(r[1] in (TYPE_PTR, TYPE_SRV) for r in wanted):
            host_a = self.records(ip)[0]
            if host_a not in wanted:
                wanted.append(host_a)
        return wanted

    @staticmethod
    def build_response(records, query_id=0, questions=(), legacy=False):
        """A response packet; a legacy (non-5353) query gets its id and questions echoed."""
        out = bytearray(struct.pack("!HHHHHH", query_id if legacy else 0, 0x8400,
                                    len(questions) if legacy else 0, len(records), 0, 0))
        if legacy:
            for name, qtype, _unicast in questions:
                out += encode_name(name) + struct.pack("!HH", qtype, CLASS_IN)
        for name, rtype, ttl, flush, rdata in records:
            # RFC 6762 6.7: no cache-flush bit and at most 10 s TTL to legacy resolvers.
            klass = CLASS_IN | (CACHE_FLUSH if flush and not legacy else 0)
            out += encode_name(name) + struct.pack("!HHIH", rtype, klass, min(ttl, 10) if legacy else ttl, len(rdata)) + rdata
        return bytes(out)

    def current_ip(self):
        return self.ip_lookup() if self.ip_lookup else socket.gethostbyname(socket.gethostname())

    def open(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # Windows runs its own mDNS on 5353: share the port.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", MDNS_PORT))
        ip = self.current_ip()
        membership = socket.inet_aton(MDNS_GROUP) + socket.inet_aton(ip)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        self.sock = sock
        return ip

    def announce(self):
        ip = self.current_ip()
        packet = self.build_response(self.records(ip))
        for _ in range(2):  # RFC 6762 8.3: at least twice, a second apart
            self.sock.sendto(packet, (MDNS_GROUP, MDNS_PORT))
            time.sleep(1)

    def serve_forever(self):
        while True:
            try:
                packet, (address, source_port) = self.sock.recvfrom(9000)
                parsed = parse_questions(packet)
                if not parsed:
                    continue
                query_id, _flags, questions = parsed
                ip = self.current_ip()
                records = self.answers_for(questions, ip)
                if not records:
                    continue
                if source_port != MDNS_PORT:
                    # A plain DNS resolver asking 224.0.0.251 directly: answer it alone.
                    self.sock.sendto(self.build_response(records, query_id, questions, legacy=True), (address, source_port))
                elif all(unicast for _n, _t, unicast in questions):
                    self.sock.sendto(self.build_response(records), (address, source_port))
                else:
                    self.sock.sendto(self.build_response(records), (MDNS_GROUP, MDNS_PORT))
            except (ValueError, struct.error, UnicodeError):
                continue  # a malformed packet from the LAN
            except OSError:
                time.sleep(1)

    def start(self):
        """Opens the socket, announces and answers in a daemon thread. Returns the address."""
        ip = self.open()
        threading.Thread(target=self._run, name="mdns", daemon=True).start()
        return ip

    def _run(self):
        self.announce()
        self.serve_forever()
