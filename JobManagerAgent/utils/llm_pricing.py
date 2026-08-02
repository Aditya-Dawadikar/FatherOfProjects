from __future__ import annotations

from .env_utils import load_env_value


# USD per 1M tokens, standard/paid tier, text-only (ai.google.dev/gemini-api/docs/pricing as of
# writing). These are defaults only -- override per-model via
# LLM_INPUT_PRICE_PER_MILLION__<MODEL>/LLM_OUTPUT_PRICE_PER_MILLION__<MODEL> (same <MODEL> key
# format as LLM_RPM_CAP__<MODEL> in rate_limiter.py) if pricing has moved or a non-global region
# applies -- checked against the provider's own console/billing, not left on guesswork, same
# policy as the RPM cap.
_DEFAULT_PRICE_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
	"gemini-3.5-flash": (1.50, 9.00),
	"gemini-3.6-flash": (1.50, 7.50),
}
_FALLBACK_PRICE_PER_MILLION_TOKENS = (1.50, 9.00)


def _price_env_key(model: str, direction: str) -> str:
	normalized = model.upper().replace("-", "_").replace(".", "_")
	return f"LLM_{direction}_PRICE_PER_MILLION__{normalized}"


def load_price_per_million_tokens(model: str) -> tuple[float, float]:
	"""(input_price, output_price) in USD per 1M tokens for `model`. Falls back to a generic
	flash-tier default if `model` isn't in the table (e.g. a newly released or renamed model)
	rather than raising -- cost estimates degrade to "approximate" instead of breaking the eval
	run they're only a side metric of."""
	default_input, default_output = _DEFAULT_PRICE_PER_MILLION_TOKENS.get(model, _FALLBACK_PRICE_PER_MILLION_TOKENS)
	input_price = float(load_env_value(_price_env_key(model, "INPUT"), str(default_input)))
	output_price = float(load_env_value(_price_env_key(model, "OUTPUT"), str(default_output)))
	return input_price, output_price


def estimate_cost_usd(model: str, *, input_tokens: int, output_tokens: int) -> float:
	input_price, output_price = load_price_per_million_tokens(model)
	return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
