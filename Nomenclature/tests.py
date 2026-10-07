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
