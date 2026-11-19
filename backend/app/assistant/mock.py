"""Deterministic mock provider (demo mode, used automatically when no API key is set).

It behaves like a model inside the same agent loop: on the first call it chooses tools from the
question (real tools, real data), and once the tool results are in the conversation it writes the
answer from templates filled ONLY with numbers from those results. It can also propose a task
(write tool -> approval card). English, French and Arabic templates for the main intents.
"""

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from .providers import LLMProvider

ARABIC = re.compile(r"[؀-ۿ]")
FR_WORDS = re.compile(
    r"\b(le|la|les|du|des|quel|quelle|quels|pourquoi|est-ce|mon|mes|bassin|oxyg[eè]ne|aujourd|"
    r"risque|combien|revenu|capteur|sonde|alertes?|faire|dois|bénéfice|coût|nuit)\b",
    re.I,
)


def detect_lang(q: str) -> str:
    if ARABIC.search(q):
        return "ar"
    return "fr" if len(FR_WORDS.findall(q)) >= 1 and not re.search(r"\b(the|what|why|how|is)\b", q, re.I) else "en"


T = {
    "refusal": {
        "en": "I can help with this farm's water, alerts, probes, costs and fish-farming practice. That question is outside what I can answer here.",
        "fr": "Je peux vous aider sur l'eau, les alertes, les sondes, les coûts de cette ferme et les pratiques d'élevage. Cette question sort de ce que je peux traiter ici.",
        "ar": "يمكنني المساعدة في ما يخص مياه هذه المزرعة وتنبيهاتها ومستشعراتها وتكاليفها وممارسات تربية الأسماك. هذا السؤال خارج ما يمكنني الإجابة عنه هنا.",
    },
    "no_alerts": {
        "en": "No open alerts right now. The alert engine is still checking every basin every few seconds.",
        "fr": "Aucune alerte ouverte pour le moment. Le moteur d'alertes continue de vérifier chaque bassin.",
        "ar": "لا توجد تنبيهات مفتوحة حاليًا. يواصل محرك التنبيهات مراقبة كل حوض.",
    },
    "alerts_head": {
        "en": "You have **{n} open alert{s}**:",
        "fr": "Vous avez **{n} alerte{s} ouverte{s}** :",
        "ar": "لديك **{n} تنبيهات مفتوحة**:",
    },
    "alerts_tail": {
        "en": "Start with the highest severity. Hardware alerts go to the technician.",
        "fr": "Commencez par la plus grave. Les alertes matérielles vont au technicien.",
        "ar": "ابدأ بالأشد خطورة. تنبيهات الأجهزة تُحال إلى الفني.",
    },
    "today_head": {
        "en": "Here is what needs you today:",
        "fr": "Voici ce qui demande votre attention aujourd'hui :",
        "ar": "إليك ما يحتاج إلى انتباهك اليوم:",
    },
    "risk_head": {
        "en": "**{level} overall.** These are model estimates, not certainties.",
        "fr": "**Risque {level_fr} dans l'ensemble.** Ce sont des estimations du modèle, pas des certitudes.",
        "ar": "**المستوى العام: {level_ar}.** هذه تقديرات من النموذج وليست يقينًا.",
    },
    "o2_main": {
        "en": "Oxygen in **{basin}** fell to **{low} mg/L at {at}**{under}. Right now it is {now} mg/L ({sat}% of saturation at {temp} °C).",
        "fr": "Dans **{basin}**, l'oxygène est descendu à **{low} mg/L à {at}**{under_fr}. En ce moment il est à {now} mg/L ({sat} % de saturation à {temp} °C).",
        "ar": "انخفض الأكسجين في **{basin}** إلى **{low} ملغ/لتر عند {at}**{under_ar}. القيمة الحالية {now} ملغ/لتر ({sat}% من التشبع عند {temp} °م).",
    },
    "o2_why": {
        "en": "This is the normal night pattern: algae stop making oxygen after sunset but keep using it until dawn, so the low comes just before sunrise. The evening feed adds demand{trout}.",
        "fr": "C'est le cycle normal de la nuit : les algues cessent de produire de l'oxygène après le coucher du soleil mais continuent d'en consommer jusqu'à l'aube. Le repas du soir augmente la demande{trout_fr}.",
        "ar": "هذا هو النمط الليلي المعتاد: تتوقف الطحالب عن إنتاج الأكسجين بعد الغروب لكنها تستمر في استهلاكه حتى الفجر، فيأتي أدنى مستوى قبل الشروق. وجبة المساء تزيد الطلب{trout_ar}.",
    },
    "o2_actions": {
        "en": "1. Cut tonight's evening feed in {basin} by about a third.\n2. Run the aerator from 22:00 until after sunrise.\n3. Check the reading again at 05:00.",
        "fr": "1. Réduisez d'un tiers le repas du soir dans {basin}.\n2. Faites tourner l'aérateur de 22:00 jusqu'après le lever du soleil.\n3. Vérifiez à nouveau la mesure à 05:00.",
        "ar": "1. خفّض وجبة المساء الليلة في {basin} بنحو الثلث.\n2. شغّل جهاز التهوية من 22:00 حتى بعد شروق الشمس.\n3. تحقق من القراءة مجددًا عند 05:00.",
    },
    "sensor_main": {
        "en": "**Probably a sensor problem, not the water.** Probe {probe} ({measures}, {basin}) is {status}: {evidence}. Real water never stays that flat.",
        "fr": "**Probablement un problème de capteur, pas de l'eau.** La sonde {probe} ({measures}, {basin}) est {status} : {evidence}. Une eau réelle ne reste jamais aussi stable.",
        "ar": "**على الأرجح مشكلة في المستشعر وليست في الماء.** المستشعر {probe} ({measures}، {basin}) حالته {status}: {evidence}. الماء الحقيقي لا يبقى ثابتًا هكذا.",
    },
    "sensor_tail": {
        "en": "This goes to the technician, not the worker on shift.",
        "fr": "Cela concerne le technicien, pas l'ouvrier de garde.",
        "ar": "هذا من اختصاص الفني وليس العامل المناوب.",
    },
    "kb_head": {
        "en": "From the farm's knowledge base:",
        "fr": "D'après la base de connaissances de la ferme :",
        "ar": "من قاعدة معارف المزرعة:",
    },
}
LEVEL_FR = {"High": "élevé", "Medium": "moyen", "Low": "faible"}
LEVEL_AR = {"High": "مرتفع", "Medium": "متوسط", "Low": "منخفض"}


