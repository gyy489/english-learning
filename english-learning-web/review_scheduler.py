"""Document-backed spaced-review scheduling for the English learning app."""

from __future__ import annotations

from copy import deepcopy
from datetime import date


REVIEW_INTERVALS = (1, 3, 7, 14, 30, 60)
MAX_ARTICLE_TARGETS = 15
ACTIVE_POOL_LIMIT = 60
MAINTENANCE_POOL_LIMIT = 120
INBOX_LIMIT = 120
URGENT_DAILY_LIMIT = 10
MAINTENANCE_DAILY_LIMIT = 2
NEW_ACTIVATION_LIMIT = 2


def empty_history() -> dict[str, object]:
    return {
        "version": 2,
        "strategy": {
            "intervals": list(REVIEW_INTERVALS),
            "maxArticleTargets": MAX_ARTICLE_TARGETS,
            "activePoolLimit": ACTIVE_POOL_LIMIT,
            "maintenancePoolLimit": MAINTENANCE_POOL_LIMIT,
            "inboxLimit": INBOX_LIMIT,
            "urgentDailyLimit": URGENT_DAILY_LIMIT,
            "maintenanceDailyLimit": MAINTENANCE_DAILY_LIMIT,
            "newActivationLimit": NEW_ACTIVATION_LIMIT,
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
    if int(entry.get("longIntervalSuccessCount", 0)) >= 1:
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
        "activationDay": None,
        "nextReviewDay": day + REVIEW_INTERVALS[0],
        "intervalIndex": 0,
        "reviewCount": 0,
        "successCount": 0,
        "successStreak": 0,
        "longIntervalSuccessCount": 0,
        "lapseCount": 0,
        "status": "learning",
        "pool": "inbox",
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
    previous_interval_index = int(entry.get("intervalIndex", 0))
    if previous_interval_index >= len(REVIEW_INTERVALS) - 1:
        entry["longIntervalSuccessCount"] = int(
            entry.get("longIntervalSuccessCount", 0)
        ) + 1
    interval_index = min(
        previous_interval_index + 1,
        len(REVIEW_INTERVALS) - 1,
    )
    entry["intervalIndex"] = interval_index
    entry["lastReviewedDay"] = day
    entry["nextReviewDay"] = day + REVIEW_INTERVALS[interval_index]
    entry["status"] = status_for(entry)


def record_failure(entry: dict[str, object], day: int) -> None:
    entry["reviewCount"] = int(entry.get("reviewCount", 0)) + 1
    entry["successStreak"] = 0
    entry["longIntervalSuccessCount"] = 0
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
        if entry.get("activationDay") is None:
            entry["activationDay"] = day
        record_success(entry, day)
    for word in forgotten:
        entry = ensure_word(words, word, day, str(meanings.get(word, "")))
        if entry.get("activationDay") is None:
            entry["activationDay"] = day
        record_failure(entry, day)
    for word in incidental:
        entry = ensure_word(words, word, day, str(meanings.get(word, "")))
        if word in previously_known:
            if entry.get("activationDay") is None:
                entry["activationDay"] = day
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


def assign_pools(
    history: dict[str, object],
    current_marked: list[object] | None = None,
) -> dict[str, int]:
    """Assign bounded scheduling pools without deleting any vocabulary."""
    words = history["words"]
    assert isinstance(words, dict)
    marked = set(unique_words(current_marked or []))
    active_candidates: list[dict[str, object]] = []
    maintenance_candidates: list[dict[str, object]] = []
    inbox_candidates: list[dict[str, object]] = []
    archived: list[dict[str, object]] = []

    for entry in words.values():
        entry.pop("poolReason", None)
        status = str(entry.get("status", "learning"))
        if status == "mastered":
            archived.append(entry)
        elif status == "familiar":
            maintenance_candidates.append(entry)
        elif entry.get("activationDay") is not None:
            active_candidates.append(entry)
        else:
            inbox_candidates.append(entry)

    active_candidates.sort(
        key=lambda entry: (
            0 if str(entry.get("word", "")) in marked else 1,
            int(entry.get("nextReviewDay", 0)),
            -int(entry.get("lapseCount", 0)),
            int(entry.get("activationDay") or 0),
            str(entry.get("word", "")),
        )
    )
    active = active_candidates[:ACTIVE_POOL_LIMIT]
    active_overflow = active_candidates[ACTIVE_POOL_LIMIT:]
    for entry in active:
        entry["pool"] = "active"

    maintenance_candidates.sort(
        key=lambda entry: (
            int(entry.get("nextReviewDay", 0)),
            -int(entry.get("lapseCount", 0)),
            str(entry.get("word", "")),
        )
    )
    maintenance = maintenance_candidates[:MAINTENANCE_POOL_LIMIT]
    maintenance_overflow = maintenance_candidates[MAINTENANCE_POOL_LIMIT:]
    for entry in maintenance:
        entry["pool"] = "maintenance"

    for entry in active_overflow:
        entry["poolReason"] = "active_pool_overflow"
    inbox_candidates.extend(active_overflow)
    inbox_candidates.sort(
        key=lambda entry: (
            0 if entry.get("activationDay") is not None else 1,
            int(entry.get("nextReviewDay", 0)),
            int(entry.get("firstSeenDay", 0)),
            str(entry.get("word", "")),
        )
    )
    inbox = inbox_candidates[:INBOX_LIMIT]
    inbox_overflow = inbox_candidates[INBOX_LIMIT:]
    for entry in inbox:
        entry["pool"] = "inbox"

    for entry in archived:
        entry["pool"] = "archive"
        entry["poolReason"] = "mastered"
    for entry in maintenance_overflow:
        entry["pool"] = "archive"
        entry["poolReason"] = "maintenance_pool_overflow"
    for entry in inbox_overflow:
        entry["pool"] = "archive"
        entry["poolReason"] = "inbox_pool_overflow"

    return {
        "active": len(active),
        "maintenance": len(maintenance),
        "inbox": len(inbox),
        "archive": len(archived) + len(maintenance_overflow) + len(inbox_overflow),
    }


def pool_due_words(history: dict[str, object], day: int, pool: str) -> list[str]:
    words = history["words"]
    assert isinstance(words, dict)
    candidates = [
        entry
        for entry in words.values()
        if entry.get("pool") == pool
        and int(entry.get("nextReviewDay", day + 1)) <= day
    ]
    candidates.sort(
        key=lambda entry: (
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
    *,
    new_words: list[object] | None = None,
    urgent_words: list[object] | None = None,
) -> dict[str, object]:
    all_recent = unique_words(marked_words)
    words = projected_history["words"]
    assert isinstance(words, dict)
    for word in all_recent:
        ensure_word(words, word, next_day - 1)

    pools = assign_pools(projected_history, all_recent)
    current_new = unique_words(new_words or [])
    if new_words is None:
        current_new = [
            word
            for word in all_recent
            if words.get(word, {}).get("activationDay") is None
        ]
    current_urgent = unique_words(urgent_words or [])
    if urgent_words is None:
        current_urgent = [word for word in all_recent if word not in set(current_new)]

    active_due = pool_due_words(projected_history, next_day, "active")
    maintenance_due = pool_due_words(projected_history, next_day, "maintenance")
    due_set = set(active_due + maintenance_due)
    current_urgent = [word for word in current_urgent if word in words]

    selected_urgent = current_urgent[:URGENT_DAILY_LIMIT]
    selected: list[str] = list(selected_urgent)
    selected_set = set(selected)

    maintenance_candidates = [
        word for word in maintenance_due if word not in selected_set
    ]
    selected_maintenance = maintenance_candidates[
        : min(
            MAINTENANCE_DAILY_LIMIT,
            MAX_ARTICLE_TARGETS - len(selected),
        )
    ]
    selected.extend(selected_maintenance)
    selected_set.update(selected_maintenance)

    active_candidates = [word for word in active_due if word not in selected_set]
    selected_active = active_candidates[: MAX_ARTICLE_TARGETS - len(selected)]
    selected.extend(selected_active)
    selected_set.update(selected_active)

    total_due = len(due_set | set(current_urgent))
    selected_due_count = len(
        [word for word in selected if word in due_set or word in current_urgent]
    )
    deferred_due = max(0, total_due - selected_due_count)

    admitted: list[str] = []
    active_capacity = max(0, ACTIVE_POOL_LIMIT - pools["active"])
    if deferred_due == 0 and len(selected) < MAX_ARTICLE_TARGETS and active_capacity:
        inbox_entries = [
            entry
            for entry in words.values()
            if entry.get("pool") == "inbox" and entry.get("activationDay") is None
        ]
        current_new_set = set(current_new)
        inbox_entries.sort(
            key=lambda entry: (
                0 if str(entry.get("word", "")) in current_new_set else 1,
                int(entry.get("firstSeenDay", 0)),
                str(entry.get("word", "")),
            )
        )
        admission_limit = min(
            NEW_ACTIVATION_LIMIT,
            active_capacity,
            MAX_ARTICLE_TARGETS - len(selected),
        )
        admitted = [str(entry["word"]) for entry in inbox_entries[:admission_limit]]
        selected.extend(admitted)
        selected_set.update(admitted)

    recent = [word for word in selected if word in set(all_recent)]
    selected_due = [word for word in selected if word in due_set and word not in set(recent)]
    inbox_waiting = max(0, pools["inbox"] - len(admitted))
    new_word_allowance = 0
    if deferred_due == 0 and inbox_waiting == 0:
        new_word_allowance = min(
            NEW_ACTIVATION_LIMIT - len(admitted),
            active_capacity - len(admitted),
        )
    return {
        "recentWords": recent,
        "dueWords": selected_due,
        "urgentWords": selected_urgent,
        "activeDueWords": selected_active,
        "maintenanceWords": selected_maintenance,
        "admittedWords": admitted,
        "targetWords": selected,
        "deferredRecentCount": max(0, len(all_recent) - len(recent)),
        "deferredDueCount": deferred_due,
        "totalDueCount": total_due,
        "newWordAllowance": max(0, new_word_allowance),
        "poolCounts": pools,
        "inboxWaitingCount": inbox_waiting,
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
            "urgentWords": [],
            "activeDueWords": [],
            "maintenanceWords": [],
            "admittedWords": [],
            "targetWords": [],
            "deferredRecentCount": 0,
            "deferredDueCount": 0,
            "totalDueCount": 0,
            "newWordAllowance": NEW_ACTIVATION_LIMIT,
            "poolCounts": {"active": 0, "maintenance": 0, "inbox": 0, "archive": 0},
            "inboxWaitingCount": 0,
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
    plan = select_next_targets(
        projected,
        next_day,
        list(current.get("markedWords", [])),
        new_words=list(pending_session.get("newWords", [])),
        urgent_words=(
            list(pending_session.get("forgottenWords", []))
            + list(pending_session.get("resurfacedWords", []))
        ),
    )
    plan["currentDay"] = int(current["day"])
    plan["nextDay"] = next_day

    words = projected["words"]
    assert isinstance(words, dict)
    pool_counts = dict(plan.get("poolCounts", {}))
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
        "activePoolWords": int(pool_counts.get("active", 0)),
        "maintenancePoolWords": int(pool_counts.get("maintenance", 0)),
        "inboxWords": int(pool_counts.get("inbox", 0)),
        "archivedWords": int(pool_counts.get("archive", 0)),
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
        f"- 收件箱：{summary.get('inboxWords', 0)}/{INBOX_LIMIT}",
        f"- 活跃学习池：{summary.get('activePoolWords', 0)}/{ACTIVE_POOL_LIMIT}",
        f"- 长期维护池：{summary.get('maintenancePoolWords', 0)}/{MAINTENANCE_POOL_LIMIT}",
        f"- 归档：{summary.get('archivedWords', 0)}",
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
        f"- 仍不会、优先重学：{'、'.join(plan.get('urgentWords', [])) or '无'}",
        f"- 活跃池到期词：{'、'.join(plan.get('activeDueWords', [])) or '无'}",
        f"- 长期维护词：{'、'.join(plan.get('maintenanceWords', [])) or '无'}",
        f"- 从收件箱新激活：{'、'.join(plan.get('admittedWords', [])) or '无'}",
        f"- 目标词总数：{len(plan.get('targetWords', []))}/{plan.get('maxTargets', MAX_ARTICLE_TARGETS)}",
        f"- 顺延当前生词：{plan.get('deferredRecentCount', 0)} 个",
        f"- 顺延到期词：{plan.get('deferredDueCount', 0)} 个",
        f"- 收件箱等待：{plan.get('inboxWaitingCount', 0)} 个",
        f"- 允许文章额外引入新词：{plan.get('newWordAllowance', 0)} 个",
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
        "| 单词 | 中文 | 词池 | 状态 | 首次出现 | 上次复习 | 下次复习 | 成功/复习 | 遗忘 |",
        "|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    status_labels = {"learning": "学习中", "familiar": "基本熟悉", "mastered": "已掌握"}
    pool_labels = {"inbox": "收件箱", "active": "活跃", "maintenance": "维护", "archive": "归档"}
    entries = sorted(
        words.values(),
        key=lambda entry: (int(entry.get("nextReviewDay", 0)), str(entry.get("word", ""))),
    )
    for entry in entries:
        last_review = entry.get("lastReviewedDay") or "—"
        lines.append(
            "| {word} | {meaning} | {pool} | {status} | {first} | {last} | {next_day} | {success}/{reviews} | {lapses} |".format(
                word=entry.get("word", ""),
                meaning=str(entry.get("meaning", "")).replace("|", "/"),
                pool=pool_labels.get(str(entry.get("pool", "inbox")), "收件箱"),
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
