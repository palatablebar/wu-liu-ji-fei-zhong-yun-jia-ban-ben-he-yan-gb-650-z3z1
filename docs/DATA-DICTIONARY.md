# 定义契约 freightrate

## 数值

| 列 | 类型 | 量化 | 可空 | 说明 |
|---|---|---|---|---|
| weight_kg | Decimal | 0.001 kg | 否 | 实重，输入单位 g/kg/t 都换算到 kg |
| length_cm / width_cm / height_cm | Decimal | 0.001 cm | 否 | 尺寸，输入单位 cm/m/mm 都换算到 cm |
| volumetric_kg | Decimal | 0.001 kg | 否 | 长×宽×高 ÷ volume_divisor |
| billable_kg | Decimal | 0.5 kg 向上 | 否 | 取实重与体积重的较大值后按台阶进位 |
| first_price / step_price / min_charge | Decimal | 0.01 元 | 否 | 运价表金额 |
| fuel_pct / insurance_pct | Decimal | 小数 | 否 | 8.5% 与 0.085 两种写法都归到小数 |
| declared_value | Decimal | 0.01 元 | 是 | 空值与哨兵都按 0 处理，表示未保价 |
| total_amount | Decimal | 0.01 元 | 否 | 由分项求和得出，不单独舍入 |

金额与用量一律 Decimal，对外 JSON 用字符串。禁止 float 累加。

## 单位

单位表只在 `app/config.py` 定义一份。重量 g=0.001 kg、t=1000 kg；尺寸 m=100 cm、mm=0.1 cm。
带单位后缀的单元格（如 3200g）先剥后缀，单位列非空时以单位列为准。

## 时间

- 存储：UTC，ISO 文本，秒精度，带 Z 后缀
- 输入：接受 Z、+hh:mm、无偏移三种写法；无偏移按 +08:00 解释
- 展示：页面显示 Asia/Shanghai，生成时间与批次时间都带时区名
- 运价版本窗口：`effective_from` 与 `effective_to` 也是 UTC，区间半开 [from, to)

## 空值

- `null` / 空串 / 哨兵 三者语义分开
- 哨兵清单：`-`、`--`、`/`、`N/A`、`NA`、`NULL`、`NONE`、`未知`、`无`、`空`
- 重量与尺寸出现哨兵即进隔离区；声明价值出现哨兵按未保价处理

## 半开区间

运价版本用 `[effective_from, effective_to)`：提货时刻等于 from 命中该版，等于 to 落到下一版。
相邻版本首尾相接时不重不漏。

## 去重键

业务键是运单号 `waybill_no`。同一运单号第二次出现时比较载荷
（承运商、服务、分区、提货时刻、重量、三边尺寸、声明价值）：
载荷相同记 DUPLICATE_WAYBILL，不同记 DUP_CONFLICT，两种都只保留第一条参与计费。

## 空态

- 0 字节文件：拒绝采信，返回 EMPTY_FILE
- 只有表头：采信成功但 rows_in 为 0，页面显示空态
- 全是空行：empty_rows 计数，rows_in 为 0

## 原因码

原因码只在 `app/reasons.py` 定义，分两级：`block` 表示该行不进计费，`info` 表示只做标记。
每条隔离都带原始行号与原因码，可导出 CSV 复核。

## 月度返利（M8）

| 列 | 类型 | 量化 | 说明 |
|---|---|---|---|
| tier_from / tier_to | Decimal | 0.01 元 | 月累计基础运费的半开档区间 `[from, to)`，末档敞口到 9999999.99 |
| rebate_pct | Decimal | 小数四位 | 命中档费率，同承运商同月份必须单调不减 |
| base_total | Decimal | 0.01 元 | 自然月内该承运商全部计费运单的基础运费 + 续重运费合计 |
| rebate_total | Decimal | 0.01 元 | `base_total × rebate_pct` 量化到分，整月补差 |
| weight_share | Decimal | 0.000001 | 票基础运费 ÷ 月基数，末票吸收舍入残差，权重和恒为 1 |
| rebate_amount | Decimal | 0.01 元 | 逐票返利分摊（负向调整），末票 = 月返利 - 已分摊之和 |

- 归集口径：按 `pickup_utc` 的 UTC 自然月 `YYYY-MM` 与承运商分组，与择版同一时刻口径。
- 返利基数只含运输性运费（基础 + 续重），不含偏远、燃油、保价等附加费。
- 返利是独立调整单：`charge_lines` 逐笔原运费永不回改；月账净值 = 原应收合计 - 返利合计。
- 状态机：`draft`（可重算）→ `publish`（月账三账相等才允许，发布后锁定）→ `revoke` 回草稿。
- 重跑按 run 整体先删后插，已发布月份在发布态下拒绝重算（REBATE_PUBLISHED_LOCKED），不会重复返利。
