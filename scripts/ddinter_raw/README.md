# DDInter 原始数据放置说明

本目录用于存放 DDInter 2.0 的原始 CSV 文件，**不会被提交到 git**（已写入 `.gitignore`）。

## 1. 下载

DDInter 2.0 官方下载页：https://ddinter.scbdd.com/download/

DDInter 2.0 按 ATC 一级类目拆分，共 5 个 CSV：

| 文件名（示例） | ATC 类目 |
|----------------|----------|
| `ddinter_downloads_code_A.csv` | A — 消化道与代谢 |
| `ddinter_downloads_code_B.csv` | B — 血液和造血系统 |
| `ddinter_downloads_code_D.csv` | D — 皮肤病用药 |
| `ddinter_downloads_code_H.csv` | H — 全身用激素类制剂 |
| `ddinter_downloads_code_L.csv` | L — 抗肿瘤药与免疫调节剂 |
| `ddinter_downloads_code_P.csv` | P — 抗寄生虫药、杀虫药 |
| `ddinter_downloads_code_R.csv` | R — 呼吸系统 |
| `ddinter_downloads_code_V.csv` | V — 各类其他药物 |

> 实际文件数和命名以官网为准。**全部放在本目录下即可**，导入脚本会自动扫描所有 `*.csv`。

## 2. CSV 列约定

DDInter 2.0 的相互作用 CSV 通常包含以下列（脚本按列名读取，列序无关）：

| 列名 | 含义 |
|------|------|
| `DDInterID_A` | 药物 A 的 DDInter ID |
| `Drug_A` | 药物 A 名称 |
| `DDInterID_B` | 药物 B 的 DDInter ID |
| `Drug_B` | 药物 B 名称 |
| `Level` | 严重度，取值 `Major` / `Moderate` / `Minor` |

> 若你下载的文件列名不一致，请在 `scripts/import_ddinter.py` 顶部的 `COLUMN_ALIASES` 里加映射。

## 3. 中英文别名（可选）

为了让风险检查命中"阿司匹林"=="Aspirin"，本目录可放一个 `aliases.yaml`：

```yaml
# key 是 DDInter 中的英文药名（lower-case），value 是该药的所有中文/英文别名
aspirin:
  - 阿司匹林
  - 乙酰水杨酸
  - ASA
warfarin:
  - 华法林
  - 华法令
  - 苯丙香豆素
clopidogrel:
  - 氯吡格雷
  - 波立维
```

脚本会自动读取本文件并把别名写入 `ddinter_drug.drug_name_normalized` 索引。

## 4. 运行导入

```bash
cd <repo-root>
uv run python scripts/import_ddinter.py
```

输出示例：

```
[1/2] 扫描 CSV: 8 个文件
[2/2] 导入药物与相互作用 ...
  - 已导入药物 4128 条
  - 已导入相互作用 21456 条
  - 别名映射 35 条
完成。
```

## 5. 合规

DDInter 2.0 数据**仅授权用于非商业研究和演示**。本目录的所有原始 CSV 不要提交到 git，也不要分发给项目组以外的人员。正式商用前必须重新确认授权或替换合规数据源。
