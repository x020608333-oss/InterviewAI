"""题库管理功能测试：管理员权限 + 增删改查 + RAG 索引热更新。可重复运行。"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765/api"
BANK_DIR = os.path.join("data", "question_banks")

NEW_Q = {
    "skill": "Go",
    "difficulty": "medium",
    "question": "请介绍 Go 语言的 goroutine 和 channel，以及它们如何组成并发模型。",
    "key_points": ["goroutine 是轻量级协程，由 Go 运行时调度", "channel 是协程间通信管道，提倡用通信共享内存", "select 多路复用与缓冲通道"],
    "reference_answer": "goroutine 是 Go 运行时调度的轻量级协程，初始栈很小可大量创建；channel 是类型化的通信管道，配合 select 实现协程同步与数据传递，体现\"用通信共享内存\"的并发哲学。",
    "follow_ups": ["goroutine 泄漏如何排查与避免？", "无缓冲和有缓冲 channel 的语义差异？"],
}


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


def main():
    print("== 1. admin / demo 登录 ==")
    _, admin = call("/auth/login", "POST", {"username": "admin", "password": "admin1234"})
    print("admin user:", admin["user"])
    assert admin["user"]["is_admin"] is True
    _, demo = call("/auth/login", "POST", {"username": "demo", "password": "demo1234"})
    assert demo["user"]["is_admin"] is False
    at, dt = admin["token"], demo["token"]

    print("== 0. 清理上次运行残留的 Go 题目 ==")
    _, listing = call("/admin/questions", token=at)
    for q in listing["items"]:
        if q["skill"] == "Go":
            call(f"/admin/questions/{q['id']}", "DELETE", None, at)
            print("removed leftover:", q["id"])
    if os.path.exists(os.path.join(BANK_DIR, "go.json")):
        remaining = json.loads(open(os.path.join(BANK_DIR, "go.json"), encoding="utf-8").read())
        if not remaining:
            os.remove(os.path.join(BANK_DIR, "go.json"))
            print("removed empty go.json")
    _, listing = call("/admin/questions", token=at)
    total_before = len(listing["items"])

    print("== 2. 非管理员访问（期望 403）==")
    code, err = call("/admin/questions", "POST", NEW_Q, dt, expect_error=True)
    print("demo create:", code, err["detail"])
    assert code == 403
    code, _ = call("/admin/questions", token=dt, expect_error=True)
    print("demo list:", code)
    assert code == 403

    print("== 3. 管理员列表 ==")
    _, listing = call("/admin/questions", token=at)
    print("total:", len(listing["items"]), "| skills:", listing["skills"])

    print("== 4. 新增题目（新技能 Go，应自动生成题库文件）==")
    _, created = call("/admin/questions", "POST", NEW_Q, at)
    q = created["question"]
    print("created:", q["id"], q["skill"], "| stats:", created["stats"])
    assert q["id"].startswith("GO"), f"新技能 ID 前缀异常: {q['id']}"
    go_file = os.path.join(BANK_DIR, "go.json")
    data = json.loads(open(go_file, encoding="utf-8").read())
    assert any(x["id"] == q["id"] for x in data), "go.json 未写入"
    print("go.json 写入 OK，文件内题目数:", len(data))

    print("== 5. 重复 ID（期望 400）==")
    code, err = call("/admin/questions", "POST", {**NEW_Q, "qid": q["id"]}, at, expect_error=True)
    print("dup qid:", code, err["detail"])
    assert code == 400

    print("== 6. 校验失败（空要点，期望 400）==")
    code, err = call("/admin/questions", "POST", {**NEW_Q, "key_points": ["  "], "qid": None}, at, expect_error=True)
    print("empty key_points:", code, err["detail"])
    assert code == 400

    print("== 7. 编辑题目（改难度 + 移动技能 Go -> Python）==")
    _, updated = call(f"/admin/questions/{q['id']}", "PUT", {
        **NEW_Q, "skill": "Python", "difficulty": "hard", "qid": None,
    }, at)
    uq = updated["question"]
    print("updated:", uq["id"], uq["skill"], uq["difficulty"])
    assert uq["skill"] == "Python" and uq["difficulty"] == "hard"
    go_data = json.loads(open(go_file, encoding="utf-8").read())
    assert not any(x["id"] == uq["id"] for x in go_data), "旧文件未移除"
    py_data = json.loads(open(os.path.join(BANK_DIR, "python.json"), encoding="utf-8").read())
    assert any(x["id"] == uq["id"] for x in py_data), "python.json 未写入"
    print("技能移动 OK：go.json 已移除该题，python.json 已写入")

    print("== 8. /api/meta 热更新检查 ==")
    _, meta = call("/meta")
    print("bank_stats:", meta["bank_stats"])
    assert meta["bank_stats"]["Python"] == 11, f"Python 题数应为 11，实际 {meta['bank_stats']['Python']}"

    print("== 9. 删除题目 ==")
    _, deleted = call(f"/admin/questions/{uq['id']}", "DELETE", None, at)
    print("deleted:", deleted["deleted"], "| stats:", deleted["stats"])
    assert deleted["stats"]["Python"] == 10
    _, listing2 = call("/admin/questions", token=at)
    assert len(listing2["items"]) == total_before, "列表数量未恢复"
    assert all(x["id"] != uq["id"] for x in listing2["items"])
    print("列表恢复原状 OK, total:", len(listing2["items"]))

    print("== 10. 删除不存在的题目（期望 404）==")
    code, err = call("/admin/questions/ZZ99", "DELETE", None, at, expect_error=True)
    print("delete missing:", code, err["detail"])
    assert code == 404

    if os.path.exists(go_file):
        remaining = json.loads(open(go_file, encoding="utf-8").read())
        if not remaining:
            os.remove(go_file)
    print("\nALL ADMIN TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("FAILED:", exc, file=sys.stderr)
        sys.exit(1)
