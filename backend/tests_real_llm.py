"""真实大模型模式的全链路验证：LLM 出题规划 + LLM 分析追问 + LLM 报告。"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765/api"


def call(path, method="GET", body=None, token=None, timeout=180):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    try:
        with urllib.request.urlopen(req, data, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} on {method} {path}: {e.read().decode('utf-8')[:300]}")
        raise


def main():
    login = call("/auth/login", "POST", {"username": "demo", "password": "demo1234"})
    token = login["token"]

    print("== 1. 创建面试（规划官走 LLM 技能提取 + RAG 出题）==")
    iv = call("/interviews", "POST",
              {"position": "Python 后端开发", "difficulty": "middle"}, token)
    interview = iv["interview"]
    print("id:", interview["id"], "| planner_mode:", interview["planner_mode"],
          "| skills:", interview["skills"])
    print("qids:", [it["qid"] for it in interview["items"]])
    opening = [m for m in iv["messages"] if m["role"] == "assistant"][0]
    print("opening:", opening["content"][:80].replace("\n", " "))

    print("\n== 2. 回答 GIL（面试官走 LLM 分析 + 决策）==")
    resp = call(f"/interviews/{interview['id']}/answer", "POST", {"content":
        "GIL 就是 Python 里的全局解释器锁，是 CPython 的东西。它的作用是保证同一时刻"
        "只有一个线程在执行字节码，所以在多核 CPU 上多线程并不能并行计算，CPU 密集型"
        "任务用多线程反而可能更慢。不过做 IO 的时候锁会释放，所以 IO 密集型场景多线程还是有效的。"
    }, token)
    ta = resp["turn_analysis"]
    print("engine:", resp["user_message"]["meta"]["analysis"].get("engine"))
    print(f"score: {ta['score']} | level: {ta['level']}")
    print("comment:", ta["comment"])
    print("strengths:", ta["strengths"])
    print("gaps:", ta["gaps"])
    kind = resp["assistant_message"]["meta"]["kind"]
    print("decision ->", kind, ":", resp["assistant_message"]["content"][:120])

    if kind == "follow_up":
        print("\n== 3. 回答追问 ==")
        resp2 = call(f"/interviews/{interview['id']}/answer", "POST", {"content":
            "多进程环境下 GIL 基本不影响并发性能。因为每个进程都有独立的解释器实例和"
            "各自的 GIL，进程之间互不干扰，multiprocessing 可以真正利用多核并行计算。"
            "代价是进程启动慢、内存占用高、进程间通信需要序列化。"
        }, token)
        ta2 = resp2["turn_analysis"]
        print(f"score: {ta2['score']} | level: {ta2['level']} | next: "
              f"{resp2['assistant_message']['meta']['kind']}")

    print("\n== 4. 生成报告（评估官走 LLM 结构化输出）==")
    report = call(f"/interviews/{interview['id']}/finish", "POST", None, token)["report"]
    print("overall:", report["overall_score"], f"({report['grade']})")
    print("summary:", report["summary"])
    print("skills:", [(s["skill"], s["score"]) for s in report["skill_scores"]])
    print("strengths:", report["strengths"][:2])
    print("weaknesses:", report["weaknesses"][:2])
    print("plan:", [(p["phase"], p["goal"][:30]) for p in report["learning_plan"]])
    print("reviews:", len(report["question_reviews"]))
    print("\nREAL-LLM E2E PASSED")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("FAILED:", exc, file=sys.stderr)
        sys.exit(1)
