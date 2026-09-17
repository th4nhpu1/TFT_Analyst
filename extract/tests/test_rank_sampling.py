import random
import unittest
from rankSampling import sample_players, TIERS


class FakeRiot:
    def __init__(self):
        self.pages = []

    def get(self, url):
        if '/entries/' not in url:
            return {'entries': [{'puuid': f'elite-{n}', 'rank': 'I'} for n in range(100)]}
        division, page = url.rsplit('/', 1)[1].split('?page=')
        page = int(page)
        self.pages.append((division, page))
        if page > 4:
            return []
        return [{'puuid': f'{division}-{page}-{n}', 'rank': division} for n in range(25)]


class SamplingTests(unittest.TestCase):
    def test_lower_rank_random_pool_spans_pages_and_divisions(self):
        client = FakeRiot()
        players = sample_players(client, 'GOLD', 50, random.Random(123))
        self.assertEqual(len(players), 50)
        self.assertEqual(len({p['puuid'] for p in players}), 50)
        self.assertGreater(len({p['division'] for p in players}), 1)
        self.assertTrue(any(p['puuid'].split('-')[1] != '1' for p in players))
        self.assertTrue(all(p['tier'] == 'GOLD' and p['match_ids'] is None for p in players))

    def test_all_elite_ranks_sample_randomly(self):
        for tier in TIERS[-3:]:
            players = sample_players(FakeRiot(), tier, 50, random.Random(123))
            self.assertEqual(len(players), 50)
            self.assertNotEqual([p['puuid'] for p in players], [f'elite-{n}' for n in range(50)])

    def test_shortfall_fails_instead_of_silently_undersampling(self):
        with self.assertRaisesRegex(RuntimeError, 'requested 101'):
            sample_players(FakeRiot(), 'MASTER', 101, random.Random(1))


if __name__ == '__main__':
    unittest.main()
