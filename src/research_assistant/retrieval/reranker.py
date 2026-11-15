"""Pinned local cross-encoder inference; no source retrieval, gold, downloads or generation."""
from __future__ import annotations

import hashlib
import importlib.metadata
import math
import time
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Literal, Protocol

from pydantic import Field

from research_assistant.contracts import Contract, fingerprint

MANIFEST = Path('manifests/reranker-msmarco-minilm-l6-v1.json')
FEATURE_POLICY = {'version':'canonical-evidence-v1','question':'exact',
                  'chunk':'exact normalized full source text','fact':'exact approved embedding_text',
                  'excluded':['paths','candidate_id','origin','gold','answer','clipping']}
FEATURE_SHA256 = fingerprint(FEATURE_POLICY)
ASSETS = {'README.md','config.json','model.safetensors','special_tokens_map.json',
          'tokenizer.json','tokenizer_config.json','vocab.txt'}
_INFERENCE_LOCK=Lock()
_MODEL_LOCK=Lock()


class RerankerManifest(Contract):
    """Only the verified M5.3 model/input/score policy can become an executable selector."""
    format: Literal['reranker-model-v1']
    model_id: Literal['cross-encoder/ms-marco-MiniLM-L6-v2']
    revision: Literal['233902d25c440f23af6f7d6e94d2946bac0bee0a']
    asset_directory: str
    files: dict[str,str]
    asset_bytes: int = Field(gt=0,le=150*1024**2)
    native_pair_limit: Literal[512]
    model_type: Literal['bert']
    num_labels: Literal[1]
    dtype: Literal['float32']
    device: Literal['cpu']
    batch_size: Literal[1]
    torch_num_threads: Literal[12]
    torch_interop_threads: Literal[12]
    runtime_versions: dict[str,str]
    score_policy: Literal['raw-logit-fp32-v1']
    feature_policy: Literal['canonical-evidence-v1']
    tie_policy: Literal['score-desc-baseline-rank-asc-id']
    max_unique_candidates: Literal[88]


class RerankerError(ValueError):
    """An explicit failed selector attempt, never permission to return another arm."""
    def __init__(self,message: str,diagnostics: dict | None=None):
        super().__init__(message)
        self.selection_diagnostics=diagnostics or {'status':'failed','stage':'model_readiness'}


class PairScorer(Protocol):
    """One shared scalar-scoring interface, including explicit native input lengths."""
    def score_pairs(self,pairs: list[tuple[str,str]]) -> tuple[list[float],list[int]]:
        """Validate every new pair before inference and return finite relevance logits."""
        ...


def verified_manifest() -> RerankerManifest:
    """Revalidate pinned files/runtime before each use, including resident-model cache hits."""
    try:
        manifest=RerankerManifest.model_validate_json(MANIFEST.read_bytes())
        directory=Path(manifest.asset_directory).resolve()
        allowed=Path('.cache/rerankers').resolve()
        if directory==allowed or not directory.is_relative_to(allowed) or set(manifest.files)!=ASSETS:
            raise ValueError('Reranker asset directory/file set is invalid')
        total=0
        for name,digest in manifest.files.items():
            path=directory/name
            if path.is_symlink() or not path.resolve().is_relative_to(directory):
                raise ValueError('Reranker asset escapes its declared directory')
            if len(digest)!=64 or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                raise ValueError('Pinned reranker asset changed: '+name)
            total+=path.stat().st_size
        if total!=manifest.asset_bytes:
            raise ValueError('Reranker asset size differs from manifest')
        if set(manifest.runtime_versions)!={'torch','transformers','sentence-transformers','safetensors','huggingface-hub'}:
            raise ValueError('Reranker runtime version set is incomplete')
        if any(importlib.metadata.version(p)!=version for p,version in manifest.runtime_versions.items()):
            raise ValueError('Reranker runtime differs from the verified locked stack')
        return manifest
    except Exception as exc:
        raise RerankerError('Reranker readiness failed: '+str(exc)) from exc


def model_identity(manifest: RerankerManifest) -> dict:
    """Persist full model/feature/score identity, not a mutable remote name alone."""
    return {'model_id':manifest.model_id,'revision':manifest.revision,
            'manifest_sha256':fingerprint(manifest.model_dump()),'asset_sha256':fingerprint(manifest.files),
            'feature_policy_sha256':FEATURE_SHA256,'score_policy':manifest.score_policy,
            'native_pair_limit':manifest.native_pair_limit,'device':manifest.device,'dtype':manifest.dtype,
            'runtime_versions':manifest.runtime_versions,'batch_size':1,
            'torch_num_threads':12,'torch_interop_threads':12}


