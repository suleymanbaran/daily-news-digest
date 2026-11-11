import os
import json
import re
import time
from typing import List, Dict, Any, Tuple, Callable
import requests

SYSTEM_INSTRUCTION = """You are "Personal Journalist", a friendly daily news-digest curator for one specific user:
- A Computer Engineering student based in Italy, finishing bachelor's this academic year.
- Career goals: AI engineer, forward deployed AI engineer, or SDE (preparing for tech interviews).
- Interested in: building AI products and agents, tech/startup jobs in Italy & Europe.
- Follows: Turkey's news & economy (TRY, EUR, USD matter).
- Improving English and learning Italian.

Your task:
1. Score each story cluster 1-5 for relevance to this user (5 = highly relevant, 1 = low relevance).
2. For the top stories (score 4-5, up to 12 items total, balanced across categories tech / europe / turkey / finance / world), produce:
   - "tldr": ONE punchy sentence (max ~20 words) capturing the core of the story, in simple everyday English.
   - "summary": a DETAILED but easy-to-understand summary of 3-4 sentences. Explain the story like you are talking to a smart friend: what happened, the key numbers or facts, who is involved, and what happens next. Use ONLY facts explicitly present in the provided titles/snippets. NEVER hallucinate or invent outside facts. If a snippet is thin, summarize what is there in 2 sentences rather than inventing detail.
   - "why_it_matters": exactly ONE short, personal sentence tailored to the user's profile (career, exams/interviews, AI engineering, Italy/Europe job market, Turkish economy). Vary the wording between items; never repeat the same sentence.
3. Strict content rules:
   - Neutral, friendly tone. No opinions, no predictions, no hype.
   - Simple language: short sentences, avoid jargon; if a technical term is necessary, briefly explain it inline.
   - Turkey: if multiple source types (independent, international, official/government-aligned) covered the same story, set "turkey_comparison" to a short text stating how each source_type frames the story and explicitly note if they differ. Otherwise null.
   - Finance: NEVER give investment advice, buy/sell suggestions, or price predictions. ONLY state what happened, the number, and the source.
4. Vocabulary (extracted from today's digest content where possible):
   - Up to 5 harder English words (B2-C1) with a short Turkish meaning and one natural English example sentence.
   - 5 Italian words (A1-A2) relevant to tech, student life, or daily news, with definite article and gender (e.g. "il lavoro (masculine)"). The user does not speak Italian yet: "english_meaning" is MANDATORY for every entry — a clear, short English translation.

Respond ONLY with valid JSON matching the requested schema.
"""

GEMINI_MODELS = ["gemini-3.8-flash"]
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

