# M5.3 model decision — recorded before adapter implementation

Selected model: `cross-encoder/ms-marco-MiniLM-L6-v2`, exact Hugging Face revision
`233902d25c440f23af6f7d6e94d2946bac0bee0a` (verified repository metadata, 2026-11-15).
Use only its `model.safetensors`, JSON/tokenizer/vocabulary assets, with local-only loading,
`trust_remote_code=False`, no pickle fallback, and recorded file SHA-256 values before use.
Public model metadata declares Apache-2.0; retain the revision-bound model card.

Reason: an English passage-ranking cross-encoder trained on MS MARCO, six BERT layers/384 hidden
dimensions, one relevance logit, compatible with the installed PyTorch/Transformers stack.
The config's historical `_name_or_path` mentions L12, but its actual architecture has six layers;
repository ID, revision and asset hashes govern identity. A larger L12 model is not needed for the
bounded first trial. No development/held-out scores were used to choose this model.
Published benchmark scores are not evidence of quality on this scientific-paper corpus.

Preflight uses the unchanged lockfile: torch 2.6.0+cu124, transformers 4.57.6,
sentence-transformers 4.1.0, safetensors 0.8.0 and huggingface-hub 0.36.2.
Model config declares `max_position_embeddings=512`; verify tokenizer's native limit also.
Complete query/passage pairs include native special tokens and must fit **512** positions.
Overlength/model/asset/score failures stop the arm; no truncation, substitution or graph fallback.

Score policy `raw-logit-fp32-v1`: CPU float32, evaluation/inference mode, identity activation,
no sigmoid/softmax/calibration/rounding, one finite scalar per pair. Single-pair inference
(batch size one), CPU threads/inter-op 12/12 as observed, concurrency one, zero automatic retries.
Require that runtime identity rather than changing global thread settings. Single-pair scoring
keeps identical features independent of pool membership and padding/batch composition.

Feature policy `canonical-evidence-v1`: exact question + exact normalized full source chunk,
or exact approved fact `embedding_text`; no graph path, ID, gold, answer, origin bonus or source
clipping enters the model. Tie policy: descending raw score, ascending original fused/cosine
rank (new graph-only items have no baseline rank), stable ID. Keep existing raw channel pools,
vector eligibility threshold, graph pre-pruning policy and common atomic packer/budgets.

At most **88 unique candidate identities per question**, including seed/ablation scoring.
A per-request feature cache reuses already scored baseline pairs before scoring graph additions;
do not score 48 seed candidates and then all 88 again. The same selector applies to all four V2
modes. Same-profile no-novel-selected Graph fallback must exactly preserve reranked fact-ablation
evidence/context. Reference mode remains available and does not load a reranker.

Preflight before adapter code: public synthetic relevance pairs and 88-pair resource probe, CPU
MiniLM resident, development Neo4j already running. Save exact native lengths/logits/runtime,
assets, elapsed time and RAM metadata; no generation, private questions or development tuning.
Bound new model downloads to this one model and 150 MiB total retained inference/card assets.
Missing assets/resources block this selector only. Model manifest is executable-ready only after
all pinned files and native/runtime checks pass.

Primary sources: [revision-bound model card](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2/tree/233902d25c440f23af6f7d6e94d2946bac0bee0a),
[publisher documentation](https://sbert.net/docs/cross_encoder/pretrained_models.html).
