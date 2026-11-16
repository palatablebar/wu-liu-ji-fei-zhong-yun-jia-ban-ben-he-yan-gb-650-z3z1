# 运行手册 freightrate

## 启动

```bash
docker compose config --quiet
docker compose up -d --build
curl -s http://127.0.0.1:18209/api/health
```

宿主机端口 18209 映射容器 8000。SQLite 落在命名卷 `freightrate-data` 的 `/app/data/freightrate.db`。

## 启动后自动完成的事

1. 建表
2. 装载 `sample_data/rate_cards.csv`（运价集 v3，38 行）
3. 装载 `sample_data/rebate_tiers.csv`（返利档位，10 行）
4. 采信 `sample_data/waybills_dirty.csv`
5. 计算计费重与账单

页面首次打开即可看到 27 条运单、15 票计费、12 行隔离、应收 1521.04 元。
返利不自动计提，在月度返利页或接口显式重算，月账核对通过后逐月发布。

## 手工重跑

```bash
curl -s -X POST http://127.0.0.1:18209/api/waybills/import -F sample=waybills_dirty.csv
curl -s -X POST http://127.0.0.1:18209/api/weights
curl -s -X POST http://127.0.0.1:18209/api/charges
curl -s http://127.0.0.1:18209/api/reconcile
```

同一份输入重复导入命中同一个 run_id，行数与合计不变。

## 月度返利流程（整月补差）

```bash
# 1. 按整月重算（原运费不动，返利写独立调整行；可随时重复，先删后插）
curl -s -X POST http://127.0.0.1:18209/api/rebates/compute
# 2. 月账核对：逐月四查（分摊守恒/基数闭合/费率复算/权重和为 1）
curl -s http://127.0.0.1:18209/api/rebates/reconcile
# 3. 核对通过才发布；不平返回 409 REBATE_RECONCILE_FAILED
curl -s -X POST "http://127.0.0.1:18209/api/rebates/publish?carrier=SF&month=2026-04"
# 4. 发布后该月锁定，重算返回 409 REBATE_PUBLISHED_LOCKED；需改数先撤回
curl -s -X POST "http://127.0.0.1:18209/api/rebates/revoke?carrier=SF&month=2026-04"
# 5. 导出返利分摊 CSV（月度汇总行 + 逐票分摊行）
curl -s http://127.0.0.1:18209/api/export/rebate.csv
```

样例结果：原应收 1521.04 元，返利合计 50.22 元（SF 4 月 36.56、JD 4 月 12.58、SF 3 月 1.08），
月账净值 1470.82 元。前半月已出账运单在月末越档后同样拿到补差，但原账单金额不变。

## 运价文件校验

```bash
curl -s -X POST http://127.0.0.1:18209/api/rates/audit -F sample=rate_cards_overlap.csv
```

返回重叠清单；`/api/rates/import` 在校验不通过时返回 409，不会替换现有运价。

## 重建数据库

```bash
docker compose down -v --remove-orphans
docker compose up -d --build
```

## 测试

```bash
docker compose exec -T app python -m pytest -q
```

## 常见失败

| 现象 | 原因 | 处理 |
|---|---|---|
| 页面 500，提示 RATE_MISSING | 采信时运价表还没装载 | 先打开运价手册页确认 38 行版本窗口 |
| /api/charges 返回 409 NO_WEIGHTS | 还没算计费重 | 先调 /api/weights |
| 导入后 rows_ok 为 0 | 全部行都被隔离 | 到运单页看原因码分布 |
| 运价装载 409 RATE_STALE | 提交的运价集版本低于现有 | 提高 CSV 里的 rate_set_version |
| 返利重算 409 REBATE_PUBLISHED_LOCKED | 该月返利已发布锁定 | 先 /api/rebates/revoke 撤回再重算 |
| 返利发布 409 REBATE_RECONCILE_FAILED | 月账四查有不平项 | 看 /api/rebates/reconcile 的 broken 字段定位 |
| 返利装载 422 REBATE_TIER_INVALID | 档位断档、费率回退或月份非法 | 按返回的前 5 条问题修正 rebate_tiers.csv |