def t(key: str, lang: str, **kw) -> str:
    d = T[key]
    return d.get(lang, d["en"]).format(**kw)


@dataclass
class Plan:
    intent: str
    lang: str
    basin: str | None = None
    extra: dict = field(default_factory=dict)


def _basin_ref(q: str, page: dict) -> str | None:
    m = re.search(r"(?:basin|bassin|حوض)\s*(\d+)", q, re.I)
    if m:
        return f"Basin {m.group(1)}"
    return page.get("basin")


def route(q: str, page: dict, role: str) -> Plan:
    s = q.lower()
    lang = detect_lang(q)
    b = _basin_ref(q, page)
    if re.search(r"ignore (all |the )?(previous|above) instructions|system prompt|jailbreak|password", s):
        return Plan("refusal", lang)
    if re.search(r"which (sensors?|probes?)|quelles? sondes?", s):
        return Plan("calibration", lang)
    domain = re.search(
        r"fish|oxygen|water|pond|basin|feed|ammonia|\bph\b|probe|trout|tilapia|carp|salmon|bass|bream|"
        r"aerat|calibrat|temperature|fcr|stocking|nitrite|algae",
        s,
    )
    personal = re.search(
        r"\b(my|our|we|last night|today|tonight|right now|now|this (farm|shift|week|quarter)|first|"
        r"revenue|profit|margin|alerts?|risk)\b",
        s,
    )
    if re.match(r"(what|how|why|does|do|is|are|should|when|at what|which)\b", s) and domain and not personal and not b:
        return Plan("knowledge", lang, None, {"query": q})
    m = re.search(r"explain alert ([0-9a-f-]{36})", s)
    if m:
        return Plan("alert", lang, extra={"alert_id": m.group(1)})
    if re.search(r"(create|add|make|schedule|remind|crée|créer|planifie|ajoute).{0,30}(task|tâche|reminder|rappel)", s):
        return Plan("action", lang, b, {"q": q})
    if re.search(r"oxygen risk|risque d.oxyg|explain this estimate|prediction|prévision", s) and b:
        return Plan("prediction", lang, b)
    if re.search(r"what if|add \d+|more fish|simulate|et si|ajoute \d+|cut .*feed.*%|feeding costs? by", s):
        n = re.search(r"(\d{2,6})\s*(fish|poissons)", s)
        pct = re.search(r"(\d{1,2})\s*%", s)
        extra = {"add_fish": int(n.group(1))} if n else ({"feed_cost_pct": -int(pct.group(1))} if pct else {"add_fish": 500})
        return Plan("whatif", lang, b or "Basin 1", extra)
    if re.search(r"maintenance|open tasks|tâches", s):
        return Plan("maintenance", lang)
    if re.search(r"calibrat|which sensors?|quelles? sondes?", s):
        return Plan("calibration", lang)
    if re.search(r"sensor|probe|stuck|broken|capteur|sonde|مستشعر|حساس", s):
        return Plan("sensor", lang, b)
    if re.search(r"compare|ranking|classement|rank", s):
        return Plan("compare", lang, extra={"metric": "margin" if re.search(r"margin|marge|profit", s) else "avg_oxygen"})
    if re.search(r"revenue|profit|money|cost|margin|earn|revenu|bénéfice|coût|marge|إيراد|ربح|تكلفة", s):
        return Plan("revenue", lang)
    if re.search(r"risk|danger|risque|خطر|مخاطر", s):
        return Plan("risk", lang)
    if re.search(r"summar|open alerts|alerts|résum|alertes|تنبيه", s):
        return Plan("alerts", lang)
    if re.search(r"attention|today|first|shift|priorit|this week|actions|aujourd|d'abord|semaine|اليوم|أولا", s):
        return Plan("today", lang)
    if re.search(r"oxygen|o2|curve|drop|explain|oxygène|courbe|أكسجين", s):
        return Plan("oxygen", lang, b)
    if re.search(r"\bph\b|acid|ammonia|ammoniac|nitrite", s):
        return Plan("knowledge", lang, b, {"query": q})
    if re.search(
        r"temperature|feed|fcr|stocking|density|trout|tilapia|carp|salmon|bass|bream|aerat|fish|"
        r"température|truite|carpe|aliment|densité|poisson|سمك|حرارة",
        s,
    ):
        return Plan("knowledge", lang, b, {"query": q})
    return Plan("refusal", lang)


