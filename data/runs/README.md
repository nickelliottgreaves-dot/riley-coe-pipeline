# Weekly run evidence package

A run directory must contain `run_manifest.json` and all five CSV files named
in `config/schemas.json`. The validator fails closed when evidence is absent,
a required venue was not checked, or the episode coverage and source-verification
flags are not explicitly true.

Do not set completion flags merely because a search was attempted. Record
inaccessible sources and incomplete tracklists honestly. This repository currently
contains the validator and seed artist pool; it does not yet include an automated
live web/episode collector, so a weekly scheduled validation will correctly fail
until a genuine evidence package is produced.
