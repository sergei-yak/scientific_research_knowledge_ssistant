# Presentation references

These are selected foundations and resources, not a claim to have reimplemented every cited paper. Indexed paper versions and complete research-corpus records remain in the source catalog and final report.

## Literature

1. Lewis, P., et al. (2020). *Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks*. NeurIPS. https://arxiv.org/abs/2005.11401
2. Edge, D., et al. (2024). *From Local to Global: A Graph RAG Approach to Query-Focused Summarization*. Indexed v1. https://arxiv.org/abs/2404.16130v1
3. Guo, Z., et al. (2024). *LightRAG: Simple and Fast Retrieval-Augmented Generation*. Indexed v1. https://arxiv.org/abs/2410.05779v1
4. Jimenez Gutierrez, B., et al. (2024). *HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models*. Indexed v1. https://arxiv.org/abs/2405.14831v1
5. Jimenez Gutierrez, B., et al. (2025). *From RAG to Memory: Non-Parametric Continual Learning for Large Language Models* (HippoRAG 2). Indexed v1. https://arxiv.org/abs/2502.14802v1
6. Han, H., et al. (2025). *Retrieval-Augmented Generation with Graphs (GraphRAG)*. Indexed v2. https://arxiv.org/abs/2501.00309v2
7. Reimers, N., & Gurevych, I. (2019). *Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks*. EMNLP. https://arxiv.org/abs/1908.10084
8. LIGO Scientific Collaboration and Virgo Collaboration (2016). *Observation of Gravitational Waves from a Binary Black Hole Merger*. Product demonstration source, v1. https://arxiv.org/abs/1602.03837v1

## Models and tools

- MiniLM encoder: https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2
- Separate MPNet encoder experiment: https://huggingface.co/sentence-transformers/all-mpnet-base-v2
- Experimental cross-encoder: https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2
- Local Qwen generation through Ollama: https://docs.ollama.com/ . Exact local model identity is the recorded digest in the source manifests. The installed alias is not evidence of an official Qwen release name. No training/fine-tuning was performed.
- Python: https://www.python.org/
- PyTorch: https://pytorch.org/
- Sentence Transformers: https://sbert.net/
- Neo4j: https://neo4j.com/docs/
- Streamlit: https://docs.streamlit.io/
- PyMuPDF: https://pymupdf.readthedocs.io/
- arXiv source papers: https://arxiv.org/
- OpenAlex publication/citation metadata: https://docs.openalex.org/
- OpenAI API: https://platform.openai.com/docs/ . Historical bounded readiness probes only, not the local product answer-generation provider or research generator.
- Codex supported AI-assisted development. The human supplied requirements, source approvals and answer scores.

## Project and public evidence

- Repository: https://github.com/sergei-yak/scientific_research_knowledge_ssistant
- Original study: evidence/FINAL_EVALUATION_REPORT.md and evidence/baseline-aggregates.json.
- Exploratory follow-up: evidence/M5_6_EVALUATION_REPORT.md, evidence/followup-aggregates.json and evidence/M5_5_STUDY_AMENDMENT.md.
- Product: evidence/M8_5_REPORT.md and evidence/M8_USER_GUIDE.md.
- Reproducibility: Source_M8_6659565.zip contains the tested source, uv.lock and model manifests. Local model weights, PDFs, databases, credentials and private evaluation contents are excluded.

The normal M8 product uses its reference profile. Experimental reranking was evaluated separately. Citations verify attribution, not independent scientific truth or universal performance.
