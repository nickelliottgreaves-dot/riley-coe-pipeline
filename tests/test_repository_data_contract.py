"""Regression checks for the committed seed pool and venue coverage contract."""
import csv
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def normalize_venue(name):
    return " ".join(name.strip().replace(" / ", "/").split()).casefold()


class RepositoryDataContractTests(unittest.TestCase):
    def test_artist_pool_has_expected_size_and_unique_normalized_names(self):
        rows = read_csv(ROOT / "data/artist_pool.csv")
        names = [row["artist"].strip().casefold() for row in rows]
        self.assertGreaterEqual(len(rows), 747, "Artist pool unexpectedly shrank below the preserved baseline")
        self.assertEqual(len(names), len(set(names)), "Artist pool contains duplicate normalized names")
        self.assertTrue(all(row["artist"].strip() and row["status"].strip() for row in rows))
        backup_path = ROOT / "data/artist_pool_backup_20261015.csv"
        if backup_path.exists():
            backup = read_csv(backup_path)
            backup_names = {row["artist"].strip().casefold() for row in backup}
            self.assertTrue(backup_names.issubset(set(names)), "Updated pool dropped names from the preserved 747-row baseline")

    def test_required_venues_and_safety_net_sources_are_registered(self):
        required = read_csv(ROOT / "config/required_venues.csv")
        mandatory = {
            normalize_venue(row["venue"])
            for row in required
            if row["mandatory"].strip().casefold() == "true"
        }
        self.assertEqual(len(mandatory), 20, "Mandatory venue sweep changed; review coverage requirements")

        sources = read_csv(ROOT / "config/venue_sources.csv")
        configured = {normalize_venue(row["venue"]) for row in sources}
        self.assertTrue(
            mandatory.issubset(configured),
            f"Required venues missing from source registry: {sorted(mandatory - configured)}",
        )
        safety_net = {"The Globe", "Little Buildings", "Utilita Arena Newcastle", "ZEROX Newcastle"}
        self.assertTrue(
            {normalize_venue(name) for name in safety_net}.issubset(configured),
            "One or more safety-net venues have been removed from the source registry",
        )


if __name__ == "__main__":
    unittest.main()
