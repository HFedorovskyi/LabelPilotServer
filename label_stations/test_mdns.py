"""The built-in mDNS responder that replaced python-zeroconf (label_stations/mdns.py)."""
import socket
import struct

from django.test import SimpleTestCase

from label_stations import mdns
from label_stations.mdns import Responder

IP = "192.168.10.5"


def query(*questions, query_id=0, unicast=False):
    out = bytearray(struct.pack("!HHHHHH", query_id, 0, len(questions), 0, 0, 0))
    for name, qtype in questions:
        out += mdns.encode_name(name) + struct.pack("!HH", qtype, mdns.CLASS_IN | (mdns.UNICAST_RESPONSE if unicast else 0))
    return bytes(out)


def parse_response(packet):
    """[(name, type, class, ttl, rdata)] of the answer section."""
    _id, flags, qd, an, _ns, _ar = struct.unpack("!HHHHHH", packet[:12])
    assert flags & 0x8000
    offset = 12
    for _ in range(qd):
        _name, offset = mdns.decode_name(packet, offset)
        offset += 4
    answers = []
    for _ in range(an):
        name, offset = mdns.decode_name(packet, offset)
        rtype, klass, ttl, length = struct.unpack("!HHIH", packet[offset:offset + 10])
        offset += 10
        answers.append((name, rtype, klass, ttl, packet[offset:offset + length]))
        offset += length
    return answers


class ResponderTests(SimpleTestCase):
    def setUp(self):
        self.responder = Responder("LabelPilot", 8000)

    def answer(self, packet, legacy=False):
        query_id, _flags, questions = mdns.parse_questions(packet)
        records = self.responder.answers_for(questions, IP)
        return parse_response(Responder.build_response(records, query_id, questions, legacy=legacy))

    def test_the_host_name_resolves_to_the_server_address(self):
        answers = self.answer(query(("labelpilot.local", mdns.TYPE_A)))
        self.assertEqual(len(answers), 1)
        name, rtype, klass, ttl, rdata = answers[0]
        self.assertEqual((name, rtype, socket.inet_ntoa(rdata)), ("labelpilot.local", mdns.TYPE_A, IP))
        self.assertEqual(klass, mdns.CLASS_IN | mdns.CACHE_FLUSH)
        self.assertEqual(ttl, mdns.HOST_TTL)

    def test_names_are_matched_without_case(self):
        self.assertEqual(len(self.answer(query(("LabelPilot.LOCAL", mdns.TYPE_A)))), 1)

    def test_other_names_and_types_get_no_answer(self):
        self.assertEqual(self.answer(query(("printer.local", mdns.TYPE_A))), [])
        self.assertEqual(self.answer(query(("labelpilot.local", 28))), [])  # AAAA

    def test_service_browse_returns_the_instance_and_the_host_address(self):
        answers = self.answer(query(("_http._tcp.local", mdns.TYPE_PTR)))
        by_type = {rtype: (name, rdata) for name, rtype, _k, _t, rdata in answers}
        self.assertEqual(mdns.decode_name(by_type[mdns.TYPE_PTR][1], 0)[0], "LabelPilot Server._http._tcp.local")
        self.assertEqual(socket.inet_ntoa(by_type[mdns.TYPE_A][1]), IP)

    def test_any_question_gets_srv_with_the_port_and_txt(self):
        answers = self.answer(query(("LabelPilot Server._http._tcp.local", mdns.TYPE_ANY)))
        srv = next(rdata for _n, rtype, _k, _t, rdata in answers if rtype == mdns.TYPE_SRV)
        priority, weight, port = struct.unpack("!HHH", srv[:6])
        self.assertEqual((priority, weight, port), (0, 0, 8000))
        self.assertEqual(mdns.decode_name(srv, 6)[0], "labelpilot.local")
        txt = next(rdata for _n, rtype, _k, _t, rdata in answers if rtype == mdns.TYPE_TXT)
        self.assertEqual(txt, b"\x06path=/")

    def test_a_plain_dns_resolver_gets_its_id_back_and_short_ttls(self):
        packet = Responder.build_response(
            self.responder.answers_for([("labelpilot.local", mdns.TYPE_A, False)], IP),
            query_id=0x1234, questions=[("labelpilot.local", mdns.TYPE_A, False)], legacy=True)
        self.assertEqual(struct.unpack("!H", packet[:2])[0], 0x1234)
        _name, _rtype, klass, ttl, _rdata = parse_response(packet)[0]
        self.assertEqual(klass, mdns.CLASS_IN)
        self.assertLessEqual(ttl, 10)

    def test_compressed_question_names_are_read(self):
        # Two questions; the second points back at "local" of the first (offset 12 + 11).
        header = struct.pack("!HHHHHH", 0, 0, 2, 0, 0, 0)
        first = mdns.encode_name("labelpilot.local") + struct.pack("!HH", mdns.TYPE_A, mdns.CLASS_IN)
        second = b"\x05_http\x04_tcp\xc0\x17" + struct.pack("!HH", mdns.TYPE_PTR, mdns.CLASS_IN)
        _id, _flags, questions = mdns.parse_questions(header + first + second)
        self.assertEqual([q[0] for q in questions], ["labelpilot.local", "_http._tcp.local"])

    def test_responses_and_garbage_are_not_treated_as_queries(self):
        response = Responder.build_response(self.responder.records(IP))
        self.assertIsNone(mdns.parse_questions(response))
        self.assertIsNone(mdns.parse_questions(b"\x00\x01"))
        with self.assertRaises(ValueError):
            mdns.parse_questions(struct.pack("!HHHHHH", 0, 0, 1, 0, 0, 0) + b"\xc0\xff")
