import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

# Lazy initialized client
_genai_client = None


def get_genai_client():
    global _genai_client
    if _genai_client is None and GEMINI_API_KEY:
        try:
            from google import genai

            _genai_client = genai.Client(api_key=GEMINI_API_KEY)
        except Exception as e:
            logger.warning("Could not initialize google.genai Client: %s", e)
    return _genai_client


def _call_gemini_json(prompt: str, retry: bool = True) -> Optional[Any]:
    """Call Gemini with strict JSON mode, retrying once on JSON parse failure."""
    client = get_genai_client()
    if not client:
        return None

    try:
        from google.genai import types

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        text = response.text or ""
        return json.loads(text)
    except json.JSONDecodeError:
        if retry:
            try:
                repair_prompt = (
                    f"{prompt}\n\nIMPORTANT: The previous output was invalid JSON. "
                    "Output ONLY valid JSON without markdown fences."
                )
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=repair_prompt,
                    config=config,
                )
                return json.loads(response.text or "")
            except Exception as e:
                logger.error("Gemini JSON retry failed: %s", e)
        return None
    except Exception as exc:
        logger.error("Gemini API call failed: %s", exc)
        return None


def extract_keywords(idea: str) -> Dict[str, Any]:
    """
    Extract broad and specific search keywords and a category from the idea.
    Broad term MUST be 1-2 common words for Google Trends.
    """
    prompt = f"""
Analyze this startup or product idea: "{idea}"
Return a strict JSON object with:
{{
  "broad": "1-2 common words for Google Trends search (e.g. 'expense tracker', 'tutor', 'pet care')",
  "specific": ["specific search phrase 1", "specific search phrase 2"],
  "category": "High level industry or category name"
}}
Ensure "broad" is extremely simple and common (1 or 2 words maximum) so Google Trends has volume.
"""
    result = _call_gemini_json(prompt)
    if (
        result
        and isinstance(result, dict)
        and "broad" in result
        and "specific" in result
        and "category" in result
    ):
        # Enforce broad is short
        broad_words = str(result["broad"]).split()
        if len(broad_words) > 2:
            result["broad"] = " ".join(broad_words[:2])
        return result

    # Deterministic fallback heuristic
    words = re.findall(r"\b[A-Za-z0-9]+\b", idea)
    broad = " ".join(words[:2]).lower() if len(words) >= 2 else idea.lower()
    return {
        "broad": broad or "startup",
        "specific": [idea, f"{broad} apps India"],
        "category": "Technology",
    }


