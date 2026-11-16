"""Conformance 测试：读取契约仓的 fixtures，验证 Python SDK 行为与 Go 一致。

运行：python3 -m pytest tests/ -v  或在仓库根跑 python3 tests/test_conformance.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from weixun import APIError, Envelope, SendTextRequest, Client  # noqa: E402
from weixun.message import parse_batch_results  # noqa: E402
from weixun.stream import parse_add_msg  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "conformance" / "fixtures"
if not FIXTURES.exists():
    FIXTURES = Path(__file__).resolve().parents[2] / "weixun-api-contract" / "fixtures"


def load(rel: str) -> dict:
    with open(FIXTURES / rel, encoding="utf-8") as fh:
        return json.load(fh)


# ── envelope ────────────────────────────────────────


def test_envelope_ok():
    fx = load("envelope/01-ok.json")
    env = Envelope.parse(fx["input"])
    assert env.ok() is fx["expect"]["ok"]
    assert env.code() == fx["expect"]["code"]


def test_envelope_code_string():
    fx = load("envelope/02-code-string.json")
    env = Envelope.parse(fx["input"])
    assert env.ok() is True
    assert env.code() == 200


def test_envelope_success_false_code_200():
    """关键反例：Code=200 但 Success 缺失/false，仍应判成功。"""
    fx = load("envelope/03-success-false-code-200.json")
    env = Envelope.parse(fx["input"])
    assert env.ok() is fx["expect"]["ok"]
    assert env.code() == 200


def test_envelope_verify_code():
    fx = load("envelope/04-verify-code.json")
    env = Envelope.parse(fx["input"])
    assert env.ok() is True
    assert env.code() == 0
    assert env.message_text() == "验证成功"


def test_envelope_error_negative():
    fx = load("envelope/05-error-negative.json")
    env = Envelope.parse(fx["input"])
    assert env.ok() is False
    assert env.code() == -2
    assert env.message_text() == fx["expect"]["message_text"].strip()


def test_envelope_reason_code():
    fx = load("envelope/06-reason-code.json")
    env = Envelope.parse(fx["input"])
    assert env.ok() is False
    assert env.reason_code == "PROXY_OFFLINE"


# ── message ─────────────────────────────────────────


def test_batch_partial_success():
    fx = load("message/01-partial-success.json")
    results = parse_batch_results(fx["input"])
    assert len(results) == fx["expect"]["count"]
    for got, want in zip(results, fx["expect"]["items"]):
        assert got.to == want["to"], f"to 不匹配: {got.to} != {want['to']}"
        assert got.ok is want["ok"], f"ok 不匹配 for {got.to}"
        assert got.error_message == want["error"]


def test_errmgs_typo():
    fx = load("message/02-errmgs-typo.json")
    results = parse_batch_results(fx["input"])
    assert len(results) == 1
    assert results[0].ok is False
    assert results[0].error_message == "上传失败"


def test_single_object_result():
    fx = load("message/03-single-object.json")
    results = parse_batch_results(fx["input"])
    assert len(results) == 1
    assert results[0].to == "wxid_a"
    assert results[0].ok is True


# ── ws ──────────────────────────────────────────────


def test_ws_message_frame():
    fx = load("ws/01-message-frame.json")
    msg = parse_add_msg(fx["input"]["message"])
    assert msg is not None
    assert msg.from_user == fx["expect"]["from"]
    assert msg.to_user == fx["expect"]["to"]
    assert msg.msg_type == fx["expect"]["type"]
    assert msg.is_group == fx["expect"]["is_group"]
    assert msg.new_msg_id == fx["expect"]["new_msg_id"], "64 位 ID 丢精度"
    assert msg.msg_id == fx["expect"]["msg_id"]


def test_ws_bare_string_field():
    fx = load("ws/04-bare-string-field.json")
    msg = parse_add_msg(fx["input"]["message"])
    assert msg is not None
    assert msg.push_content == "裸字符串内容"
    assert msg.msg_type == 10000


# ── login ───────────────────────────────────────────


def test_login_state_machine():
    fx = load("login/01-state-machine.json")
    from weixun.login import LoginState

    for case in fx["cases"]:
        st = LoginState.parse({"loginState": case["loginState"]})
        assert st.is_online is case["online"], f"{case['loginState']} is_online"
        assert st.is_terminal is case["terminal"], f"{case['loginState']} is_terminal"


# ── 客户端行为 ──────────────────────────────────────


def test_key_in_query():
    """license key 必须走 query 参数（协议端唯一鉴权方式）。"""
    c = Client("http://127.0.0.1:7006", "abcdefgh12345678", None)
    assert c.key_masked == "abcd****5678", c.key_masked


def test_error_mapping():
    env = Envelope.parse({"Code": -2, "Text": "该链接不存在", "Success": False})
    from weixun.envelope import error_from_envelope

    err = error_from_envelope(env, 200, b"")
    assert isinstance(err, APIError)
    assert err.is_key_invalid() is True


if __name__ == "__main__":
    # 不依赖 pytest 也能跑
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ✅ {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  ❌ {name}: {exc}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"  ❌ {name}: {type(exc).__name__}: {exc}")
    print(f"\n{'全部通过' if failures == 0 else f'{failures} 个失败'}")
    sys.exit(1 if failures else 0)
