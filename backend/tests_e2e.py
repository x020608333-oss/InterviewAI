"""端到端冒烟测试：登录 → 创建面试 → 逐题作答（含追问）→ 提前结束 / 自然完场 → 报告。"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765/api"


def call(path, method="GET", body=None, token=None, expect_error=False):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    try:
        with urllib.request.urlopen(req, data) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        payload = json.loads(e.read().decode("utf-8"))
        if not expect_error:
            raise AssertionError(f"{method} {path} -> {e.code}: {payload}")
        return e.code, payload


GOOD_ANSWERS = {
    "GIL": "GIL 是 CPython 解释器里的全局互斥锁，保证同一时刻只有一个线程执行字节码。"
           "所以 CPU 密集型任务多线程无法真正并行，甚至因切换更慢；"
           "IO 密集型任务在等待时会释放锁，多线程仍然有效。",
    "GENERIC_GOOD": "这个问题我从概念、原理和实际场景三个层面回答："
                    "核心机制是把请求和数据按规则组织起来，先定位再处理，"
                    "同时要考虑并发下的正确性与性能权衡，实践中会结合监控持续优化。",
    "WEAK": "这个我不太确定，可能和锁有关系吧，具体的原理没有深入研究过。",
}


def print_report(tag, report):
    print(f"[{tag}] overall: {report['overall_score']} ({report['grade']})")
    print(f"[{tag}] skills:", [(s["skill"], s["score"]) for s in report["skill_scores"]])
    print(f"[{tag}] strengths:", report["strengths"][:2])
    print(f"[{tag}] weaknesses:", report["weaknesses"][:2])
    print(f"[{tag}] plan phases:", [p["phase"] for p in report["learning_plan"]])
    print(f"[{tag}] reviews:", len(report["question_reviews"]))


def main():
    print("== 1. health/meta ==")
    _, meta = call("/meta")
    print("mode:", meta["llm_mode"], "| model:", meta["model"], "| bank:", meta["bank_stats"])

    print("== 2. login demo ==")
    _, login = call("/auth/login", "POST", {"username": "demo", "password": "demo1234"})
    token = login["token"]

    print("== 3. register duplicate (expect 400) / wrong password (expect 400) ==")
    code, err = call("/auth/register", "POST", {"username": "demo", "password": "xxxxxx"}, expect_error=True)
    print("dup register:", code, err["detail"])
    code, err = call("/auth/login", "POST", {"username": "demo", "password": "wrong!"}, expect_error=True)
    print("bad login:", code, err["detail"])

    print("== 4. no token access (expect 401) ==")
    code, _ = call("/interviews", expect_error=True)
    print("no token:", code)

    # ---------- 面试 A：答 3 题后提前结束 ----------
    print("== 5. interview A: answer 3 turns then finish early ==")
    _, created = call("/interviews", "POST",
                      {"position": "Python 后端开发", "difficulty": "senior"}, token)
    iv_a = created["interview"]
    print("id:", iv_a["id"], "| qids:", [it["qid"] for it in iv_a["items"]])
    for i, ans in enumerate([GOOD_ANSWERS["GIL"], GOOD_ANSWERS["WEAK"], GOOD_ANSWERS["GENERIC_GOOD"]]):
        _, resp = call(f"/interviews/{iv_a['id']}/answer", "POST", {"content": ans}, token)
        ta = resp["turn_analysis"]
        print(f"  turn {i + 1}: score={ta['score']} level={ta['level']} next={resp['assistant_message']['meta']['kind']}")
    _, done_a = call(f"/interviews/{iv_a['id']}/finish", "POST", token=token)
    print_report("A", done_a["report"])
    _, again = call(f"/interviews/{iv_a['id']}/finish", "POST", token=token)
    assert again["report"]["overall_score"] == done_a["report"]["overall_score"], "报告不幂等!"
    print("[A] finish idempotent OK")

    # ---------- 面试 B：完整走完 7 题 ----------
    print("== 6. interview B: full loop to natural finish ==")
    _, created = call("/interviews", "POST",
                      {"position": "AI 算法工程师", "difficulty": "middle",
                       "jd": "负责大模型应用开发，要求熟悉 RAG、Agent、Prompt 工程，了解 Transformer 原理。"}, token)
    iv_b = created["interview"]
    print("id:", iv_b["id"], "| skills:", iv_b["skills"], "| planner:", iv_b["planner_mode"])
    print("qids:", [it["qid"] for it in iv_b["items"]])
    script = [
        GOOD_ANSWERS["GENERIC_GOOD"], GOOD_ANSWERS["WEAK"], GOOD_ANSWERS["WEAK"],
        GOOD_ANSWERS["GIL"], GOOD_ANSWERS["GENERIC_GOOD"], GOOD_ANSWERS["WEAK"],
        GOOD_ANSWERS["GENERIC_GOOD"], GOOD_ANSWERS["GENERIC_GOOD"], GOOD_ANSWERS["WEAK"],
        GOOD_ANSWERS["GENERIC_GOOD"], GOOD_ANSWERS["GENERIC_GOOD"], GOOD_ANSWERS["WEAK"],
        GOOD_ANSWERS["GENERIC_GOOD"], GOOD_ANSWERS["GENERIC_GOOD"], GOOD_ANSWERS["GENERIC_GOOD"],
        GOOD_ANSWERS["WEAK"], GOOD_ANSWERS["GENERIC_GOOD"], GOOD_ANSWERS["GENERIC_GOOD"],
        GOOD_ANSWERS["GENERIC_GOOD"], GOOD_ANSWERS["WEAK"], GOOD_ANSWERS["GENERIC_GOOD"],
        GOOD_ANSWERS["GENERIC_GOOD"], GOOD_ANSWERS["GENERIC_GOOD"], GOOD_ANSWERS["GENERIC_GOOD"],
    ]
    finished_naturally = False
    followups_seen = 0
    for i, ans in enumerate(script):
        _, resp = call(f"/interviews/{iv_b['id']}/answer", "POST", {"content": ans}, token)
        meta = resp["assistant_message"]["meta"]
        if meta["kind"] == "follow_up":
            followups_seen += 1
        print(f"  turn {i + 1}: score={resp['turn_analysis']['score']} "
              f"level={resp['turn_analysis']['level']} next={meta['kind']} finished={resp['finished']}")
        if resp["finished"]:
            finished_naturally = True
            break
    assert finished_naturally, "面试未自然完场!"
    assert followups_seen > 0, "全程没有触发追问!"
    print(f"[B] 自然完场 OK，追问次数={followups_seen}")

    _, done_b = call(f"/interviews/{iv_b['id']}/finish", "POST", token=token)
    print_report("B", done_b["report"])
    assert 0 <= done_b["report"]["overall_score"] <= 100

    print("== 7. history + detail ==")
    _, history = call("/interviews", token=token)
    print("history count:", len(history["items"]))
    _, detail = call(f"/interviews/{iv_b['id']}", token=token)
    print("detail messages:", len(detail["messages"]), "| report in detail:", detail["report"] is not None)

    print("== 8. other user cannot access (expect 404) ==")
    call("/auth/register", "POST", {"username": "e2e_other", "password": "password1"}, expect_error=True)
    _, other = call("/auth/login", "POST", {"username": "e2e_other", "password": "password1"})
    code, _ = call(f"/interviews/{iv_b['id']}", token=other["token"], expect_error=True)
    print("cross-user:", code)

    print("\nALL E2E TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("FAILED:", exc, file=sys.stderr)
        sys.exit(1)
