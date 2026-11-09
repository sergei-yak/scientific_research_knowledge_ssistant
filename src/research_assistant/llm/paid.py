"""Explicit Responses adapter with persistent, conservative spending reservations."""

import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

from openai import OpenAI, pydantic_function_tool
from pydantic import BaseModel

from research_assistant.contracts import LLMResult, fingerprint
from research_assistant.retrieval.evidence import estimate_tokens
from research_assistant.settings import Settings

BUDGET_DIRECTORY = Path(__file__).resolve().parents[3] / 'data/accounting'
RATE_REVIEW_DATE = '2026-11-08'
RATE_SOURCE = 'https://developers.openai.com/api/docs/models/gpt-6.1-terra'
# Standard text prices are $1/$5 per million input/output tokens. The larger
# input ceiling also covers documented cache-write premiums; tools/fast/regional are disabled.
TOKEN_RATE_CEILING = Decimal('0.000005')


def read_ledger(directory: Path) -> list[dict]:
    """Fail closed on a modified/truncated journal; never reset consumed reservations."""
    events, previous = [], '0' * 64
    path = directory / 'openai.jsonl'
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            event = json.loads(line)
            digest = event.pop('sha256')
            if event['previous_sha256'] != previous or fingerprint(event) != digest:
                raise ValueError('OpenAI budget journal integrity failure')
            previous = digest
            events.append({**event, 'sha256': digest})
    return events


