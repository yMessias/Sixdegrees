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


class SearchActorTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    @patch('api.views.tmdb.search_actor')
    def test_search_actor_ignores_short_queries(self, search_actor):
        request = self.factory.get('/api/search/', {'q': 'a'})

        response = views.search_actor(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])
        search_actor.assert_not_called()

    @patch('api.views.tmdb.search_actor')
    def test_search_actor_returns_only_acting_results(self, search_actor):
        search_actor.return_value = [
            {
                'id': 1,
                'name': 'Ator A',
                'profile_path': '/ator-a.jpg',
                'known_for_department': 'Acting',
                'known_for': [{'title': 'Filme A'}, {'name': 'Serie A'}],
            },
            {
                'id': 2,
                'name': 'Diretor B',
                'profile_path': '/diretor-b.jpg',
                'known_for_department': 'Directing',
                'known_for': [{'title': 'Filme B'}],
            },
            {
                'id': 3,
                'name': 'Atriz C',
                'profile_path': None,
                'known_for_department': 'Acting',
                'known_for': [],
            },
        ]
        request = self.factory.get('/api/search/', {'q': 'ator'})

        response = views.search_actor(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            [
                {
                    'id': 1,
                    'name': 'Ator A',
                    'photo': 'https://image.tmdb.org/t/p/w300/ator-a.jpg',
                    'known_for': 'Filme A, Serie A',
                },
                {
                    'id': 3,
                    'name': 'Atriz C',
                    'photo': None,
                    'known_for': '',
                },
            ],
        )
        search_actor.assert_called_once_with('ator')
