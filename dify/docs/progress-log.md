
## 合规自检 2026-11-03 19:43

通过 1/8

- [FAIL] **C1 DSL 可重导入** — 异常：HTTP Error 401: UNAUTHORIZED
- [FAIL] **C2 seekdb 承载数据** — 异常：ERROR 2003 (HY000): Can't connect to MySQL server on '127.0.0.1:2881' (111)
- [FAIL] **C3 seekdb 检索生效** — 异常：HTTP Error 500: Internal Server Error
- [FAIL] **C4 Dify 应用可运行** — 异常：HTTP Error 401: UNAUTHORIZED
- [FAIL] **C5 运行说明完整** — README.md 不存在
- [FAIL] **C6 验证样例完整** — samples/ 不存在
- [PASS] **C7 无真实凭证** — 未发现 sk- 形式的真实凭证
- [FAIL] **C8 证据索引有效** — evidence/README.md 缺失

## 合规自检 2026-11-03 20:00

通过 8/8

- [PASS] **C1 DSL 可重导入** — 重导入成功（completed，dsl 0.7.0）
- [PASS] **C2 seekdb 承载数据** — 表齐；向量索引 14 组、全文索引 6 个；台词 41 条、事件 11 条
- [PASS] **C3 seekdb 检索生效** — 命中 3 条，Top1=往酒坛里兑水(vsim=1.0, ft=True, score=1.0)
- [PASS] **C4 Dify 应用可运行** — workflow succeeded，回答 90 字
- [PASS] **C5 运行说明完整** — 六项要素齐全（8797 字）
- [PASS] **C6 验证样例完整** — 7 个样例，必需要素齐全
- [PASS] **C7 无真实凭证** — 未发现 sk- 形式的真实凭证
- [PASS] **C8 证据索引有效** — 索引 14 条，全部存在

## 合规自检 2026-11-03 20:32

通过 9/9

- [PASS] **C1 DSL 可重导入** — 重导入成功（completed，dsl 0.7.0）
- [PASS] **C2 seekdb 承载数据** — 表齐；向量索引 14 组、全文索引 6 个；台词 41 条、事件 14 条
- [PASS] **C3 seekdb 检索生效** — 命中 3 条，Top1=又往酒坛里兑水(vsim=0.9599, ft=True, score=0.972)
- [PASS] **C4 Dify 应用可运行** — workflow succeeded，回答 148 字
- [PASS] **C9 PowerContext 记忆生效** — 记忆召回生效：MEMORY=柳三娘对陈三（p_demo01）的印象：逐客。最近一次在大堂掀了桌子（violence，5级，第2次），仇值 100。；柳三娘对陈三（p_demo…
- [PASS] **C5 运行说明完整** — 六项要素齐全（9634 字）
- [PASS] **C6 验证样例完整** — 9 个样例，必需要素齐全
- [PASS] **C7 无真实凭证** — 未发现 sk- 形式的真实凭证
- [PASS] **C8 证据索引有效** — 索引 18 条，全部存在

## 合规自检 2026-11-03 21:05

通过 9/9

- [PASS] **C1 DSL 可重导入** — 重导入成功（completed，dsl 0.7.0）
- [PASS] **C2 seekdb 承载数据** — 表齐；向量索引 14 组、全文索引 6 个；台词 41 条、事件 27 条
- [PASS] **C3 seekdb 检索生效** — 命中 3 条，Top1=往酒坛里兑水(vsim=1.0, ft=True, score=1.0)
- [PASS] **C4 Dify 应用可运行** — workflow succeeded，回答 140 字
- [PASS] **C9 PowerContext 记忆生效** — 记忆召回生效：MEMORY=柳三娘对陈三（p_demo01）的印象：逐客。最近一次在大堂掀了桌子（violence，5级，第2次），仇值 100。；柳三娘对陈三（p_demo…
- [PASS] **C5 运行说明完整** — 六项要素齐全（9634 字）
- [PASS] **C6 验证样例完整** — 9 个样例，必需要素齐全
- [PASS] **C7 无真实凭证** — 未发现 sk- 形式的真实凭证
- [PASS] **C8 证据索引有效** — 索引 25 条，全部存在

## 合规自检 2026-11-03 22:25

通过 4/9

