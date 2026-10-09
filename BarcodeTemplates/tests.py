"""The barcode preview builds the same data the station prints (src-tauri/src/barcode.rs)."""
from datetime import date

from django.contrib.auth.models import Group, User
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from api.auth_views import ensure_groups
from api.utils import BarcodeGenerator, validate_structure


class Product:
    article = "10231"
    is_fixed_weight = True
    fixed_weight_grams = 512
    exp_date = 30
    close_box_counter = 8
    extra_data = {"GTIN": "4870254930240"}


def build(fields, product=None):
    data, _warnings = BarcodeGenerator().decode_structure_barcode(fields, product=product or Product())
    return data


class PreviewMatchesStationTests(SimpleTestCase):
    def test_weighed_ean_parts(self):
        fields = [
            {"field_type": "constanta", "value": "21"},
            {"field_type": "article", "length": "5"},
            {"field_type": "weight_netto_pack", "length": "5", "decimalPlaces": "3"},
        ]
        self.assertEqual(build(fields), "211023100512")

    def test_numbers_are_padded_but_never_cut(self):
        # 12.345 kg does not fit 4 digits: the station keeps the whole number, so does the preview.
        heavy = type("Heavy", (Product,), {"fixed_weight_grams": 12345})()
        self.assertEqual(build([{"field_type": "weight_netto_pack", "length": "4", "decimalPlaces": "3"}], heavy), "12345")
        self.assertEqual(build([{"field_type": "article", "length": "3"}]), "10231")

    def test_article_of_14_digits_is_a_gtin14_with_check_digit(self):
        self.assertEqual(build([{"field_type": "article", "length": "14"}]), "00000000102315")
        self.assertEqual(build([{"field_type": "article"}]), "00000000102315", "14 is the station's default")

    def test_dates_default_to_gs1_order_and_ignore_length(self):
        today = date.today()
        self.assertEqual(build([{"field_type": "production_date", "length": "4"}]), today.strftime("%y%m%d"))
        self.assertEqual(build([{"field_type": "production_date", "dateFormat": "ddMMyyyy"}]), today.strftime("%d%m%Y"))

    def test_gs_is_not_written_into_the_data(self):
        fields = [{"field_type": "ai", "value": "10"}, {"field_type": "constanta", "value": "A1"}, {"field_type": "gs"}]
        self.assertEqual(build(fields), "(10)A1")

    def test_extra_field_and_count(self):
        self.assertEqual(build([{"field_type": "extra_data", "value": "GTIN"}]), "4870254930240")
        self.assertEqual(build([{"field_type": "pack_count", "length": "3"}]), "008")

    def test_best_before_identifier_is_allowed(self):
        structure = {"barcode_type": "gs1qrcode", "fields": [{"field_type": "ai", "value": "15"}, {"field_type": "exp_date", "dateFormat": "yyMMdd"}]}
        self.assertEqual(validate_structure(structure), [])


class PreviewEndpointTests(TestCase):
    """The server prepares the data; the admin panel draws the picture with bwip-js."""

    def setUp(self):
        ensure_groups()
        user = User.objects.create_user("chief", password="luna-kora-47")
        user.groups.add(Group.objects.get(name="admin"))
        self.client = APIClient()
        self.client.login(username="chief", password="luna-kora-47")

    def generate(self, structure):
        return self.client.post("/api/v1/barcodes/generate/", {"barcode_structure": structure}, format="json")

    def test_returns_the_type_and_data_without_a_picture(self):
        response = self.generate({"barcode_type": "ean13", "fields": [{"field_type": "constanta", "value": "460123456789"}]})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["barcode_type"], "ean13")
        self.assertEqual(body["data_string"], "4601234567893")
        self.assertNotIn("png", body)

    def test_gs1_data_keeps_the_identifiers_for_the_encoder(self):
        structure = {"barcode_type": "gs1qrcode", "fields": [{"field_type": "ai", "value": "10"}, {"field_type": "constanta", "value": "A1"}]}
        body = self.generate(structure).json()
        self.assertEqual((body["barcode_type"], body["data_string"]), ("gs1qrcode", "(10)A1"))

    def test_bad_ean_payload_is_still_an_error(self):
        response = self.generate({"barcode_type": "ean13", "fields": [{"field_type": "constanta", "value": "12345"}]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())