def extract_json(text: str) -> Dict[str, Any]:
    """Safely extract JSON from model output."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)

def call_gemini(api_key: str, prompt: str, model: str = None) -> Tuple[str, int, int, str]:
    models_to_try = [model] if model else GEMINI_MODELS
    last_err = None

    for m in models_to_try:
        for attempt in range(3):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
            payload = {
                "contents": [
                    {"role": "user", "parts": [{"text": prompt}]}
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "responseMimeType": "application/json"
                }
            }
            try:
                resp = requests.post(url, json=payload, timeout=90)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text = candidates[0]["content"]["parts"][0]["text"]
                        usage = data.get("usageMetadata", {})
                        prompt_tokens = usage.get("promptTokenCount", len(prompt) // 4)
                        completion_tokens = usage.get("candidatesTokenCount", len(text) // 4)
                        return text, prompt_tokens, completion_tokens, m
                    last_err = f"model '{m}' returned empty candidates"
                else:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    if resp.status_code not in RETRYABLE_STATUS:
                        break
            except requests.exceptions.RequestException as e:
                last_err = str(e)
            if attempt < 2:
                time.sleep(3 * (attempt + 1))

        print(f"[WARN] Gemini model '{m}' failed after retries: {last_err}")

    raise RuntimeError(f"All Gemini models failed. Last error: {last_err}")

def call_openai_compatible(api_key: str, prompt: str, base_url: str, model: str) -> Tuple[str, int, int]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.post(base_url, headers=headers, json=payload, timeout=90)
            if resp.status_code == 200:
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", len(prompt) // 4)
                completion_tokens = usage.get("completion_tokens", len(text) // 4)
                return text, prompt_tokens, completion_tokens
            last_err = f"API error ({model}) {resp.status_code}: {resp.text[:200]}"
            if resp.status_code not in RETRYABLE_STATUS:
                break
        except requests.exceptions.RequestException as e:
            last_err = str(e)
        if attempt < 2:
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(last_err)

def call_openai(api_key: str, prompt: str, model: str = "gpt-4o-mini") -> Tuple[str, int, int, str]:
    text, pt, ct = call_openai_compatible(api_key, prompt, "https://api.openai.com/v1/chat/completions", model)
    return text, pt, ct, model

GROQ_MODEL_PREFERENCE = [
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
    "moonshotai/kimi-k2-instruct",
    "gemma2-9b-it",
    "llama-3.1-8b-instant",
]

def pick_groq_model(api_key: str) -> str:
    """Ask Groq which models this account can actually use, and pick the best one.
    Avoids hardcoding model names that get deprecated over time."""
    resp = requests.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Groq /models returned {resp.status_code}: {resp.text[:200]}")
    ids = [m.get("id") for m in resp.json().get("data", []) if m.get("id")]
    if not ids:
        raise RuntimeError(
            "Groq account reports no available models. Verify the account has "
            "production access (console.groq.com may require account/phone verification)."
        )
    for pref in GROQ_MODEL_PREFERENCE:
        if pref in ids:
            return pref
    print(f"[INFO] No preferred Groq model found; available: {ids}. Using '{ids[0]}'.")
    return ids[0]

def call_groq(api_key: str, prompt: str, model: str = None) -> Tuple[str, int, int, str]:
    if not model:
        model = pick_groq_model(api_key)
    text, pt, ct = call_openai_compatible(api_key, prompt, "https://api.groq.com/openai/v1/chat/completions", model)
    return text, pt, ct, model

def select_balanced_clusters(clusters: List[Dict[str, Any]], total: int = 15) -> List[Dict[str, Any]]:
    """Round-robin across categories so the LLM sees every category, not just the first N clusters."""
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for c in clusters:
        by_cat.setdefault(c.get("category", "other"), []).append(c)

    selected = []
    queues = list(by_cat.values())
    while len(selected) < total and any(queues):
        for q in queues:
            if q and len(selected) < total:
                selected.append(q.pop(0))
    return selected

def heuristic_dry_run_process(clusters: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Deterministic rule-based processor for dry-run mode or when no LLM key is configured.
    Ensures zero hallucination, strict adherence to facts in snippet, and zero API cost.
    """
    scored = []
    for c in clusters:
        items = c["items"]
        primary = items[0]
        cat = primary.get("category", "")
        title = primary.get("title", "")
        snippet = primary.get("snippet", "")
        combined = (title + " " + snippet).lower()

        score = 3
        if cat == "tech":
            if any(k in combined for k in ["agent", "llm", "ai", "deep learning", "model release", "openai", "interview", "engineer"]):
                score = 5
            else:
                score = 4
        elif cat == "europe":
            if any(k in combined for k in ["startup", "job", "hiring", "italy", "milan", "talent", "funding"]):
                score = 5
            else:
                score = 4
        elif cat == "turkey":
            if any(k in combined for k in ["tcmb", "faiz", "enflasyon", "ekonomi", "lira", "try", "dolar"]):
                score = 5
            else:
                score = 4
        elif cat == "finance":
            if any(k in combined for k in ["fed", "ecb", "rates", "interest rate", "inflation", "cpi", "gdp"]):
                score = 5
            else:
                score = 4
        elif cat == "world":
            score = 3

        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", snippet) if s.strip()]
        if sentences:
            summary = " ".join(sentences[:3])
        else:
            summary = title
        tldr = sentences[0][:160] if sentences else title[:160]

        if cat == "tech":
            why = "Directly relevant for your AI/software engineering background and technical interview prep."
        elif cat == "europe":
            why = "Relevant for tracking tech ecosystem developments and career opportunities in Italy and Europe."
        elif cat == "turkey":
            why = "Impacts the Turkish economic outlook and currency exchange dynamics you monitor."
        elif cat == "finance":
            why = "Key macroeconomic indicator influencing global monetary policy, interest rates, and foreign exchange (USD/EUR/TRY)."
        else:
            why = "Provides broader global context affecting markets and technology policy."

        turkey_comparison = None
        if cat == "turkey" and len(items) > 1:
            sources_present = {it.get("source_type"): it for it in items if it.get("source_type")}
            if len(sources_present) > 1:
                parts = []
                for stype, it in sources_present.items():
                    s_first = (it.get("snippet") or it.get("title", ""))[:120].strip()
                    parts.append(f"[{stype}]: {s_first}...")
                turkey_comparison = " | ".join(parts)

        scored.append({
            "cluster_id": c["cluster_id"],
            "relevance_score": score,
            "category": cat,
            "title": primary["title"],
            "tldr": tldr,
            "items": [
                {
                    "source_name": it["source_name"],
                    "source_type": it.get("source_type"),
                    "link": it["link"]
                }
                for it in items
            ],
            "summary": summary,
            "turkey_comparison": turkey_comparison,
            "why_it_matters": why
        })

    # Balanced pick: highest scores first, round-robin across categories
    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    candidates = [it for it in scored if it["relevance_score"] >= 4]
    top_items = select_balanced_clusters(candidates, total=12)

    sample_vocab_en = [
        {
            "word": "ubiquitous",
            "level": "C1",
            "turkish_meaning": "her yerde bulunan, yaygın",
            "example_usage": "Autonomous AI systems are becoming ubiquitous across modern software engineering workflows."
        },
        {
            "word": "discrepancy",
            "level": "B2",
            "turkish_meaning": "farklılık, tutarsızlık, çelişki",
            "example_usage": "There is a notable discrepancy between market expectations and official inflation forecasts."
        },
        {
            "word": "resilience",
            "level": "B2",
            "turkish_meaning": "direnç, dayanıklılık, toparlanma gücü",
            "example_usage": "European tech startups showed surprising resilience amidst tight macroeconomic conditions."
        },
        {
            "word": "stringent",
            "level": "C1",
            "turkish_meaning": "sıkı, titiz, kati",
            "example_usage": "The central bank maintained stringent monetary policy measures to curb inflation."
        },
        {
            "word": "proliferation",
            "level": "C1",
            "turkish_meaning": "hızlı artış, yayılma, üreme",
            "example_usage": "The proliferation of open-source AI models is democratizing machine learning research."
        }
    ]

    sample_vocab_it = [
        {
            "article": "il",
            "word": "lavoro",
            "gender": "masculine",
            "level": "A1",
            "english_meaning": "work / job"
        },
        {
            "article": "lo",
            "word": "sviluppo",
            "gender": "masculine",
            "level": "A2",
            "english_meaning": "development"
        },
        {
            "article": "l'",
            "word": "azienda",
            "gender": "feminine",
            "level": "A2",
            "english_meaning": "company / enterprise"
        },
        {
            "article": "la",
            "word": "laurea",
            "gender": "feminine",
            "level": "A2",
            "english_meaning": "university degree / graduation"
        },
        {
            "article": "la",
            "word": "crescita",
            "gender": "feminine",
            "level": "A2",
            "english_meaning": "growth / increase"
        }
    ]

    return {
        "items": top_items,
        "vocabulary_english": sample_vocab_en,
        "vocabulary_italian": sample_vocab_it,
        "tokens_prompt": 0,
        "tokens_completion": 0,
        "estimated_cost_usd": 0.0,
        "model_used": "dry-run (heuristic)"
    }

