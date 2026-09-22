import json

from django.test import SimpleTestCase
from django.urls import reverse


class ApiNavigationTests(SimpleTestCase):
    def test_home_redirects_to_api_docs(self):
        response = self.client.get('/')

        self.assertRedirects(
            response,
            reverse('swagger-ui'),
            fetch_redirect_response=False,
        )

    def test_api_docs_load(self):
        response = self.client.get(reverse('swagger-ui'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'LabelPilot API')

    def test_schema_documents_core_read_endpoints(self):
        response = self.client.get(reverse('schema'), HTTP_ACCEPT='application/json')

        self.assertEqual(response.status_code, 200)
        schema = json.loads(response.content)
        version_operation = schema['paths']['/api/v1/version/']['get']
        sync_operation = schema['paths']['/api/v1/full_sync/']['get']

        self.assertEqual(
            version_operation['summary'],
            'Get server and supported client versions',
        )
        self.assertIn(
            'VersionInfo',
            version_operation['responses']['200']['content']['application/json']['schema']['$ref'],
        )
        self.assertIn(
            'FullSyncResponse',
            sync_operation['responses']['200']['content']['application/json']['schema']['$ref'],
        )
