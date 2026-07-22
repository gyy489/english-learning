"""Document-backed spaced-review scheduling for the English learning app."""

from __future__ import annotations

from copy import deepcopy
from datetime import date


REVIEW_INTERVALS = (1, 3, 7, 14, 30, 60)
MAX_ARTICLE_TARGETS = 15
LIGHT_DUE_LIMIT = 5
NORMAL_DUE_LIMIT = 4


def empty_history() -> dict[str, object]:
    return {
        "version": 1,
        "strategy": {
            "intervals": list(REVIEW_INTERVALS),
            "maxArticleTargets": MAX_ARTICLE_TARGETS,
            "lightDueLimit": LIGHT_DUE_LIMIT,
            "normalDueLimit": NORMAL_DUE_LIMIT,
        },
        "words": {},
        "sessions": [],
    }


def unique_words(items: list[object]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for item in items:
        word = str(item).strip().lower()
        if word and word != "无" and word not in seen:
            seen.add(word)
            found.append(word)
    return found


def status_for(entry: dict[str, object]) -> str:
    interval_index = int(entry.get("intervalIndex", 0))
    streak = int(entry.get("successStreak", 0))
    if interval_index >= len(REVIEW_INTERVALS) - 1 and streak >= 3:
        return "mastered"
    if interval_index >= 3 and streak >= 2:
        return "familiar"
    return "learning"


def make_word(word: str, day: int, meaning: str = "") -> dict[str, object]:
    return {
        "word": word,
        "meaning": meaning,
        "firstSeenDay": day,
        "lastSeenDay": day,
        "lastReviewedDay": None,
        "nextReviewDay": day + REVIEW_INTERVALS[0],
        "intervalIndex": 0,
        "reviewCount": 0,
        "successCount": 0,
        "successStreak": 0,
        "lapseCount": 0,
        "status": "learning",
    }


def ensure_word(
    words: dict[str, dict[str, object]],
    word: str,
    day: int,
    meaning: str = "",
) -> dict[str, object]:
    entry = words.get(word)
    if entry is None:
        entry = make_word(word, day, meaning)
        words[word] = entry
    elif meaning and not entry.get("meaning"):
        entry["meaning"] = meaning
    entry["lastSeenDay"] = day
    return entry


def record_success(entry: dict[str, object], day: int) -> None:
    entry["reviewCount"] = int(entry.get("reviewCount", 0)) + 1
    entry["successCount"] = int(entry.get("successCount", 0)) + 1
    entry["successStreak"] = int(entry.get("successStreak", 0)) + 1
    interval_index = min(
        int(entry.get("intervalIndex", 0)) + 1,
        len(REVIEW_INTERVALS) - 1,
    )
    entry["intervalIndex"] = interval_index
    entry["lastReviewedDay"] = day
    entry["nextReviewDay"] = day + REVIEW_INTERVALS[interval_index]
    entry["status"] = status_for(entry)


def record_failure(entry: dict[str, object], day: int) -> None:
    entry["reviewCount"] = int(entry.get("reviewCount", 0)) + 1
    entry["successStreak"] = 0
    entry["lapseCount"] = int(entry.get("lapseCount", 0)) + 1
    entry["intervalIndex"] = 0
    entry["lastReviewedDay"] = day
    entry["nextReviewDay"] = day + REVIEW_INTERVALS[0]
    entry["status"] = "learning"


def apply_session(
    history: dict[str, object],
    snapshot: dict[str, object],
    *,
    append_session: bool = True,
) -> dict[str, object]:
    day = int(snapshot["day"])
    review_words = unique_words(list(snapshot.get("reviewWords", [])))
    marked_words = unique_words(list(snapshot.get("markedWords", [])))
    meanings = dict(snapshot.get("meanings", {}))
    reviewed = set(review_words)
    marked = set(marked_words)
    remembered = [word for word in review_words if word not in marked]
    forgotten = [word for word in review_words if word in marked]
    incidental = [word for word in marked_words if word not in reviewed]

    words = history["words"]
    assert isinstance(words, dict)
    previously_known = set(words)

    for word in remembered:
        entry = ensure_word(words, word, day, str(meanings.get(word, "")))
        record_success(entry, day)
    for word in forgotten:
        entry = ensure_word(words, word, day, str(meanings.get(word, "")))
        record_failure(entry, day)
    for word in incidental:
        entry = ensure_word(words, word, day, str(meanings.get(word, "")))
        if word in previously_known:
            record_failure(entry, day)

    new_words = [word for word in marked_words if word not in previously_known]
    resurfaced = [word for word in incidental if word in previously_known]
    session = {
        "day": day,
        "reviewedWords": review_words,
        "rememberedWords": remembered,
        "forgottenWords": forgotten,
        "newWords": new_words,
        "resurfacedWords": resurfaced,
        "markedWords": marked_words,
    }
    if append_session:
        sessions = history["sessions"]
        assert isinstance(sessions, list)
        sessions.append(session)
    return session


def due_words(history: dict[str, object], day: int) -> list[str]:
    words = history["words"]
    assert isinstance(words, dict)
    candidates = [
        entry
        for entry in words.values()
        if int(entry.get("nextReviewDay", day + 1)) <= day
    ]
    candidates.sort(
        key=lambda entry: (
            -int(entry.get("lastSeenDay", 0)),
            int(entry.get("nextReviewDay", day)),
            -int(entry.get("lapseCount", 0)),
            int(entry.get("lastReviewedDay") or 0),
            str(entry.get("word", "")),
        )
    )
    return [str(entry["word"]) for entry in candidates]


def select_next_targets(
    projected_history: dict[str, object],
    next_day: int,
    marked_words: list[object],
) -> dict[str, object]:
    all_recent = unique_words(marked_words)
    recent = all_recent[:MAX_ARTICLE_TARGETS]
    recent_set = set(all_recent)
    all_due = [word for word in due_words(projected_history, next_day) if word not in recent_set]

    if len(recent) >= 11:
        due_limit = 0
    elif len(recent) >= 6:
        due_limit = NORMAL_DUE_LIMIT
    else:
        due_limit = LIGHT_DUE_LIMIT
    due_limit = min(due_limit, MAX_ARTICLE_TARGETS - len(recent))
    selected_due = all_due[:due_limit]
    targets = recent + selected_due
    return {
        "recentWords": recent,
        "dueWords": selected_due,
        "targetWords": targets,
        "deferredRecentCount": max(0, len(all_recent) - len(recent)),
        "deferredDueCount": max(0, len(all_due) - len(selected_due)),
        "totalDueCount": len(all_due),
        "maxTargets": MAX_ARTICLE_TARGETS,
    }


def build_review_state(
    snapshots: list[dict[str, object]],
) -> tuple[dict[str, object], dict[str, object]]:
    history = empty_history()
    if not snapshots:
        plan = {
            "currentDay": 0,
            "nextDay": 1,
            "recentWords": [],
            "dueWords": [],
            "targetWords": [],
            "deferredRecentCount": 0,
            "deferredDueCount": 0,
            "totalDueCount": 0,
            "maxTargets": MAX_ARTICLE_TARGETS,
        }
        return history, plan

    ordered = sorted(snapshots, key=lambda item: int(item["day"]))
    for index, snapshot in enumerate(ordered[:-1]):
        session = apply_session(history, snapshot)
        next_review_words = unique_words(list(ordered[index + 1].get("reviewWords", [])))
        session["scheduledForNext"] = next_review_words

    current = ordered[-1]
    projected = deepcopy(history)
    pending_session = apply_session(projected, current, append_session=False)
    next_day = int(current["day"]) + 1
    plan = select_next_targets(projected, next_day, list(current.get("markedWords", [])))
    plan["currentDay"] = int(current["day"])
    plan["nextDay"] = next_day

    words = projected["words"]
    assert isinstance(words, dict)
    status_counts = {"learning": 0, "familiar": 0, "mastered": 0}
    for entry in words.values():
        status = str(entry.get("status", "learning"))
        status_counts[status if status in status_counts else "learning"] += 1

    history["currentDay"] = int(current["day"])
    history["completedThroughDay"] = int(current["day"]) - 1
    history["generatedAt"] = date.today().isoformat()
    history["words"] = words
    history["pendingSession"] = pending_session
    history["nextPlan"] = plan
    sessions = history["sessions"]
    assert isinstance(sessions, list)
    review_attempts = sum(len(session.get("reviewedWords", [])) for session in sessions)
    remembered_total = sum(len(session.get("rememberedWords", [])) for session in sessions)
    marked_total = sum(len(session.get("markedWords", [])) for session in sessions)
    recent_sessions = sessions[-7:]
    recent_attempts = sum(
        len(session.get("reviewedWords", [])) for session in recent_sessions
    )
    recent_remembered = sum(
        len(session.get("rememberedWords", [])) for session in recent_sessions
    )
    history["habits"] = {
        "completedSessions": len(sessions),
        "totalReviewAttempts": review_attempts,
        "overallRecallRate": round(remembered_total * 100 / review_attempts)
        if review_attempts
        else 0,
        "recentWindow": len(recent_sessions),
        "recentRecallRate": round(recent_remembered * 100 / recent_attempts)
        if recent_attempts
        else 0,
        "averageMarkedWords": round(marked_total / len(sessions), 1)
        if sessions
        else 0,
    }
    history["summary"] = {
        "totalWords": len(words),
        "learningWords": status_counts["learning"],
        "familiarWords": status_counts["familiar"],
        "masteredWords": status_counts["mastered"],
        "currentMarkedWords": len(list(current.get("markedWords", []))),
        "dueForNextDay": int(plan["totalDueCount"]),
    }
    return history, plan


def render_markdown_report(history: dict[str, object]) -> str:
    summary = dict(history.get("summary", {}))
    habits = dict(history.get("habits", {}))
    plan = dict(history.get("nextPlan", {}))
    pending = dict(history.get("pendingSession", {}))
    words = history.get("words", {})
    sessions = history.get("sessions", [])
    assert isinstance(words, dict)
    assert isinstance(sessions, list)

    lines = [
        "# 单词复习记录",
        "",
        "> 本文件由 Web App 根据每日 Markdown 自动生成；请在每日文章的 `生单词:` 区域记录不会的词。",
        "",
        "## 当前概览",
        "",
        f"- 当前天数：第 {history.get('currentDay', 0)} 天",
        f"- 词库总数：{summary.get('totalWords', 0)}",
        f"- 学习中：{summary.get('learningWords', 0)}",
        f"- 基本熟悉：{summary.get('familiarWords', 0)}",
        f"- 已掌握：{summary.get('masteredWords', 0)}",
        f"- 当前标记生词：{summary.get('currentMarkedWords', 0)}",
        "",
        "## 复习习惯",
        "",
        f"- 已完成学习篇数：{habits.get('completedSessions', 0)}",
        f"- 累计复习词次数：{habits.get('totalReviewAttempts', 0)}",
        f"- 累计回忆成功率：{habits.get('overallRecallRate', 0)}%",
        f"- 最近 {habits.get('recentWindow', 0)} 篇回忆成功率：{habits.get('recentRecallRate', 0)}%",
        f"- 平均每篇标记生词：{habits.get('averageMarkedWords', 0)} 个",
        "",
        f"## 第 {plan.get('nextDay', 1)} 天生成计划",
        "",
        f"- 当前生词优先：{'、'.join(plan.get('recentWords', [])) or '无'}",
        f"- 到期旧词补充：{'、'.join(plan.get('dueWords', [])) or '无'}",
        f"- 目标词总数：{len(plan.get('targetWords', []))}/{plan.get('maxTargets', MAX_ARTICLE_TARGETS)}",
        f"- 顺延当前生词：{plan.get('deferredRecentCount', 0)} 个",
        f"- 顺延到期词：{plan.get('deferredDueCount', 0)} 个",
        "",
        "## 当前文章学习结果（待生成下一天时确认）",
        "",
        f"- 记住：{'、'.join(pending.get('rememberedWords', [])) or '无'}",
        f"- 仍不会：{'、'.join(pending.get('forgottenWords', [])) or '无'}",
        f"- 新发现：{'、'.join(pending.get('newWords', [])) or '无'}",
        f"- 旧词再次遗忘：{'、'.join(pending.get('resurfacedWords', [])) or '无'}",
        "",
        "## 词库",
        "",
        "| 单词 | 中文 | 状态 | 首次出现 | 上次复习 | 下次复习 | 成功/复习 | 遗忘 |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    status_labels = {"learning": "学习中", "familiar": "基本熟悉", "mastered": "已掌握"}
    entries = sorted(
        words.values(),
        key=lambda entry: (int(entry.get("nextReviewDay", 0)), str(entry.get("word", ""))),
    )
    for entry in entries:
        last_review = entry.get("lastReviewedDay") or "—"
        lines.append(
            "| {word} | {meaning} | {status} | {first} | {last} | {next_day} | {success}/{reviews} | {lapses} |".format(
                word=entry.get("word", ""),
                meaning=str(entry.get("meaning", "")).replace("|", "/"),
                status=status_labels.get(str(entry.get("status", "learning")), "学习中"),
                first=entry.get("firstSeenDay", "—"),
                last=last_review,
                next_day=entry.get("nextReviewDay", "—"),
                success=entry.get("successCount", 0),
                reviews=entry.get("reviewCount", 0),
                lapses=entry.get("lapseCount", 0),
            )
        )

    lines.extend(["", "## 最近复习历史", ""])
    if not sessions:
        lines.append("暂无已完成记录。")
    for session in sessions[-10:][::-1]:
        lines.extend(
            [
                f"### 第 {session.get('day')} 天",
                "",
                f"- 记住：{'、'.join(session.get('rememberedWords', [])) or '无'}",
                f"- 仍不会：{'、'.join(session.get('forgottenWords', [])) or '无'}",
                f"- 新词：{'、'.join(session.get('newWords', [])) or '无'}",
                f"- 安排到下一篇：{'、'.join(session.get('scheduledForNext', [])) or '无'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def dashboard_payload(history: dict[str, object]) -> dict[str, object]:
    return {
        "currentDay": history.get("currentDay", 0),
        "summary": history.get("summary", {}),
        "habits": history.get("habits", {}),
        "nextPlan": history.get("nextPlan", {}),
        "pendingSession": history.get("pendingSession", {}),
    }