def build_prompt(clusters: List[Dict[str, Any]]) -> str:
    cluster_prompts = []
    for c in select_balanced_clusters(clusters, total=15):
        # Cap items per cluster, keeping distinct source_types first (needed for Turkey comparisons)
        items_sorted = sorted(c["items"], key=lambda it: it.get("source_type") or "")
        items_desc = []
        seen_types = set()
        for it in items_sorted:
            stype = it.get("source_type")
            if len(items_desc) >= 4 and stype in seen_types:
                continue
            seen_types.add(stype)
            items_desc.append({
                "source_name": it["source_name"],
                "source_type": stype,
                "title": it["title"],
                "snippet": it["snippet"][:500],
                "link": it["link"]
            })
            if len(items_desc) >= 5:
                break
        cluster_prompts.append({
            "cluster_id": c["cluster_id"],
            "category": c["category"],
            "items": items_desc
        })

    return f"""Here are the candidate story clusters from today's feeds:
```json
{json.dumps(cluster_prompts, indent=2, ensure_ascii=False)}
```

Provide your JSON response matching this schema:
{{
  "items": [
    {{
      "cluster_id": 1,
      "relevance_score": 5,
      "category": "tech",
      "title": "Selected concise title",
      "tldr": "One punchy sentence, max ~20 words, simple English.",
      "items": [
        {{
          "source_name": "Source Name",
          "source_type": "optional source_type",
          "link": "https://..."
        }}
      ],
      "summary": "3-4 sentence detailed but easy-to-understand summary using ONLY facts from the provided text.",
      "turkey_comparison": "Optional comparison of sources if multiple source types covered this Turkey story, otherwise null.",
      "why_it_matters": "One short personal sentence explaining why it matters to the user."
    }}
  ],
  "vocabulary_english": [
    {{
      "word": "word",
      "level": "B2/C1",
      "turkish_meaning": "short Turkish translation",
      "example_usage": "sentence with word"
    }}
  ],
  "vocabulary_italian": [
    {{
      "article": "il / la / lo / l'",
      "word": "parola",
      "gender": "masculine / feminine",
      "level": "A1/A2",
      "english_meaning": "English translation"
    }}
  ]
}}
"""

