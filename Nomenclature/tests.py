"""Products a station cannot print: no pack label template (the station refuses the pack)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from LabelTemplates.models import LabelTemplates

from .models import Nomenclature


class NoTemplateTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_superuser("chief", password="x"))
        pack = LabelTemplates.objects.create(name="Pack 58x40", scheme={})
        box = LabelTemplates.objects.create(name="Box", scheme={})
        make = lambda article, **fields: Nomenclature.objects.create(name=article, article=article, exp_date=10, close_box_counter=10, **fields)
        self.ready = make("1", templates_pack_label=pack)
        self.box_only = make("2", templates_box_label=box)
        self.bare = make("3")

    def test_filter_lists_products_without_a_pack_template(self):
        rows = self.client.get("/api/v1/nomenclature/", {"no_template": "1"}).json()
        self.assertEqual(sorted(row["article"] for row in rows), ["2", "3"])
        self.assertEqual(len(self.client.get("/api/v1/nomenclature/").json()), 3)

    def test_dashboard_counts_the_same_products(self):
        readiness = self.client.get("/api/v1/statistics/").json()["readiness"]
        self.assertEqual(readiness["products_without_template"], 2)


class FieldDeletionTests(TestCase):
    def test_deleting_a_field_removes_its_values_from_products(self):
        from .models import GlobalProductAttribute
        client = APIClient()
        client.force_authenticate(get_user_model().objects.create_superuser("chief", password="x"))
        field = GlobalProductAttribute.objects.create(name="Состав")
        product = Nomenclature.objects.create(name="Ham", article="1", exp_date=10, close_box_counter=10,
                                              extra_data={"Состав": "Свинина", "Цена": "5"})
        # An hour back, so a coarse clock (Windows) cannot make the bump invisible.
        import datetime
        before = product.edited - datetime.timedelta(hours=1)
        Nomenclature.objects.filter(pk=product.pk).update(edited=before)
        self.assertEqual(client.delete(f"/api/v1/attributes/{field.pk}/").status_code, 204)
        product.refresh_from_db()
        self.assertEqual(product.extra_data, {"Цена": "5"})
        self.assertGreater(product.edited, before)


class TareAndTemplateChangeTests(TestCase):
    """A new tare weight or template reaches stations only with the next push: the
    products that use it count as changed, the others do not."""

    def setUp(self):
        import datetime
        from Packs.models import Pack
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_superuser("chief", password="x"))
        self.tray = Pack.objects.create(name="Tray", weight=0)
        self.box = Pack.objects.create(name="Box", weight=400)
        self.template = LabelTemplates.objects.create(name="Pack 58x40", scheme={})
        make = lambda article, **fields: Nomenclature.objects.create(name=article, article=article, exp_date=10, close_box_counter=10, **fields)
        self.on_tray = make("1", portion_container=self.tray, templates_pack_label=self.template)
        self.in_box = make("2", box_container=self.box)
        self.other = make("3")
        # An hour back, so a coarse clock (Windows) cannot hide the bump.
        self.before = self.other.edited - datetime.timedelta(hours=1)
        Nomenclature.objects.update(edited=self.before)

    def edited(self, product):
        product.refresh_from_db()
        return product.edited

    def test_new_tare_weight_marks_its_products(self):
        self.assertEqual(self.client.patch(f"/api/v1/packs/{self.tray.pk}/", {"weight": 12}, format="json").status_code, 200)
        self.assertGreater(self.edited(self.on_tray), self.before)
        self.assertEqual(self.edited(self.in_box), self.before)
        self.assertEqual(self.edited(self.other), self.before)

    def test_removed_box_marks_its_products(self):
        self.assertEqual(self.client.delete(f"/api/v1/packs/{self.box.pk}/").status_code, 204)
        self.assertGreater(self.edited(self.in_box), self.before)
        self.in_box.refresh_from_db()
        self.assertIsNone(self.in_box.box_container)
        self.assertEqual(self.edited(self.on_tray), self.before)

    def test_saved_template_marks_its_products(self):
        response = self.client.patch(f"/api/v1/labels/{self.template.pk}/", {"name": "Pack 58x40 v2"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(self.edited(self.on_tray), self.before)
        self.assertEqual(self.edited(self.other), self.before)


class BarcodeChangeTests(TestCase):
    """A changed barcode reaches stations with the label templates that use it."""

    def setUp(self):
        import datetime
        from BarcodeTemplates.models import BarcodeTemplate
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_superuser("chief", password="x"))
        structure = {"barcode_type": "ean13", "fields": [{"field_type": "constanta", "value": "21"}, {"field_type": "article", "length": "5"}, {"field_type": "weight_netto_pack", "length": "5"}]}
        self.code = BarcodeTemplate.objects.create(name="Weighed", structure=structure)
        self.other_code = BarcodeTemplate.objects.create(name="Box no.", structure={"barcode_type": "code128", "fields": [{"field_type": "box_number", "length": "12"}]})
        by_id = LabelTemplates.objects.create(name="Pack", scheme={"elements": [{"type": "barcode", "templateId": self.code.pk, "barcodeType": "Weighed"}]})
        by_name = LabelTemplates.objects.create(name="Old pack", scheme={"elements": [{"type": "barcode", "barcodeType": "Weighed"}]})
        unrelated = LabelTemplates.objects.create(name="Box", scheme={"elements": [{"type": "barcode", "templateId": self.other_code.pk}]})
        make = lambda article, **fields: Nomenclature.objects.create(name=article, article=article, exp_date=10, close_box_counter=10, **fields)
        self.a = make("1", templates_pack_label=by_id)
        self.b = make("2", templates_pack_label=by_name)
        self.c = make("3", templates_box_label=unrelated)
        self.before = self.a.edited - datetime.timedelta(hours=1)
        Nomenclature.objects.update(edited=self.before)

    def edited(self, product):
        product.refresh_from_db()
        return product.edited

    def test_saved_barcode_marks_products_of_labels_using_it(self):
        response = self.client.patch(f"/api/v1/barcodes/{self.code.pk}/", {"name": "Weighed 21"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(self.edited(self.a), self.before)
        self.assertGreater(self.edited(self.b), self.before)
        self.assertEqual(self.edited(self.c), self.before)

    def test_deleted_barcode_marks_its_products(self):
        self.assertEqual(self.client.delete(f"/api/v1/barcodes/{self.code.pk}/").status_code, 204)
        self.assertGreater(self.edited(self.a), self.before)
        self.assertEqual(self.edited(self.c), self.before)

