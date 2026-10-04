## 变更说明 (Description)

简要说明本次 PR 的背景、修改内容及动机。
Briefly describe the context, changes, and motivation.

## 关联 Issue (Related Issues)

- Closes #
- Fixes #

## 自查清单 (Checklist)

- [ ] 已在本地运行单元测试并通过：`pytest tests/ -q` (240+ passed)
- [ ] 代码风格检查通过：`ruff check .`
- [ ] 若新增积木或修改数据契约，已同步更新中英文文档并运行 `pytest tests/test_contract_sync.py` 验证防漂移
- [ ] 零私有凭据或硬编码密钥（严格遵循无凭据与最小权限原则）
- [ ] 新增功能已补充对应单元测试
