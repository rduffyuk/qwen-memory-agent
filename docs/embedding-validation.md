# Embedding Threshold Validation

Model: `text-embedding-v3` via DashScope live embeddings.
Supersession threshold under review: `0.90`.

This is a one-shot live validation of semantic supersession pairs against unrelated same-person distractors. It is separate from the offline benchmark, which uses a deterministic keyword embedder to test ranking and budget-packing logic without model or network variance.

| Case | Supersession pair | Pair cosine | Distractor | Distractor cosine |
|---|---|---:|---|---:|
| Ryan morning drink | Ryan prefers coffee in the morning. -> Ryan now prefers tea in the morning. | 0.908 | Ryan uses Python for prototypes. | 0.689 |
| Priya commute | Priya usually commutes by bus. -> Priya now commutes by train. | 0.900 | Priya uses Postgres for local databases. | 0.683 |
| Alex cloud provider | Alex deploys prototypes on AWS. -> Alex now deploys prototypes on Alibaba Cloud. | 0.893 | Alex writes tests with pytest. | 0.743 |
| Jordan breakfast | Jordan eats oatmeal for breakfast. -> Jordan now eats yogurt for breakfast. | 0.879 | Jordan keeps notes in UTC. | 0.685 |

Mean supersession cosine: `0.895`.
Mean distractor cosine: `0.700`.
Max distractor cosine: `0.743`.

The lowest supersession-pair cosine is 0.879, below the 0.90 default. This contradicts the threshold on this live sample; the default is left unchanged and should be revisited with a larger validation set.