class LocalCrossEncoder:
    """Single-pair BERT scalar logits, CPU/eval/inference mode with no truncation."""
    def __init__(self,manifest: RerankerManifest):
        import torch
        from transformers import AutoTokenizer,AutoModelForSequenceClassification
        self.manifest=manifest
        self.tokenizer=AutoTokenizer.from_pretrained(manifest.asset_directory,local_files_only=True,trust_remote_code=False)
        self.model=AutoModelForSequenceClassification.from_pretrained(manifest.asset_directory,local_files_only=True,
            trust_remote_code=False,use_safetensors=True).to('cpu').float().eval()
        if (self.tokenizer.model_max_length!=512 or self.model.config.max_position_embeddings!=512
                or self.model.config.num_labels!=1 or self.model.config.num_hidden_layers!=6):
            raise RerankerError('Reranker native architecture/input contract changed')
        self._runtime(torch)

    @staticmethod
    def _runtime(torch) -> None:
        if torch.get_num_threads()!=12 or torch.get_num_interop_threads()!=12:
            raise RerankerError('Reranker CPU thread runtime differs from its verified manifest')

    def score_pairs(self,pairs: list[tuple[str,str]]) -> tuple[list[float],list[int]]:
        """Preflight the whole stage, then infer each exact pair with the pinned scalar policy."""
        if not _INFERENCE_LOCK.acquire(blocking=False):
            raise RerankerError('Reranker is busy; concurrent inference is not permitted',
                {'status':'failed','stage':'concurrency','new_pairs_inferred':0})
        try:
            return self._score_pairs(pairs)
        finally:
            _INFERENCE_LOCK.release()

    def _score_pairs(self,pairs: list[tuple[str,str]]) -> tuple[list[float],list[int]]:
        """Execute a single owned inference stage and preserve all failure accounting."""
        import torch
        self._runtime(torch)
        if len(pairs)>88:raise RerankerError('Reranker pair bound exceeded')
        prepared=[];lengths=[]
        try:
            for question,text in pairs:
                tokens=self.tokenizer(question,text,truncation=False,return_tensors='pt')
                size=int(tokens['input_ids'].shape[1])
                if size>512:
                    raise RerankerError('Reranker pair exceeds native 512-token limit',
                        {'status':'failed','stage':'native_length','native_pair_tokens':size,'limit':512,'new_pairs_inferred':0})
                prepared.append(tokens);lengths.append(size)
            values=[]
            with torch.inference_mode():
                for tokens in prepared:
                    result=self.model(**tokens).logits
                    if result.shape!=(1,1):raise ValueError('Reranker did not return one scalar per pair')
                    value=float(result[0,0])
                    if not math.isfinite(value):raise ValueError('Reranker returned a nonfinite score')
                    values.append(value)
            return values,lengths
        except RerankerError:
            raise
        except Exception as exc:
            raise RerankerError('Reranker inference failed: '+str(exc),
                {'status':'failed','stage':'inference','requested_pairs':len(pairs),
                 'completed_pairs':len(locals().get('values',[]))}) from exc


@lru_cache(maxsize=1)
def _resident(digest: str) -> LocalCrossEncoder:
    """Cache only after full verification; the caller verifies again for every new request."""
    manifest=verified_manifest()
    if fingerprint(manifest.model_dump())!=digest:raise RerankerError('Model manifest changed during load')
    return LocalCrossEncoder(manifest)


def pinned_scorer() -> LocalCrossEncoder:
    """Reuse loaded weights without allowing stale/corrupt local artifacts to pass readiness."""
    return scorer_with_readiness()[0]


def scorer_with_readiness() -> tuple[LocalCrossEncoder,dict]:
    """Record asset verification/load time and resident cache state separately from scoring."""
    start=time.perf_counter()
    manifest=verified_manifest()
    verified_at=time.perf_counter()
    with _MODEL_LOCK:
        before=_resident.cache_info().hits
        scorer=_resident(fingerprint(manifest.model_dump()))
        reused=_resident.cache_info().hits>before
    return scorer,{'resident_reused':reused,'asset_verification_ms':(verified_at-start)*1000,
                   'load_or_cache_ms':(time.perf_counter()-verified_at)*1000,
                   'device':'cpu','batch_size':1,'torch_num_threads':12,'torch_interop_threads':12}