def _parse(content: str) -> dict:
    m = re.search(r"<tool_data>\n(.*)\n</tool_data>", content, re.S)
    try:
        return json.loads(m.group(1) if m else content)
    except (json.JSONDecodeError, AttributeError):
        return {}


def conversation_state(messages: list[dict]) -> tuple[str, dict[str, list[dict]], int]:
    """(last user question, {tool name: [results]} since that question, number of tool rounds)."""
    q, start = "", 0
    for i, m in enumerate(messages):
        if m["role"] == "user" and any(b.get("type") == "text" for b in m["content"]):
            q = next(b["text"] for b in m["content"] if b.get("type") == "text")
            start = i
    names: dict[str, str] = {}
    results: dict[str, list[dict]] = {}
    rounds = 0
    for m in messages[start + 1 :]:
        for b in m["content"]:
            if b.get("type") == "tool_use":
                names[b["id"]] = b["name"]
            elif b.get("type") == "tool_result":
                results.setdefault(names.get(b["tool_use_id"], "?"), []).append(_parse(b["content"]))
        if m["role"] == "assistant":
            rounds += 1
    return q, results, rounds


def read_context(system: list[dict]) -> tuple[str, dict]:
    txt = "\n".join(b["text"] for b in system)
    role = (re.search(r"USER ROLE: (\w+)", txt) or [None, "owner"])[1]
    page = {}
    m = re.search(r"CURRENT PAGE: ([^\n]+)", txt)
    if m:
        page["page"] = m.group(1)
        bm = re.search(r"basin=([^;\n]+)", m.group(1))
        if bm:
            page["basin"] = bm.group(1).strip()
    return role, page