def cluster_evidence(
    evidence_list: List[Dict[str, Any]],
    context: str,
    group: str = "pain",
    max_clusters: int = 5,
) -> List[Dict[str, Any]]:
    """
    Cluster evidence items into 3-6 thematic clusters.
    References evidence ONLY by ID. Never writes or paraphrases quotes.
    """
    if not evidence_list:
        return []

    # Format items for prompt: [ev_0007] (play_store, 1★) text...
    formatted_items = []
    for item in evidence_list[:80]:  # feed up to top 80 items
        ev_id = item["id"]
        source = item["source"]
        rating = f"{item['rating']}★" if item.get("rating") else "N/A"
        text = item["text"].replace("\n", " ")
        formatted_items.append(f"[{ev_id}] ({source}, {rating}) {text}")

    evidence_text = "\n".join(formatted_items)
    theme = "weaknesses and pain points" if group == "pain" else "strengths and user loves"

    prompt = f"""
You are an expert market analyst analyzing real user feedback for context: "{context}".
Here is the scanned evidence pool:
{evidence_text}

Task:
Group these items into 3 to {max_clusters} distinct clusters focused on {theme}.

STRICT RULES:
1. Reference evidence ONLY by their exact bracketed ID (e.g. "ev_0007").
2. NEVER write or paraphrase quotes in the output.
3. If a cluster has no supporting IDs, set ai_suggested=true.
4. Each cluster must have:
   - "title": Short punchy title (3-7 words)
   - "summary": 1-2 sentence description of the common problem or theme
   - "severity": "high", "medium", or "low"
   - "evidence_ids": list of exact ID strings (e.g. ["ev_0001", "ev_0004"])

Return a strict JSON list:
[
  {{
    "title": "...",
    "summary": "...",
    "severity": "high|medium|low",
    "evidence_ids": ["ev_..."]
  }}
]
"""
    result = _call_gemini_json(prompt)
    if result and isinstance(result, list):
        return result

    # Heuristic fallback if LLM unavailable
    clusters = []
    chunk_size = max(1, len(evidence_list) // 3)
    titles = (
        ["Frequent Performance & Lag Issues", "Confusing Interface & UX", "Missing Key Features"]
        if group == "pain"
        else ["Intuitive User Experience", "Reliable Performance", "Helpful Daily Utility"]
    )
    for i in range(min(3, len(titles))):
        sub_slice = evidence_list[i * chunk_size : (i + 1) * chunk_size]
        ev_ids = [it["id"] for it in sub_slice]
        clusters.append(
            {
                "title": titles[i],
                "summary": f"Users reported common themes regarding {titles[i].lower()}.",
                "severity": "high" if i == 0 else "medium",
                "evidence_ids": ev_ids,
            }
        )
    return clusters


def generate_opportunities(
    clusters: List[Dict[str, Any]],
    context: str,
) -> List[Dict[str, Any]]:
    """
    Generate strategic opportunities/concepts addressing the validated clusters.
    """
    cluster_summaries = []
    for c in clusters:
        cluster_summaries.append(
            f"Cluster ID: {c.get('id', 'cl_?')} | Title: {c.get('title')} | Summary: {c.get('summary')}"
        )
    clusters_text = "\n".join(cluster_summaries)

    prompt = f"""
You are a product strategist proposing high-leverage product opportunities for: "{context}".
Based on these user feedback clusters:
{clusters_text}

Task:
Propose 2-3 specific product opportunities or challenger plays.
Each opportunity must directly address one or more of the cluster IDs listed above.

Return a strict JSON list of objects:
[
  {{
    "title": "Short product concept title",
    "pitch": "1-2 sentence compelling value proposition explaining how it solves the pain points",
    "target_user": "Specific target audience in India",
    "addresses_cluster_ids": ["cl_1"]
  }}
]
"""
    result = _call_gemini_json(prompt)
    if result and isinstance(result, list):
        return result

    # Heuristic fallback
    opps = []
    if clusters:
        c1 = clusters[0]
        c1_id = c1.get("id", "cl_1")
        opps.append(
            {
                "title": f"Frictionless Alternative to {c1.get('title', 'Market Pain')}",
                "pitch": f"A purpose-built solution that completely eliminates user frustration around {c1.get('title', 'common complaints')}.",
                "target_user": "Digital-native Indian users",
                "addresses_cluster_ids": [c1_id],
            }
        )
    else:
        opps.append(
            {
                "title": "Modern Focused Solution",
                "pitch": "A streamlined product built specifically for underserved customer pain points.",
                "target_user": "Target Indian users",
                "addresses_cluster_ids": [],
            }
        )
    return opps


def classify_news(headlines_with_ids: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    Classify news items into positive, neutral, or negative sentiment.
    Input: [{"evidence_id": "ev_0101", "text": "..."}]
    Output: [{"evidence_id": "ev_0101", "sentiment": "positive|neutral|negative"}]
    """
    if not headlines_with_ids:
        return []

    items_text = "\n".join(
        [f"[{item['evidence_id']}] {item['text']}" for item in headlines_with_ids[:30]]
    )

    prompt = f"""
Classify the market sentiment of these headlines/news items:
{items_text}

For each item, classify as "positive", "neutral", or "negative".
Return a strict JSON list:
[
  {{
    "evidence_id": "ev_...",
    "sentiment": "positive|neutral|negative"
  }}
]
"""
    result = _call_gemini_json(prompt)
    if result and isinstance(result, list):
        # Validate output matches format
        valid_sentiments = {"positive", "neutral", "negative"}
        classified = []
        for r in result:
            if isinstance(r, dict) and "evidence_id" in r:
                s = r.get("sentiment", "neutral").lower()
                classified.append(
                    {
                        "evidence_id": r["evidence_id"],
                        "sentiment": s if s in valid_sentiments else "neutral",
                    }
                )
        return classified

    # Fallback sentiment analysis based on keyword heuristics
    classified = []
    neg_words = {"layoffs", "loss", "crash", "down", "fired", "scam", "shut", "decline", "fall"}
    pos_words = {"funding", "growth", "profit", "raises", "expands", "surges", "hiring", "record"}
    for item in headlines_with_ids:
        txt = item.get("text", "").lower()
        if any(w in txt for w in neg_words):
            s = "negative"
        elif any(w in txt for w in pos_words):
            s = "positive"
        else:
            s = "neutral"
        classified.append({"evidence_id": item["evidence_id"], "sentiment": s})
    return classified


def post_validate_and_enrich_clusters(
    raw_clusters: List[Dict[str, Any]],
    evidence_map: Dict[str, Dict[str, Any]],
    total_reviews_scanned: int,
    group: str = "pain",
) -> List[Dict[str, Any]]:
    """
    Post-validation and enrichment core (REQUIRED):
    - Strips any evidence_id that doesn't exist in evidence_map.
    - Computes frequency.count = len(valid_ids).
    - If count == 0: ai_suggested = True.
    - Assigns stable cluster IDs (cl_1, cl_2, ...).
    - Extracts apps_affected from the valid evidence entities.
    """
    validated_clusters: List[Dict[str, Any]] = []

    for idx, raw in enumerate(raw_clusters, start=1):
        cl_id = f"cl_{idx}"
        raw_ids = raw.get("evidence_ids", [])
        valid_ids = [eid for eid in raw_ids if eid in evidence_map]

        ai_suggested = len(valid_ids) == 0

        # Discover affected apps/entities from valid evidence
        affected_entities = []
        seen_entities = set()
        for eid in valid_ids:
            ent = evidence_map[eid].get("entity")
            if ent and ent not in seen_entities and ent != "News" and ent != "Reddit Discussion":
                seen_entities.add(ent)
                affected_entities.append(ent)

        count = len(valid_ids)
        total = max(total_reviews_scanned, count, 1)

        validated_clusters.append(
            {
                "id": cl_id,
                "group": group,
                "title": raw.get("title", f"Cluster {idx}"),
                "summary": raw.get("summary", ""),
                "severity": raw.get("severity", "medium").lower(),
                "frequency": {
                    "count": count,
                    "total": total,
                    "label": f"{count} of {total} reviews",
                },
                "apps_affected": affected_entities,
                "evidence_ids": valid_ids,
                "ai_suggested": ai_suggested,
            }
        )

    return validated_clusters


def post_validate_and_enrich_opportunities(
    raw_opps: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
    evidence_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Enrich opportunities with cluster references, valid evidence IDs, and ai_suggested flags.
    """
    cluster_map = {c["id"]: c for c in clusters}
    validated_opps: List[Dict[str, Any]] = []

    for idx, raw in enumerate(raw_opps, start=1):
        op_id = f"op_{idx}"
        addressed_ids = raw.get("addresses_cluster_ids", [])
        if not isinstance(addressed_ids, list):
            addressed_ids = [addressed_ids] if addressed_ids else []

        # Filter addressed clusters that actually exist
        valid_addressed = [cid for cid in addressed_ids if cid in cluster_map]
        if not valid_addressed and clusters:
            valid_addressed = [clusters[0]["id"]]

        # Collect evidence IDs from addressed clusters
        opp_evidence_ids = []
        seen_eids = set()
        for cid in valid_addressed:
            for eid in cluster_map[cid].get("evidence_ids", []):
                if eid in evidence_map and eid not in seen_eids:
                    seen_eids.add(eid)
                    opp_evidence_ids.append(eid)

        ai_suggested = len(opp_evidence_ids) == 0

        validated_opps.append(
            {
                "id": op_id,
                "title": raw.get("title", f"Opportunity {idx}"),
                "pitch": raw.get("pitch", ""),
                "target_user": raw.get("target_user", "Target market"),
                "addresses_cluster_ids": valid_addressed,
                "evidence_ids": opp_evidence_ids[:10],
                "ai_suggested": ai_suggested,
            }
        )

    return validated_opps
