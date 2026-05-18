from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from . import views


class ConnectionValidationTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_find_connection_requires_both_actor_ids(self):
        request = self.factory.get('/api/connect/', {'actor_a': '', 'actor_b': '2'})

        response = views.find_connection(request)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], views.MISSING_ACTOR_IDS_ERROR)

    def test_find_connection_rejects_non_positive_actor_ids(self):
        invalid_values = ['abc', '0', '-1']

        for invalid_value in invalid_values:
            with self.subTest(actor_a=invalid_value):
                request = self.factory.get(
                    '/api/connect/',
                    {'actor_a': invalid_value, 'actor_b': '2'},
                )

                response = views.find_connection(request)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data['error'], views.INVALID_ACTOR_IDS_ERROR)

    @patch('api.views.find_path')
    def test_find_connection_passes_valid_actor_ids_as_integers(self, find_path):
        find_path.return_value = [
            {'actor': {'id': 1, 'name': 'Ator A'}, 'movie': {'id': 10}},
            {'actor': {'id': 2, 'name': 'Ator B'}, 'movie': None},
        ]
        request = self.factory.get('/api/connect/', {'actor_a': '1', 'actor_b': '2'})

        response = views.find_connection(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['degrees'], 1)
        find_path.assert_called_once_with(1, 2)

    @patch('api.views.start_connection_job')
    def test_start_connection_search_queues_job_with_valid_actor_ids(self, start_job):
        start_job.return_value = {
            'id': 'job-1',
            'status': 'pending',
            'actor_a_id': 1,
            'actor_b_id': 2,
        }
        request = self.factory.post(
            '/api/connect/start/',
            {'actor_a': '1', 'actor_b': '2'},
            format='json',
        )

        response = views.start_connection_search(request)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['id'], 'job-1')
        start_job.assert_called_once_with(1, 2)