def process_clusters(
    clusters: List[Dict[str, Any]],
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Score clusters, summarize top ones, and extract vocabulary.
    Tries every configured LLM provider in order before falling back to heuristics.
    Returns processed digest payload + token/cost metrics.
    """
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    groq_key = (os.environ.get("GROQ_API_KEY") or "").strip()
    gemini_key = (os.environ.get("GEMINI_API_KEY") or "").strip()

    if dry_run or (not openai_key and not groq_key and not gemini_key):
        return heuristic_dry_run_process(clusters)

    prompt_content = build_prompt(clusters)

    providers: List[Tuple[str, str, Callable[[], Tuple[str, int, int, str]]]] = []
    if openai_key:
        providers.append((
            "openai",
            "gpt-4o-mini",
            lambda: call_openai(openai_key, prompt_content),
        ))
    if groq_key:
        providers.append((
            "groq",
            "auto-selected",
            lambda: call_groq(groq_key, prompt_content),
        ))
    if gemini_key:
        providers.append((
            "gemini",
            GEMINI_MODELS[0],
            lambda: call_gemini(gemini_key, prompt_content),
        ))

    errors = []
    for provider, model_label, call in providers:
        try:
            raw_response, prompt_tokens, completion_tokens, model_used = call()
            parsed = extract_json(raw_response)
            if provider == "openai":
                cost = (prompt_tokens * 0.00000015) + (completion_tokens * 0.00000060)
            elif provider == "gemini":
                cost = (prompt_tokens * 0.00000010) + (completion_tokens * 0.00000040)
            else:
                cost = 0.0
            parsed["tokens_prompt"] = prompt_tokens
            parsed["tokens_completion"] = completion_tokens
            parsed["estimated_cost_usd"] = round(cost, 6)
            parsed["model_used"] = f"{provider}/{model_used}"
            return parsed
        except Exception as e:
            print(f"[WARN] Provider '{provider}' ({model_label}) failed: {e}")
            errors.append(f"{provider}: {str(e)[:160]}")
            continue

    print("[WARN] All LLM providers failed; falling back to heuristic scoring.")
    fallback = heuristic_dry_run_process(clusters)
    fallback["model_used"] = f"fallback heuristic (errors: {' | '.join(errors)})"
    return fallback