- [FAIL] **C1 DSL 可重导入** — 异常：<urlopen error [Errno 111] Connection refused>
- [FAIL] **C2 seekdb 承载数据** — 异常：ERROR 2003 (HY000): Can't connect to MySQL server on '127.0.0.1:2891' (111)
- [FAIL] **C3 seekdb 检索生效** — 异常：<urlopen error [Errno 111] Connection refused>
- [FAIL] **C4 Dify 应用可运行** — 未设置 INN_APP_ID，跳过运行检查
- [FAIL] **C9 PowerContext 记忆生效** — 异常：<urlopen error [Errno 111] Connection refused>
- [PASS] **C5 运行说明完整** — 六项要素齐全（9708 字）
- [PASS] **C6 验证样例完整** — 10 个样例，必需要素齐全
- [PASS] **C7 无真实凭证** — 未发现 sk- 形式的真实凭证
- [PASS] **C8 证据索引有效** — 索引 27 条，全部存在

## 合规自检 2026-11-03 22:29

通过 9/9

- [PASS] **C1 DSL 可重导入** — 重导入成功（completed，dsl 0.7.0）
- [PASS] **C2 seekdb 承载数据** — 表齐；向量索引 14 组、全文索引 6 个；台词 41 条、事件 19 条
- [PASS] **C3 seekdb 检索生效** — 命中 3 条，Top1=往酒坛里兑水(vsim=1.0, ft=True, score=1.0)
- [PASS] **C4 Dify 应用可运行** — workflow succeeded，回答 102 字
- [PASS] **C9 PowerContext 记忆生效** — 记忆召回生效：MEMORY=柳三娘对陈三（p_demo01）的印象：逐客。最近一次在大堂掀了桌子（violence，5级，第2次），仇值 100。；柳三娘对陈三（p_demo…
- [PASS] **C5 运行说明完整** — 六项要素齐全（9708 字）
- [PASS] **C6 验证样例完整** — 10 个样例，必需要素齐全
- [PASS] **C7 无真实凭证** — 未发现 sk- 形式的真实凭证
- [PASS] **C8 证据索引有效** — 索引 27 条，全部存在

## 合规自检 2026-11-03 23:00

通过 9/9

- [PASS] **C1 DSL 可重导入** — 重导入成功（completed，dsl 0.7.0）
- [PASS] **C2 seekdb 承载数据** — 表齐；向量索引 14 组、全文索引 6 个；台词 60 条、事件 17 条
- [PASS] **C3 seekdb 检索生效** — 命中 3 条，Top1=又往酒坛里兑水(vsim=1.0, ft=True, score=1.0)
- [PASS] **C4 Dify 应用可运行** — workflow succeeded，回答 129 字
- [PASS] **C9 PowerContext 记忆生效** — 记忆召回生效：MEMORY=柳三娘对浪客（p_check_pc）的印象：和善。最近一次在后厨在醋坛子里洗手（hygiene，1级，第2次），仇值 14。；柳三娘对浪客（p_c…
- [PASS] **C5 运行说明完整** — 六项要素齐全（10146 字）
- [PASS] **C6 验证样例完整** — 10 个样例，必需要素齐全
- [PASS] **C7 无真实凭证** — 未发现 sk- 形式的真实凭证
- [PASS] **C8 证据索引有效** — 索引 28 条，全部存在

## 合规自检 2026-11-03 23:28

通过 10/10

- [PASS] **C1 DSL 可重导入** — 重导入成功（completed，dsl 0.7.0）
- [PASS] **C2 seekdb 承载数据** — 表齐；向量索引 14 组、全文索引 6 个；台词 60 条、事件 19 条
- [PASS] **C3 seekdb 检索生效** — 命中 3 条，Top1=又往酒坛里兑水(vsim=1.0, ft=True, score=1.0)
- [PASS] **C4 Dify 应用可运行** — workflow succeeded，回答 107 字
- [PASS] **C9 PowerContext 记忆生效** — 记忆召回生效：MEMORY=柳三娘对浪客（p_check_pc）的印象：和善。最近一次在后厨在醋坛子里洗手（hygiene，1级，第1次），仇值 6。；柳三娘对浪客（p_ch…
- [PASS] **C10 打包完整性** — zip 内 75 个文件，必需项齐全、无 .env/.venv 泄漏
- [PASS] **C5 运行说明完整** — 六项要素齐全（10996 字）
- [PASS] **C6 验证样例完整** — 10 个样例，必需要素齐全
- [PASS] **C7 无真实凭证** — 未发现 sk- 形式的真实凭证
- [PASS] **C8 证据索引有效** — 索引 30 条，全部存在