def append_ledger(directory: Path, event: dict) -> None:
    """Durably append under the caller's exclusive lock before any billable request."""
    events = read_ledger(directory)
    record = {**event, 'previous_sha256': events[-1]['sha256'] if events else '0' * 64}
    record['sha256'] = fingerprint(record)
    with (directory / 'openai.jsonl').open('a', encoding='utf-8', newline='\n') as handle:
        handle.write(json.dumps(record, sort_keys=True) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def reserve(settings: Settings, amount: Decimal, request_id: str, identity: dict):
    """Serialize paid calls; all successful/failed/unknown attempts retain the full bound."""
    directory = BUDGET_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / '.openai.lock'
    with lock.open('x', encoding='utf-8') as handle:
        handle.write(request_id)
    try:
        attempts = [event for event in read_ledger(directory) if event['kind'] == 'reserve']
        used = sum((Decimal(event['reserved_usd']) for event in attempts), Decimal('0'))
        if len(attempts) >= settings.api_max_requests:
            raise ValueError('Approved OpenAI request count exhausted')
        if amount > Decimal(str(settings.api_max_request_usd)) or used + amount > Decimal(str(settings.api_budget_usd)):
            raise ValueError('OpenAI reservation exceeds per-request ceiling or remaining approved budget')
        append_ledger(directory, {'kind': 'reserve', 'request_id': request_id,
                                  'reserved_usd': str(amount), **identity})
        yield directory
    finally:
        lock.unlink()


def open_mapping(schema) -> bool:
    """Identify free-form maps unsupported by the strict JSON Schema subset."""
    if isinstance(schema, list):
        return any(open_mapping(value) for value in schema)
    if not isinstance(schema, dict):
        return False
    extra = schema.get('additionalProperties', False)
    return extra is True or isinstance(extra, dict) or any(open_mapping(value) for value in schema.values())


class OpenAIClient:
    """One explicit text-only model/tier; zero SDK retries or provider fallback."""

    def __init__(self, settings: Settings, context_tokens: int = 4096, output_tokens: int = 512,
                 purpose: str = 'generation', operation: str | None = None) -> None:
        if purpose not in {'generation', 'extraction'} or getattr(settings, purpose + '_provider') != 'openai':
            raise ValueError('OpenAI must be explicitly selected; no provider fallback')
        blockers = settings.paid_probe_blockers()
        if blockers:
            raise ValueError('; '.join(blockers))
        if operation not in {None, 'm3_3_readiness'} or settings.api_budget_scope != (operation or purpose):
            raise ValueError('Paid operation is outside the explicitly approved budget scope')
        self.model = getattr(settings, purpose + '_model')
        if self.model != 'gpt-6.1-terra':
            raise ValueError('No reviewed price/adapter contract for the selected OpenAI model')
        if (date.today() - date.fromisoformat(RATE_REVIEW_DATE)).days > 14:
            raise ValueError('OpenAI price review expired; reverify official rates before paid calls')
        if settings.max_retries != 0 or settings.max_concurrency != 1:
            raise ValueError('Paid adapter requires retries=0 and concurrency=1')
        if not 64 <= output_tokens <= min(1024, settings.max_output_tokens) or not 2048 <= context_tokens <= 8192:
            raise ValueError('OpenAI context/output request exceeds configured limits')
        self.settings, self.context_tokens, self.output_tokens = settings, context_tokens, output_tokens
        self.purpose = purpose
        self.operation = operation or purpose
        self.prompt_version = 'bounded-claims-v1' if purpose == 'extraction' else 'grounded-evidence-v2'
        self.last_result = None
        self.client = OpenAI(api_key=settings.openai_api_key.get_secret_value(),
            base_url='https://api.openai.com/v1', max_retries=0, timeout=settings.request_timeout_seconds)

    def _generate(self, messages: list[dict[str, str]], schema: dict | None, json_object: bool = False) -> LLMResult:
        self.last_result = None
        if not messages or len(messages) > 32 or any(set(m) != {'role', 'content'} or
                m['role'] not in {'system', 'user', 'assistant'} or not isinstance(m['content'], str) for m in messages):
            raise ValueError('Paid adapter accepts bounded text messages only')
        serialized = json.dumps({'messages': messages, 'schema': schema}, ensure_ascii=False)
        estimate = estimate_tokens(serialized)
        if int(estimate * 1.25) + self.output_tokens + 256 > self.context_tokens:
            raise ValueError('Prompt/context safety margin exceeded')
        byte_count = len(serialized.encode('utf-8'))
        if byte_count > 65536:
            raise ValueError('Paid input byte limit exceeded')
        # UTF-8 bytes bound byte-BPE text tokens; reserve extra protocol overhead.
        bound = byte_count + 4096 + len(messages) * 256
        amount = Decimal(bound + self.output_tokens) * TOKEN_RATE_CEILING
        request_id = uuid.uuid4().hex
        params = dict(model=self.model, input=messages, max_output_tokens=self.output_tokens,
                      reasoning={'effort': 'none'}, service_tier='default', store=False,
                      truncation='disabled', tools=[])
        if schema:
            params['text'] = {'format': {'type': 'json_schema', 'name': 'result', 'strict': True, 'schema': schema}}
        elif json_object:
            params['text'] = {'format': {'type': 'json_object'}}
        identity = {'model': self.model, 'request_sha256': fingerprint(params), 'input_token_upper_bound': bound,
                    'operation': self.operation,
                    'max_output_tokens': self.output_tokens, 'rate_review_date': RATE_REVIEW_DATE,
                    'rate_source': RATE_SOURCE, 'usd_per_token_ceiling': str(TOKEN_RATE_CEILING)}
        with reserve(self.settings, amount, request_id, identity) as directory:
            start = time.perf_counter()
            try:
                response = self.client.responses.create(**params)
            except Exception as exc:
                append_ledger(directory, {'kind': 'unknown', 'request_id': request_id, 'error_type': type(exc).__name__})
                raise
            usage = response.usage
            self.last_result = LLMResult(text=response.output_text or '', provider='openai', model=response.model,
                digest='provider-model:' + response.model, elapsed_ms=(time.perf_counter()-start)*1000,
                usage={'prompt_tokens': usage.input_tokens if usage else None, 'output_tokens': usage.output_tokens if usage else None},
                messages=messages, settings={**identity, 'budget_request_id': request_id, 'reserved_usd': str(amount),
                    'retries': 0, 'concurrency': 1, 'purpose': self.purpose, 'prompt_version': self.prompt_version,
                    'request': params, 'provider_response': response.model_dump(mode='json'),
                    'identity_kind': 'provider model identifier; no weights digest exposed'})
            append_ledger(directory, {'kind': 'response', 'request_id': request_id,
                'response_id': response.id, 'status': response.status, 'usage': self.last_result.usage})
            if (response.status != 'completed' or not usage or not 0 <= usage.input_tokens <= bound
                    or not 0 <= usage.output_tokens <= self.output_tokens
                    or usage.input_tokens + self.output_tokens > self.context_tokens
                    or not response.output_text
                    or any(part.type == 'refusal' for item in response.output if item.type == 'message' for part in item.content)):
                raise ValueError('OpenAI refusal, incomplete output, missing usage or token-bound violation; reservation retained')
            if response.model != self.model and not response.model.startswith(self.model + '-'):
                raise ValueError('Unexpected provider model identity; no substitution accepted')
            return self.last_result

    def generate_text(self, messages: list[dict[str, str]]) -> LLMResult:
        """Generate one budget-reserved text response."""
        return self._generate(messages, None)

    def generate_structured(self, schema: type[BaseModel], messages: list[dict[str, str]]):
        """Strict schemas for fixed fields; explicit JSON mode plus validation for open maps."""
        definition = schema.model_json_schema()
        if open_mapping(definition):
            actual = [{'role': 'system', 'content': 'Return only a JSON object satisfying this schema: ' + json.dumps(definition)}, *messages]
            result = self._generate(actual, None, json_object=True)
        else:
            definition = pydantic_function_tool(schema)['function']['parameters']
            result = self._generate(messages, definition)
        return schema.model_validate_json(result.text), result
