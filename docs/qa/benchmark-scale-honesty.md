# Benchmark Scale Honesty Note

Jira: VW-1090

The benchmark fixture was scaled from one persona and two scored queries to six personas and
twenty-four scored queries.

The core finding held: B3 kept context recall at 1.000 and staleness at 0.000 for every tested
budget.

The B2 staleness finding weakened in magnitude but did not disappear. In the old toy fixture,
B2 staleness rose from 0.00 to 0.50. In the scaled fixture, B2 staleness rises from 0.125 to
0.250 and then plateaus. This is the honest scaled result and is the value used in README,
`docs/SUBMISSION.md`, and `benchmark/results/context_efficiency.png`.

The live `text-embedding-v3` threshold validation also produced a caveat: supersession-pair
cosines ranged from 0.879 to 0.908, while unrelated distractors ranged from 0.683 to 0.743.
Because one supersession pair fell below `SUPERSEDE_THRESHOLD=0.9`, the default is documented as
conservative and in need of broader validation, not as a universal constant.
