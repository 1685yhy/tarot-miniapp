# QA Round 1 — 接口回归验证

**日期**: 2026-07-11  
**服务器**: http://localhost:8000  
**验证目标**: 本轮修复后关键端点是否正常

---

## 测试结果汇总

| # | 端点 | 方法 | HTTP 状态 | 结论 |
|---|------|------|-----------|------|
| 1 | `/cards` | GET | 200 | PASS |
| 2 | `/cards/daily` | GET | 200 | PASS |
| 3 | `/readings/spread/three_card` | POST | **500** | **FAIL** |
| 4 | `/readings/history` | GET | 200 | PASS |
| 5 | `/diary/entries` | POST | 200 | PASS |

**结果**: 4/5 PASS, **1 FAIL**

---

## 失败详情

### POST /readings/spread/three_card — HTTP 500

**错误类型**: `TypeError`

**错误位置**: `backend/app/api/readings.py`, line 58, `_reset_daily_count_if_new_day`

**错误信息**:
```
TypeError: can't compare offset-naive and offset-aware datetimes
```

**根因**: 函数 `_reset_daily_count_if_new_day` 在第 58 行将 `last`（从数据库读取的 offset-naive datetime）与 `_today()`（offset-aware datetime）直接比较，Python 禁止这种比较。

**修复建议**: 在 `readings.py` 的 `_today()` 函数中，将 `datetime.now(tz=timezone.utc)` 改为 `datetime.now(timezone.utc).replace(tzinfo=None)`，或在比较前对 `_today()` 调用 `.replace(tzinfo=None)` 使其变为 naive datetime。

---

## 补充

- 认证接口 `/auth/dev-login` 正常工作，返回有效 token
- 所有通过测试的端点均返回预期的 JSON 结构，无数据异常
