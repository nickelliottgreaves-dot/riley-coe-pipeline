"""Regression checks for the committed seed pool and venue coverage contract."""
import csv
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


class RepositoryDataContractTests(unittest.TestCase):
    def test_artist_pool_has_expected_size_and_unique_normalized_names(self):
        rows = read_csv(ROOT / "data/artist_pool.csv")
        names = [row["artist"].strip().casefold() for row in rows]
        self.assertEqual(len(rows), 747, "Seed pool size changed; review and document before updating the contract")
        self.assertEqual(len(names), len(set(names)), "Artist pool contains duplicate normalized names")
        self.assertTrue(all(row["artist"].strip() and row["status"].strip() for row in rows))

    def test_required_venues_and_safety_net_sources_are_registered(self):
        required = read_csv(ROOT / "config/required_venues.csv")
        mandatory = {row["venue"].strip() for row in required if row["mandatory"].strip().casefold() == "true"}
        self.assertEqual(len(mandatory), 16, "Mandatory venue sweep changed; review coverage requirements")

        sources = read_csv(ROOT / "config/venue_sources.csv")
        configured = {row["venue"].strip() for row in sources}
        self.assertTrue(mandatory.issubset(configured), f"Required venues missing from source registry: {sorted(mandatory - configured)}")
        self.assertTrue(
            {"The Globe", "Little Buildings", "Utilita Arena Newcastle", "ZEROX Newcastle"}.issubset(configured),
            "One or more safety-net venues have been removed from the source registry",
        )


if __name__ == "__main__":
    unittest.main()
