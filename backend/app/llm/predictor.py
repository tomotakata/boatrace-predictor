"""
LLM prediction engine using Claude and Gemini.
Generates race predictions based on boat data.
"""
import json
from typing import Dict, Any
from backend.app.config import ANTHROPIC_API_KEY, GOOGLE_API_KEY


def _build_prompt(race: Dict[str, Any]) -> str:
    boats = race.get("boats", [])
    venue = race.get("venue", "")
    race_no = race.get("race_no", "")
    date = race.get("date", "")
    weather = race.get("weather", "")
    wind_speed = race.get("wind_speed", "")
    wind_direction = race.get("wind_direction", "")
    wave_height = race.get("wave_height", "")

    boat_lines = []
    for b in boats:
        lane = b.get("lane", "")
        name = b.get("name", "不明")
        rank = b.get("rank", "")
        national_win = b.get("national_win_rate", "")
        local_win = b.get("local_win_rate", "")
        motor_dash = b.get("motor_dashfoot", "")
        motor_ext = b.get("motor_extfoot", "")
        exh_time = b.get("exhibition_time", "")
        exh_st = b.get("exhibition_st", "")
        avg_st = b.get("avg_st", "")
        motor_place2 = b.get("motor_place2_rate", "")

        boat_lines.append(
            f"  {lane}号艇: {name}({rank}) "
            f"全国勝率:{national_win} 当地勝率:{local_win} "
            f"モーター出足:{motor_dash} 伸足:{motor_ext} 2連率:{motor_place2} "
            f"展示タイム:{exh_time} 展示ST:{exh_st} 平均ST:{avg_st}"
        )

    boats_str = "\n".join(boat_lines)

    return f"""以下の競艇レース情報を分析し、予測結果をJSON形式で返してください。

【レース情報】
日付: {date}
場: {venue} {race_no}R
天候: {weather} 風速:{wind_speed}m {wind_direction} 波高:{wave_height}cm

【出走艇データ】
{boats_str}

【出力形式】(JSON)
{{
  "ei": [1号艇EI, 2号艇EI, 3号艇EI, 4号艇EI, 5号艇EI, 6号艇EI],
  "ti": [1号艇TI, 2号艇TI, 3号艇TI, 4号艇TI, 5号艇TI, 6号艇TI],
  "judgement": ["頭/軸/紐/消", ...6艇分],
  "pattern": "レース展開パターンの説明",
  "main_attack": "主要な攻め手の説明",
  "sink_candidate": "沈み候補の説明",
  "suji": "特記事項",
  "exacta": "本命2連単 (例: 1-2)",
  "trifecta": "本命3連単 (例: 1-2-3)",
  "honmei_exacta": ["本命党2連単候補1", "候補2"],
  "honmei_trifecta": ["本命党3連単候補1", "候補2"],
  "ana_exacta": ["穴党2連単候補1", "候補2"],
  "ana_trifecta": ["穴党3連単候補1", "候補2"],
  "classification": "レース分類 (本命/中穴/大穴)",
  "confidence": 0.0から1.0の確信度
}}

EI(期待指数)とTI(戦術指数)は各艇の勝率を0.0〜10.0で評価した数値です。
judgementは「頭」(1着候補)、「軸」(2-3着候補)、「紐」(3連絡み候補)、「消」(消し)のいずれか。
JSONのみを返してください。"""


async def run_claude_prediction(race: Dict[str, Any]) -> Dict[str, Any]:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _build_prompt(race)

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = message.content[0].text.strip()
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
    return json.loads(response_text)


async def run_gemini_prediction(race: Dict[str, Any]) -> Dict[str, Any]:
    import google.generativeai as genai
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-pro")
    prompt = _build_prompt(race)

    response = model.generate_content(prompt)
    response_text = response.text.strip()
    if response_text.startswith("```"):
        response_text = response_text.split("```")[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
    return json.loads(response_text)


async def run_ensemble_prediction(race: Dict[str, Any]) -> Dict[str, Any]:
    """Run both Claude and Gemini predictions and merge."""
    results = {}
    try:
        claude_result = await run_claude_prediction(race)
        results["claude"] = claude_result
    except Exception as e:
        results["claude"] = None

    try:
        gemini_result = await run_gemini_prediction(race)
        results["gemini"] = gemini_result
    except Exception as e:
        results["gemini"] = None

    # Merge: average EI/TI, use Claude's text fields as primary
    valid = [r for r in results.values() if r is not None]
    if not valid:
        raise RuntimeError("Both Claude and Gemini predictions failed")

    primary = valid[0]

    if len(valid) == 2:
        claude_r = results.get("claude", {}) or {}
        gemini_r = results.get("gemini", {}) or {}

        def avg_list(a, b, n=6):
            if not a or not b:
                return a or b or [0.0] * n
            return [round((a[i] + b[i]) / 2, 2) if i < len(a) and i < len(b) else 0.0 for i in range(n)]

        merged = {
            **claude_r,
            "ei": avg_list(claude_r.get("ei"), gemini_r.get("ei")),
            "ti": avg_list(claude_r.get("ti"), gemini_r.get("ti")),
            "confidence": round(
                ((claude_r.get("confidence") or 0.5) + (gemini_r.get("confidence") or 0.5)) / 2, 2
            )
        }
        return merged

    return primary


async def run_prediction(race: Dict[str, Any], source: str = "ensemble") -> Dict[str, Any]:
    if source == "claude":
        return await run_claude_prediction(race)
    elif source == "gemini":
        return await run_gemini_prediction(race)
    else:
        return await run_ensemble_prediction(race)
