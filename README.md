# freightrate 物流计费重与运价版本核验

3PL 结算组每天要把 3 家承运商的运单算成应收：先确认这一票该用哪一版运价，再算体积重与
计费重，最后把首重、续重、偏远、燃油、保价叠成账单。本项目把这套判定做成可复核的流水线，
每一步都留下行号与原因码。

## 能力

- 运单采信：编码回退链、重复表头、列数校验、尾行截断、全角与千分位、单位换算、时区归一
- 运价版本：生效区间半开择版、区间重叠检测、陈旧运价集拒绝
- 质量隔离：原因码分级、隔离区证据行、可导出 CSV
- 计费重：体积重按服务除数、取实重与体积重的较大值、按 0.5 kg 台阶向上进位
- 分区附加：首重价 + 续重单价 × 段数、最低收费兜底、偏远固定额、燃油百分比、保价费率
- 账单对账：运单行账、金额账、版本账、计费重账四账相等
- 导出：账单 CSV、证据 CSV、运行清单 JSON（含 run_id 与输入 sha256）

## 模块

| 模块 | 动作 | 入口 |
|---|---|---|
| M1 运单采信 | 导入脏运单，逐行诊断 | `POST /api/waybills/import` |
| M2 运价版本 | 看版本窗口，校验运价文件 | `GET /api/rates` `POST /api/rates/audit` |
| M3 质量隔离 | 原因码分布与证据导出 | `GET /api/quarantine` `GET /api/quarantine.csv` |
| M4 计费重 | 体积重与进位 | `POST /api/weights` |
| M5 分区附加 | 分区价与附加费叠算 | `POST /api/charges` |
| M6 账单对账 | 四账核对 | `GET /api/reconcile` |
| M7 导出 | 账单、证据、清单 | `GET /api/export/invoice.csv` |

## 核心规则

1. 择版：取 `pickup_date` 归一后的 UTC 时刻，落在 `[effective_from, effective_to)` 的那一版；
   命中 0 版记 RATE_MISSING，命中 2 版及以上记 RATE_OVERLAP 并拒绝计费。
2. 计费重：`max(实重, 长×宽×高 / volume_divisor)`，再按 `step_weight_kg`（0.5 kg）向上取整。
3. 分区价：`首重价 + 续重单价 × 段数`，段数 = `ceil((计费重 - 首重) / 续重台阶)`。
4. 兜底：分区价低于 `min_charge` 时补差额到首重项。
5. 附加：偏远固定额，燃油 = `(基础 + 续重) × fuel_pct`，保价 = `声明价值 × insurance_pct`。
6. 应收：五个分项之和，先各自量化到分再相加，合计必然等于分项之和。

## 定义与已知不覆盖

单位表、量化刻度、半开区间、去重键、空态与原因码见 `docs/DATA-DICTIONARY.md`；
陷阱登记与对账规则见 `docs/DEPTH.md`；不覆盖多币种换算、一票多分区、承运商账单二次导入。

## 启动

```bash
docker compose up -d --build
# 页面 http://127.0.0.1:18209/
# 接口文档 http://127.0.0.1:18209/docs
```

样例数据随仓库自带，启动后首页直接可看运价手册，运单页可一键重跑主流程。

## 演示步骤

1. 首页看运价集 v3 的 38 行版本窗口，点「校验」用 `rate_cards_overlap.csv` 看到重叠被拒
2. 运单页点「导入」，得到 27 条记录、15 票计费、12 行隔离与原因码分布
3. 计费重页点「计算」，看 9 票体积重择用、6 票实重择用
4. 分区附加页点「计算」，看五个分项与应收 1521.04 元
5. 账单对账页看四账相等
6. 导出页取账单 CSV、证据 CSV 与运行清单

## 目录

```text
app/main.py config.py errors.py reasons.py manifest.py store.py web.py
app/modules/m1_waybill … m7_export   每个模块 handler + service + 2-3 个规则文件
app/templates   base + 6 页
app/static      theme/layout/components + 3 个 js
docs/           DEPTH.md DATA-DICTIONARY.md RUNBOOK.md
sample_data/    rate_cards.csv（干净）与 4 份脏运单
tests/          每模块一个测试文件 + e2e + 不变量
```

## 测试

```bash
docker compose exec -T app python -m pytest -q
```
