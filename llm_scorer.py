import os
import json
import re
from typing import List, Dict, Any, Tuple
import requests

SYSTEM_INSTRUCTION = """You are a personal daily news-digest curator and summarizer for a specific user:
- A Computer Engineering student based in Italy, finishing bachelor's this academic year.
- Career goals: AI engineer, forward deployed AI engineer, or SDE (preparing for tech interviews).
- Interested in: building AI products and agents, tech/startup jobs in Italy & Europe.
- Follows: Turkey's news & economy (TRY, EUR, USD matter).
- Improving English.

Your task:
1. Score each item/story cluster 1-5 for relevance to the user's profile and goals (5 = highly relevant, 1 = low relevance).
2. For top items (score 4 or 5, or best in each category up to top 10 items total), generate:
   - A short, neutral 1-2 sentence summary using ONLY facts explicitly present in the provided title and snippet. NEVER hallucinate or invent outside facts.
   - "Why it matters to me:" exactly ONE short sentence tailored to the user's profile (career, engineering, exams/interviews, economy).
3. Strict Content Rules:
   - Neutral tone. No opinions, no predictions.
   - Turkey: If multiple source types (e.g. independent, international, official/government-aligned) covered the story, group under one item and explicitly state each source_type next to its summary so the user can compare how it is reported. If the sources differ, explicitly say "sources differ" and state what each one says.
   - Finance: NEVER give investment advice, buy/sell suggestions, or price predictions. ONLY state what happened, the number, and the source.
4. Vocabulary:
   - Up to 5 harder English words (B2-C1 level) found in today's digest with a short Turkish meaning and an English example sentence.
   - 5 Italian vocabulary words (A1-A2 level) relevant to tech, student life, or daily news, with definite article and gender (e.g., 'il lavoro (masculine)' or 'la laurea (feminine)').

Respond ONLY with valid JSON matching the requested schema.
"""

def extract_json(text: str) -> Dict[str, Any]:
    """Safely extract JSON from model output."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)

def call_gemini(api_key: str, prompt: str, model: str = None) -> Tuple[str, int, int, str]:
    """
    Call Gemini API with automatic model rollover if a model experiences 503 high demand spikes.
    """
    models_to_try = [model] if model else ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-3.8-flash"]
    last_err = None

    for m in models_to_try:
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
            resp = requests.post(url, json=payload, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    text = candidates[0]["content"]["parts"][0]["text"]
                    usage = data.get("usageMetadata", {})
                    prompt_tokens = usage.get("promptTokenCount", len(prompt) // 4)
                    completion_tokens = usage.get("candidatesTokenCount", len(text) // 4)
                    return text, prompt_tokens, completion_tokens, m
            print(f"[WARN] Gemini model '{m}' returned HTTP {resp.status_code}. Retrying with next model...")
            last_err = f"HTTP {resp.status_code}: {resp.text[:120]}"
        except Exception as e:
            print(f"[WARN] Request to Gemini model '{m}' failed: {e}. Retrying with next model...")
            last_err = str(e)

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
    resp = requests.post(base_url, headers=headers, json=payload, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"API error ({model}) {resp.status_code}: {resp.text}")
    
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", len(prompt) // 4)
    completion_tokens = usage.get("completion_tokens", len(text) // 4)
    return text, prompt_tokens, completion_tokens

def call_openai(api_key: str, prompt: str, model: str = "gpt-4o-mini") -> Tuple[str, int, int]:
    return call_openai_compatible(api_key, prompt, "https://api.openai.com/v1/chat/completions", model)

def call_groq(api_key: str, prompt: str, model: str = "llama-3.3-70b-versatile") -> Tuple[str, int, int]:
    return call_openai_compatible(api_key, prompt, "https://api.groq.com/openai/v1/chat/completions", model)

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
        # Score relevance to user
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

        # Create summary from first 1-2 sentences of snippet or title
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", snippet) if s.strip()]
        if sentences:
            summary = " ".join(sentences[:2])
        else:
            summary = title

        # Why it matters
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

        # Multi-source comparison for Turkey
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

    # Sort by relevance
    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    top_items = [it for it in scored if it["relevance_score"] >= 4][:12]

    # Deterministic vocabulary
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

def process_clusters(
    clusters: List[Dict[str, Any]],
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Score clusters, summarize top ones, and extract vocabulary.
    Returns processed digest payload + token/cost metrics.
    """
    openai_key = os.environ.get("OPENAI_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    gemini_key = os.environ.get("GEMINI_API_KEY")

    if dry_run or (not openai_key and not groq_key and not gemini_key):
        return heuristic_dry_run_process(clusters)

    # Format clusters into prompt
    cluster_prompts = []
    for c in clusters[:12]:  # limit to top 12 candidate clusters to conserve tokens and prevent API timeouts
        items_desc = []
        for it in c["items"]:
            items_desc.append({
                "source_name": it["source_name"],
                "source_type": it.get("source_type"),
                "title": it["title"],
                "snippet": it["snippet"][:400],
                "link": it["link"]
            })
        cluster_prompts.append({
            "cluster_id": c["cluster_id"],
            "category": c["category"],
            "items": items_desc
        })

    prompt_content = f"""{SYSTEM_INSTRUCTION}

Here are the candidate story clusters from today's feeds:
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
      "items": [
        {{
          "source_name": "Source Name",
          "source_type": "optional source_type",
          "link": "https://..."
        }}
      ],
      "summary": "1-2 sentence neutral summary using ONLY facts from the provided text.",
      "turkey_comparison": "Optional comparison of sources if multiple source types covered this Turkey story, otherwise null.",
      "why_it_matters": "One short sentence explaining why it matters to the user."
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

    model_name = ""
    prompt_tokens = 0
    completion_tokens = 0
    cost = 0.0
    raw_response = ""

    try:
        if openai_key:
            model_name = "gpt-4o-mini"
            raw_response, prompt_tokens, completion_tokens = call_openai(openai_key, prompt_content, model=model_name)
            # GPT-4o-mini pricing: $0.15/1M input, $0.60/1M output
            cost = (prompt_tokens * 0.00000015) + (completion_tokens * 0.00000060)
        elif groq_key:
            model_name = "llama-3.3-70b-versatile"
            raw_response, prompt_tokens, completion_tokens = call_groq(groq_key, prompt_content, model=model_name)
            # Groq free tier
            cost = 0.0
        elif gemini_key:
            raw_response, prompt_tokens, completion_tokens, model_name = call_gemini(gemini_key, prompt_content)
            # Gemini Flash pricing: $0.10/1M input, $0.40/1M output
            cost = (prompt_tokens * 0.00000010) + (completion_tokens * 0.00000040)

        parsed = extract_json(raw_response)
        parsed["tokens_prompt"] = prompt_tokens
        parsed["tokens_completion"] = completion_tokens
        parsed["estimated_cost_usd"] = round(cost, 6)
        parsed["model_used"] = model_name
        return parsed

    except Exception as e:
        print(f"[WARN] LLM call failed ({e}); falling back to heuristic scoring.")
        fallback = heuristic_dry_run_process(clusters)
        fallback["model_used"] = f"fallback heuristic (error: {str(e)})"
        return fallback
