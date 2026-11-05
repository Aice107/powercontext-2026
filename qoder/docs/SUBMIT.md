# 提交信息（SUBMIT）

> 提交前请把占位符补齐。

## 仓库与分支

| 项 | 值 |
| --- | --- |
| 代码仓库 | https://github.com/Aice107/powercontext-2026 |
| 提交分支 | `2026-competition-ecosystem`（按赛题要求基于该分支开发；提交内容同时在分支 `qoder-submission` 上） |
| 提交 commit | 以上述分支的当前顶端为准（平台提交时用 `git rev-parse origin/2026-competition-ecosystem` 获取最新值填入） |
| 项目资产目录 | `qoder/` |

## 项目网站

| 项 | 值 |
| --- | --- |
| 网站地址 | https://gewu-copilot-l2o2y8buvaq.qoder.zone |
| 可见范围 | 任何人都可访问（公开，未登录可打开） |
| 发布方式 | Qoder Sites（站点源码：`qoder/site/`，发布产物：`qoder/site-dist/`） |

## 提交前自检清单

- [ ] 无痕窗口打开项目网站可正常访问；
- [ ] `docs/REPRODUCE.md` 的步骤在干净环境重跑过一遍；
- [ ] `bash scripts/verify.sh` 全部通过，`evidence/logs/` 与提交版本一致；
- [ ] 仓库与文档中无任何真实凭据（token、密码、Key）；
- [ ] `docs/QODER_LOG.md` 已补齐对话截图与 Qoder 账号 UID；
- [ ] 本文件占位符已全部替换。

## 使用效果材料

见 `docs/COMPLIANCE.md`「关于使用效果数据的说明」：受控自测数据 + 站点访问统计，
不包含未发生的用户数据。访问统计截图存 `evidence/site-analytics/`。