## 合规自检 2026-11-04 11:12

通过 10/10

- [PASS] **C1 DSL 可重导入** — 重导入成功（completed，dsl 0.7.0）
- [PASS] **C2 seekdb 承载数据** — 表齐；向量索引 14 组、全文索引 6 个；台词 60 条、事件 30 条
- [PASS] **C3 seekdb 检索生效** — 命中 3 条，Top1=又往酒坛里兑水(vsim=1.0, ft=True, score=1.0)
- [PASS] **C4 Dify 应用可运行** — workflow succeeded，回答 118 字
- [PASS] **C9 PowerContext 记忆生效** — 记忆召回生效：MEMORY=柳三娘对浪客（p_check_pc）的印象：戒备。最近一次在后厨在醋坛子里洗手（hygiene，1级，第3次），仇值 24。；柳三娘对浪客（p_c…
- [PASS] **C10 打包完整性** — zip 内 77 个文件，必需项齐全、无 .env/.venv 泄漏
- [PASS] **C5 运行说明完整** — 六项要素齐全（11824 字）
- [PASS] **C6 验证样例完整** — 10 个样例，必需要素齐全
- [PASS] **C7 无真实凭证** — 未发现 sk- 形式的真实凭证
- [PASS] **C8 证据索引有效** — 索引 31 条，全部存在

## 合规自检 2026-11-04 12:01

通过 10/10

- [PASS] **C1 DSL 可重导入** — 重导入成功（completed，dsl 0.7.0）
- [PASS] **C2 seekdb 承载数据** — 表齐；向量索引 14 组、全文索引 6 个；台词 60 条、事件 16 条
- [PASS] **C3 seekdb 检索生效** — 命中 3 条，Top1=又往酒坛里兑水(vsim=1.0, ft=True, score=1.0)
- [PASS] **C4 Dify 应用可运行** — workflow succeeded，回答 132 字
- [PASS] **C9 PowerContext 记忆生效** — 记忆召回生效：MEMORY=柳三娘对浪客（p_check_pc）的印象：和善。最近一次在后厨在醋坛子里洗手（hygiene，1级，第1次），仇值 6。；柳三娘对浪客（p_ch…
- [PASS] **C10 打包完整性** — zip 内 77 个文件，必需项齐全、无 .env/.venv 泄漏
- [PASS] **C5 运行说明完整** — 六项要素齐全（11824 字）
- [PASS] **C6 验证样例完整** — 10 个样例，必需要素齐全
- [PASS] **C7 无真实凭证** — 未发现 sk- 形式的真实凭证
- [PASS] **C8 证据索引有效** — 索引 31 条，全部存在

## 合规自检 2026-11-04 12:04

通过 8/10

- [FAIL] **C1 DSL 可重导入** — 异常：HTTP Error 401: UNAUTHORIZED
- [PASS] **C2 seekdb 承载数据** — 表齐；向量索引 14 组、全文索引 6 个；台词 60 条、事件 23 条
- [PASS] **C3 seekdb 检索生效** — 命中 3 条，Top1=又往酒坛里兑水(vsim=1.0, ft=True, score=1.0)
- [FAIL] **C4 Dify 应用可运行** — 异常：HTTP Error 401: UNAUTHORIZED
- [PASS] **C9 PowerContext 记忆生效** — 记忆召回生效：MEMORY=柳三娘对浪客（p_check_pc）的印象：和善。最近一次在后厨在醋坛子里洗手（hygiene，1级，第1次），仇值 6。；柳三娘对浪客（p_ch…
- [PASS] **C10 打包完整性** — zip 内 79 个文件，必需项齐全、无 .env/.venv 泄漏
- [PASS] **C5 运行说明完整** — 六项要素齐全（12144 字）
- [PASS] **C6 验证样例完整** — 10 个样例，必需要素齐全
- [PASS] **C7 无真实凭证** — 未发现 sk- 形式的真实凭证
- [PASS] **C8 证据索引有效** — 索引 32 条，全部存在