class MockProvider(LLMProvider):
    name = "mock"
    model = "mock-templates"

    async def stream_chat(self, system, messages, tools, max_tokens) -> AsyncIterator[dict]:
        role, page = read_context(system)
        q, res, rounds = conversation_state(messages)
        plan = route(q, page, role)
        calls = self.next_calls(plan, res, rounds, role)
        if calls:
            for i, (name, args) in enumerate(calls):
                yield {"type": "tool_use", "id": f"mock_{rounds}_{i}", "name": name, "input": args}
            yield {"type": "usage", "input": 0, "output": 0, "cache_read": 0}
            yield {"type": "stop", "reason": "tool_use"}
            return
        text, action = self.compose(plan, res, role)
        for w in re.split(r"(\s+)", text):
            yield {"type": "text", "text": w}
        if action:
            yield {"type": "tool_use", "id": f"mock_{rounds}_act", "name": "create_maintenance_task", "input": action}
        yield {"type": "usage", "input": 0, "output": 0, "cache_read": 0}
        yield {"type": "stop", "reason": "tool_use" if action else "end_turn"}

    # ---------- which tools, in which order ----------
    def next_calls(self, p: Plan, res: dict, rounds: int, role: str) -> list[tuple[str, dict]]:
        if p.intent in ("refusal", "action") or rounds >= 3:
            return []
        if p.intent == "today" and rounds == 0:
            return [("get_farm_briefing", {}), ("get_alerts", {"status": "open"}), ("get_oxygen_prediction", {})]
        if p.intent == "risk" and rounds == 0:
            return [("get_oxygen_prediction", {}), ("get_alerts", {"status": "open"})]
        if p.intent == "alerts" and rounds == 0:
            return [("get_alerts", {"status": "open"})]
        if p.intent == "maintenance" and rounds == 0:
            return [("get_maintenance", {"upcoming_only": False, "limit": 10})]
        if p.intent == "calibration" and rounds == 0:
            return [("get_sensor_health", {})]
        if p.intent == "sensor" and rounds == 0:
            return [("get_sensor_health", {"basin_id": p.basin} if p.basin else {}), ("get_alerts", {"status": "open"})]
        if p.intent == "revenue" and rounds == 0:
            if role != "owner":
                return []
            return [
                ("get_financials", {"period": "quarter"}),
                ("compare_basins", {"metric": "margin", "period": "quarter"}),
                ("search_knowledge", {"query": "feed cost share FCR profit"}),
            ]
        if p.intent == "compare" and rounds == 0:
            if p.extra["metric"] == "margin" and role != "owner":
                return []
            return [
                (
                    "compare_basins",
                    {"metric": p.extra["metric"], "period": "quarter" if p.extra["metric"] == "margin" else "week"},
                )
            ]
        if p.intent == "whatif" and rounds == 0:
            if role != "owner":
                return []
            return [("simulate_scenario", {"basin_id": p.basin, **p.extra}), ("get_basin_status", {"basin_id": p.basin})]
        if p.intent == "prediction" and rounds == 0:
            return [("get_oxygen_prediction", {"basin_id": p.basin}), ("get_basin_status", {"basin_id": p.basin})]
        if p.intent == "knowledge" and rounds == 0:
            sp = {
                "trout": "rainbow_trout",
                "truite": "rainbow_trout",
                "tilapia": "tilapia",
                "carp": "common_carp",
                "carpe": "common_carp",
                "salmon": "atlantic_salmon",
            }
            species = next((v for k, v in sp.items() if k in p.extra["query"].lower()), None)
            return [("search_knowledge", {"query": p.extra["query"], **({"species": species} if species else {})})]
        if p.intent == "oxygen":
            if rounds == 0 and not p.basin:
                return [("get_alerts", {"status": "open"}), ("list_basins", {})]
            basin = p.basin or self._pick_o2_basin(res)
            if basin and "get_readings" not in res:
                p.basin = basin
                return [
                    ("get_readings", {"basin_id": basin, "metric": "dissolved_oxygen"}),
                    ("get_basin_status", {"basin_id": basin}),
                    ("search_knowledge", {"query": "night oxygen dip dawn aeration"}),
                ]
        if p.intent == "alert":
            if rounds == 0:
                return [("get_alerts", {"status": "all", "limit": 50})]
            a = self._alert(p, res)
            if a and rounds == 1:
                if a["kind"] == "hardware":
                    return [("get_sensor_health", {"basin_id": a["basin"]})]
                if "oxygen" in a["title"].lower():
                    return [
                        ("get_readings", {"basin_id": a["basin"], "metric": "dissolved_oxygen"}),
                        ("get_basin_status", {"basin_id": a["basin"]}),
                        ("search_knowledge", {"query": "night oxygen dip dawn aeration"}),
                    ]
                metric = "ph" if "ph" in a["title"].lower() else "temperature"
                return [
                    ("get_readings", {"basin_id": a["basin"], "metric": metric}),
                    ("search_knowledge", {"query": "ammonia toxic high pH" if metric == "ph" else "temperature limits"}),
                ]
        return []

    @staticmethod
    def _pick_o2_basin(res: dict) -> str | None:
        for r in res.get("get_alerts", []):
            for a in r.get("alerts", []):
                if "oxygen" in a["title"].lower():
                    return a["basin"]
        basins = (res.get("list_basins") or [{}])[0].get("basins", [])
        if basins:
            return min(basins, key=lambda b: b.get("oxygen_mg_l") or 99)["name"]
        return None

    @staticmethod
    def _alert(p: Plan, res: dict) -> dict | None:
        for r in res.get("get_alerts", []):
            for a in r.get("alerts", []):
                if a["id"] == p.extra.get("alert_id"):
                    return a
        return None

    # ---------- the answer, from tool results only ----------
    def compose(self, p: Plan, res: dict, role: str) -> tuple[str, dict | None]:
        L = p.lang
        first = {k: v[-1] for k, v in res.items() if v}
        errors = [v.get("error") for v in first.values() if isinstance(v, dict) and v.get("error")]
        if p.intent == "refusal":
            return t("refusal", L), None
        if role != "owner" and p.intent in ("revenue", "whatif") or (p.intent == "compare" and not first):
            return (
                "Financial data is only available to the farm owner. I can help with your basins, water alerts and probes."
            ), None
        if errors and p.intent not in ("today",):
            return f"I couldn't get that data: {errors[0]} Try naming a basin from your farm, for example Basin 1.", None

        if p.intent == "alerts":
            al = first.get("get_alerts", {}).get("alerts", [])
            if not al:
                return t("no_alerts", L), None
            lines = "\n".join(f"- **{a['basin']}** · {a['title']} ({a['severity']}, {a['kind']}, {a['at']})" for a in al[:6])
            return f"{t('alerts_head', L, n=len(al), s='' if len(al) == 1 else 's')}\n\n{lines}\n\n{t('alerts_tail', L)}", None

        if p.intent == "today":
            br = first.get("get_farm_briefing", {})
            items = br.get("top_actions") or []
            bullets = br.get("bullets") or []
            body = (
                "\n".join(f"{i}. **{a['title']}** · {a['detail']}" for i, a in enumerate(items, 1))
                if items
                else "\n".join(f"- {b}" for b in bullets)
            )
            if role != "owner":
                al = first.get("get_alerts", {}).get("alerts", [])
                body = (
                    "\n".join(
                        f"{i}. **{a['basin']}**: {a['title']} ({a['severity']}) · {a['description']}"
                        for i, a in enumerate(al[:3], 1)
                    )
                    or "- No open alerts for you. Walk the basins and note anything unusual in your shift report."
                )
            action = None
            o2 = next((a for a in first.get("get_alerts", {}).get("alerts", []) if "oxygen" in a["title"].lower()), None)
            if o2 and role in ("owner", "technician"):
                action = {
                    "title": f"Run the {o2['basin']} aerator 22:00–07:00 tonight",
                    "basin_id": o2["basin"],
                    "due": "Tonight",
                }
            return f"{t('today_head', L)}\n\n{body}", action

        if p.intent == "risk":
            preds = [
                x for x in first.get("get_oxygen_prediction", {}).get("predictions", []) if x.get("probability_pct") is not None
            ]
            if not preds:
                return "The oxygen model has no prediction yet: it needs a few hours of readings per basin.", None
            top = max(x["probability_pct"] for x in preds)
            level = "High" if top > 70 else "Medium" if top > 30 else "Low"
            lines = "\n".join(
                f"- **{x['basin']}** ({x['species']}): {x['probability_pct']}% chance of {x['event']}"
                for x in sorted(preds, key=lambda x: -x["probability_pct"])
            )
            return f"{t('risk_head', L, level=level, level_fr=LEVEL_FR[level], level_ar=LEVEL_AR[level])}\n\n{lines}", None

        if (
            p.intent in ("oxygen", "alert")
            and "get_readings" in first
            and first["get_readings"].get("metric") == "dissolved_oxygen"
        ):
            r, st = first["get_readings"], first.get("get_basin_status", {})
            warn = st.get("thresholds", {}).get("oxygen_warning_mg_l")
            sp = st.get("species", "")
            low = r["min"]
            under = f", under the **{warn} mg/L** warning level for {sp.lower()}" if warn and low["value"] < warn else ""
            under_fr = f", sous le seuil d'alerte de **{warn} mg/L** pour la {sp.lower()}" if warn and low["value"] < warn else ""
            under_ar = f"، أي أقل من حد التحذير **{warn} ملغ/لتر**" if warn and low["value"] < warn else ""
            live = st.get("live", {})
            now = live.get("oxygen", {}).get("value", r["latest"]["value"])
            temp = live.get("temperature", {}).get("value", "–")
            trout = "trout" in sp.lower()
            text = (
                t(
                    "o2_main",
                    L,
                    basin=r["basin"],
                    low=f"{low['value']:.2f}",
                    at=low["at"].split()[-1],
                    under=under,
                    under_fr=under_fr,
                    under_ar=under_ar,
                    now=f"{now:.2f}",
                    sat=round(st["oxygen_saturation_pct"]) if st.get("oxygen_saturation_pct") is not None else "–",
                    temp=f"{temp:.1f}" if isinstance(temp, int | float) else temp,
                )
                + "\n\n"
                + t(
                    "o2_why",
                    L,
                    trout=", and trout need more oxygen than tilapia or carp" if trout else "",
                    trout_fr=", et la truite a besoin de plus d'oxygène que le tilapia ou la carpe" if trout else "",
                    trout_ar="، والسلمون المرقط يحتاج إلى أكسجين أكثر من البلطي والشبوط" if trout else "",
                )
            )
            if warn and low["value"] < warn:
                text += "\n\n" + t("o2_actions", L, basin=r["basin"])
                action = (
                    {"title": f"Run the {r['basin']} aerator 22:00–07:00 tonight", "basin_id": r["basin"], "due": "Tonight"}
                    if role in ("owner", "technician")
                    else None
                )
                return text, action
            return text + "\n\nIt stayed above the warning level, so no action is needed tonight.", None

        if p.intent == "alert" and "get_readings" in first:
            r = first["get_readings"]
            k = (first.get("search_knowledge", {}).get("results") or [{}])[0]
            if r["metric"] == "ph":
                return (
                    f"**{r['basin']}** pH peaked at **{r['max']['value']} at {r['max']['at']}** (range in the last 24 h: "
                    f"{r['min']['value']}–{r['max']['value']}). pH rises in the afternoon when algae use up carbon dioxide, "
                    "so a high afternoon pH usually means a strong algae bloom.\n\nHigh pH also makes ammonia more toxic: "
                    "at 24 °C the toxic share is 0.0502 at pH 8 and 0.3456 at pH 9, about seven times more"
                    f"{' (' + k.get('title', '') + ')' if k else ''}.\n\n1. Test ammonia today.\n2. Avoid adding lime or "
                    "fertilizer.\n3. Re-check pH at 15:00 tomorrow."
                ), None
            return (
                f"**{r['basin']}** {r['metric']}: highest {r['max']['value']} {r['unit']} at {r['max']['at']}, lowest "
                f"{r['min']['value']} {r['unit']} at {r['min']['at']}. One reading outside the range can be noise; if the "
                "next readings stay out of range, act on it."
            ), None

        if p.intent in ("sensor", "calibration") or (p.intent == "alert" and "get_sensor_health" in first):
            h = first.get("get_sensor_health", {})
            probs = h.get("problems", [])
            if p.intent == "calibration" or not probs:
                if not probs:
                    return "Every probe reads normally. The pipeline checks them with rolling statistics on the last 24 h.", None
                lines = "\n".join(
                    f"- **{x['probe']}**, {x['basin']} {x['measures']}: {x['status']}. {x['evidence']}. "
                    f"Last calibrated {x['last_calibrated']}."
                    for x in probs
                )
                return f"{len(probs)} of your {len(h.get('probes', []))} probes need attention:\n\n{lines}", None
            x = next((y for y in probs if y["status"] == "stuck"), probs[0])
            text = t(
                "sensor_main",
                L,
                probe=x["probe"],
                measures=x["measures"],
                basin=x["basin"],
                status=x["status"],
                evidence=x["evidence"],
            )
            text += "\n\n" + t("sensor_tail", L)
            action = (
                {
                    "title": f"Check and recalibrate the {x['basin']} {x['measures']} probe ({x['probe']})",
                    "basin_id": x["basin"],
                    "due": "Today",
                }
                if role in ("owner", "technician")
                else None
            )
            return text, action

        if p.intent == "revenue":
            f = first.get("get_financials", {})
            tot, rows = f.get("total", {}), sorted(f.get("basins", []), key=lambda r: r["margin_pct"] or 0)
            if not rows:
                return "There are no basin finances yet. Add revenue and costs on each basin page.", None
            low, best = rows[0], rows[-1]
            text = (
                f"Your farm made **€{tot['profit_eur']:,}** profit this quarter (margin {tot['margin_pct']}%). Feed is "
                f"**{tot['feed_share_pct']}%** of all costs, so feed is where small changes matter most.\n\n"
                f"1. **{low['basin']}** has the lowest margin ({low['margin_pct']}%, €{low['profit_per_fish_eur']} per fish). "
                "Weigh a sample of fish and check how much feed turns into growth (FCR) before buying more feed.\n"
                f"2. **{best['basin']}** earns the most per fish (€{best['profit_per_fish_eur']}). If its oxygen stays "
                "safe, it is the best basin to grow.\n"
                "3. Skip the evening meal on nights the model predicts low oxygen: fish eat less then and the feed is wasted."
            )
            return text, None

        if p.intent == "maintenance":
            m = first.get("get_maintenance", {})
            tasks = "\n".join(
                f"- {x['title']} · {x['status']} · {x['assignee'] or 'unassigned'} · due {x['due'] or 'no date'}"
                for x in m.get("tasks", [])[:6]
            )
            # free-text notes are user-written data: they are summarised by type and probe, never repeated as orders
            logs = "\n".join(f"- {x['work']} on probe {x['probe'] or '–'} ({x['at']})" for x in m.get("recent_logs", [])[:4])
            return (
                f"**Maintenance tasks:**\n\n{tasks or '- none'}\n\n**Recent maintenance logs:**\n\n{logs or '- none'}\n\n"
                "Open a log in the reports inbox to read the technician's full note."
            ), None

        if p.intent == "compare":
            c = first.get("compare_basins", {})
            lines = "\n".join(f"{i}. **{r['basin']}**: {r['value']} {r['unit']}" for i, r in enumerate(c.get("ranking", []), 1))
            return f"Ranking by {c.get('metric', '').replace('_', ' ')} ({c.get('period')}):\n\n{lines}", None

        if p.intent == "whatif":
            s = first.get("simulate_scenario", {})
            b0, b1 = s["before"], s["after"]
            change = s["changes"]
            what = (
                f"add **{change['add_fish']} fish**"
                if "add_fish" in change
                else f"change feed cost by **{change.get('feed_cost_pct')}%**"
            )
            sign = "+" if s["profit_change_eur"] >= 0 else ""
            text = (
                f"If you {what} in **{s['basin']}** (estimate, same growth and price as now):\n\n"
                f"- Revenue: €{b0['revenue_eur']:,} → **€{b1['revenue_eur']:,}**\n"
                f"- Feed cost: €{b0['feed_cost_eur']:,} → **€{b1['feed_cost_eur']:,}**\n"
                f"- Profit: €{b0['profit_eur']:,} → **€{b1['profit_eur']:,}** ({sign}€{s['profit_change_eur']:,})\n"
                f"- Density: {b0['density_fish_per_m3']} → **{b1['density_fish_per_m3']} fish per m³**"
            )
            if s.get("risks"):
                text += "\n\n" + " ".join(s["risks"])
            return text, None

        if p.intent == "prediction":
            pr = (first.get("get_oxygen_prediction", {}).get("predictions") or [{}])[0]
            if pr.get("probability_pct") is None:
                return "There is no prediction for this basin yet: the model needs a few hours of readings.", None
            feats = "; ".join(f"{f['label'].lower()} {f['value']} {f['unit']}".strip() for f in pr["top_features"])
            return (
                f"The model gives **{pr['basin']}** a **{pr['probability_pct']}% chance** of {pr['event']} "
                f"(estimate, model {pr['model_version']}, computed {pr['computed_at']}).\n\nIt looks mostly at last night's "
                f"low, the water temperature and the feeding load. Current inputs: {feats}.\n\nTreat it as an early "
                "warning, not a certainty: if it is high, cut the evening feed and plan to aerate tonight."
            ), None

        if p.intent == "knowledge":
            hits = first.get("search_knowledge", {}).get("results", [])
            if not hits:
                return t("refusal", L), None
            h = hits[0]
            sentences = re.split(r"(?<=[.!?])\s+", h["text"].replace("\n", " "))
            snippet = " ".join(sentences[:3])
            return f"{t('kb_head', L)} {snippet}\n\n(Source: {h['title']}, {h['publisher']}, {h['year']}.)", None

        if p.intent == "action":
            if role not in ("owner", "technician"):
                return "Only the owner or a technician can create tasks. I can explain alerts and readings for you.", None
            title = (
                re.sub(
                    r"^(please\s+)?(create|add|make|schedule)\s+(a\s+)?(task|reminder)\s*(to|for)?\s*",
                    "",
                    p.extra["q"],
                    flags=re.I,
                )
                .strip()
                .rstrip("?.!")
                or "Check the basins"
            )
            title = re.sub(r"\s+(tomorrow|today|tonight|demain)\s*$", "", title, flags=re.I)
            title = title[0].upper() + title[1:]
            due = (
                "Tomorrow"
                if re.search(r"tomorrow|demain", p.extra["q"], re.I)
                else "Tonight"
                if re.search(r"tonight|ce soir", p.extra["q"], re.I)
                else "Today"
            )
            return "I prepared this task. It will only be created after you approve it below.", {
                "title": title[:200],
                "basin_id": p.basin,
                "due": due,
            }

        return t("refusal", L), None
