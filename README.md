# weixun-python

微寻微信协议 API 的 Python SDK。

覆盖 226 个客户可用接口，强类型、内置限速、大整数安全，配套 WebSocket 实时消息与扫码登录。

## 安装

pip install weixun

Python 3.8+，无必装依赖；实时消息需 `pip install "weixun[stream]"`（websocket-client）

## 快速开始

```python
from weixun import Client, SendTextRequest

c = Client("http://127.0.0.1:7006", "你的协议 license Key")

# 发一条文本消息
res = c.message.send_text(SendTextRequest(to="wxid_xxxxx", text="订单已发货"))
if not res.ok:
    print("发送失败:", res.error_message)

# 实时收消息
from weixun import Stream, StreamOptions

with Stream(c, StreamOptions(on_message=lambda m: print(m.from_user, m.content))) as s:
    s._thread.join()
```

## 核心设计

这个 SDK 不是简单的 HTTP 包装，它把 API 实际使用中容易踩的坑都处理掉了。

### 1. 成功判定不是看 HTTP 状态码

API 绝大多数情况都返回 HTTP 200，**成败在响应体的 `Code` 字段**。
而且 `Code` 可能是数字 `200`，也可能是字符串 `"200"`。

判定顺序：

1. `Code` 存在且为 `0` 或 `200` → 成功
2. `Code` 不存在 → 回退 `Success == true`
3. 都无法判定 → 失败

**关键反例**：`/user/SetProxy` 返回 `Code=200` 但 `Success` 缺失或为 `false`，
所以**不能**用 `Success == true` 作为主判据。

### 2. 64 位 ID 一律用字符串

`new_msg_id` 这类字段超过 2^53，JS 的 `JSON.parse` 会静默截断。
部分接口已做字符串化处理，其余仍是裸数字。

SDK 在契约层就把 23 个 64 位字段声明为 `string`。

### 3. 内置限速（服务端不限流）

服务端不对请求做频率限制：并发猛发不会收到错误码，而是直接承担微信侧的风控后果。

SDK 默认 40 条/分钟（官方风控建议）。关闭需显式配置，请自行承担风险。

### 4. 逐条结果字段不统一

批量发送接口返回数组，但：

- 接收方字段有两种拼写：`toUSerName`（14 处）与 `toUserName`（9 处）
- 成功标志有 7 种命名：`isSendSuccess` / `isCommentSuccess` / `isMarkSuccess` / …
- 错误信息有拼写错误：`errMgs`（UploadFriendCircleImage）

SDK 统一归一化为 `ok` / `to` / `errorMessage`。

### 5. 登录状态机

5 个状态（`waiting` / `login_processing` / `ipad_required` / `online` /
`security_verify_required`）+ 13 个 `reasonCode`。轮询节奏建议 2.5 秒（官方推荐）。

## 目录结构

```
weixun/
├── __init__.py    公共导出
├── client.py      Client + 统一调用出口
├── envelope.py    信封判定 + 错误映射
├── message.py     消息服务 + 逐条结果归一化
├── stream.py      WebSocket 流
├── login.py       扫码登录状态机
├── upload.py      multipart + base64
└── ratelimit.py   令牌桶
```

## 接口契约

`contract/weixun-api.json` 是本 SDK 覆盖的接口定义（OpenAPI 3.0），共 226 个端点。
已修正 64 位整数精度、空引用、非标准类型等问题。

接口若有版本更新，运行 `scripts/sync-contract.sh` 同步契约后重新生成模型即可。
`contract/CONTRACT_VERSION` 记录当前契约版本，便于追溯。


## 测试

```bash
python3 tests/test_conformance.py
```

测试读取 `conformance/fixtures/` 下的行为样本，七个语言跑同一套断言，
任何语言行为不一致都会被发现。

## 边界

- 本 SDK 是**非微信官方接口**的客户端，与腾讯无关
- 账号风控由使用者自行承担，建议先用测试 Key 验证
- 微寻只提供收发消息的通道，机器人逻辑与知识库都在调用方自己的程序里

## 许可证

MIT
