"""One-shot inspection of every model id in the live registry and how
``parse_ollama_tag`` decomposes it.  Used to verify v2.43.0 coverage
across the full fleet (OpenAI cloud + every Ollama tag the local
inference engine currently advertises).

Run via:
    docker exec auto-ml-backend-1 sh -c 'cd /app/backend && python scripts/inspect_model_tags.py'
"""
import os
import sys

# Make the backend package importable when the script is run with
# CWD=/app inside the container.  model_registry doesn't touch Django
# models so we skip django.setup() entirely.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))  # /app/backend

from ai_assistant.model_registry import (  # noqa: E402
    MODEL_REGISTRY, _refresh_engine_models, parse_ollama_tag,
)


def fmt_row(vendor, model_id, family, tag, psize):
    return f"{vendor:<8} {model_id:<28} {family:<18} {tag:<10} {psize:<10}"


def main():
    engine_entries = _refresh_engine_models(force=True)
    static_entries = MODEL_REGISTRY

    print()
    print('=' * 80)
    print(fmt_row('vendor', 'model_id', 'family', 'tag', 'param_size'))
    print('=' * 80)

    print()
    print('--- OpenAI cloud (static MODEL_REGISTRY) ---')
    for key, cfg in static_entries.items():
        print(fmt_row('openai', cfg['model_id'], '(n/a)', '(n/a)', '(n/a)'))

    print()
    print(f'--- Engine/Ollama (dynamic — {len(engine_entries)} entries from /v1/models) ---')
    if not engine_entries:
        print('(engine returned no models — check inference engine is up)')
    else:
        for key, cfg in engine_entries.items():
            parsed = parse_ollama_tag(cfg['model_id'])
            family = parsed['family'] or '(none)'
            tag = parsed['tag'] or '(none)'
            psize = parsed['parameter_size'] or '(none)'
            print(fmt_row('ollama', cfg['model_id'], family, tag, psize))
    print()


if __name__ == '__main__':
    main()
