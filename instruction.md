# NovelSnip
**本项目不对任何产生的后果和影响付任何责任，请有责任心地谨慎摸鱼**
**把小说“藏”在注释里、随写随看 —— 在代码中分散注入小段注释作为小说页面，支持翻页、移除与 PyCharm 一键调用。**
> NovelSnip 把指定的 `.txt` 小说分成“页”，并将每页的若干小段（snippet）以普通注释的形式分散写入目标代码文件中。写代码时这些注释像普通注释一样存在，不影响运行；通过命令可以翻到下一页/上一页/指定页；完成后可一键清除所有小说注释。

---

## 主要特点
- 将小说拆成“页（page）”并分散插入为多个注释 snippet。
- 翻页命令会**只替换注释片段**，不动原有代码。
- 注释完全是普通 `#` 注释，PyCharm 下极易混入常规注释之中。
- 注入前会自动备份目标文件（`<file>.novelbak`）。
- 支持 `inject`、`next`、`prev`、`goto`、`status`、`strip` 操作。
- 支持在注入时把小说 companion 写入隐藏目录（建议）以便离线翻页。

---

## 文件说明
- `novel_injector.py` — 主脚本（命令行工具）。  
- `README.md` — 本文档。  
- （注）脚本在注入时会在目标同目录或 `.idea/novels/` 写入一个 companion 小说副本（可配置），用于翻页时读取小说内容。脚本也会生成目标文件的备份 `<target>.novelbak`。

---

## Quickstart

1. 把 `novel_injector.py` 放到你的项目根目录（或任意可执行路径）。  
2. 准备想要阅读的小说 `.txt`（UTF-8 编码优先）。  
3. 在项目目录打开终端运行（示例）：

```bash
# 在 module.py 顶部注入 novel.txt（默认 page_size=40，snippets=6）
python novel_injector.py inject /path/to/novel.txt /path/to/project/module.py --page-size 40 --snippets 6

# 翻到下一页
python novel_injector.py next /path/to/project/module.py

# 翻到上一页
python novel_injector.py prev /path/to/project/module.py

# 跳到指定页（0-based）
python novel_injector.py goto /path/to/project/module.py 3

# 查看注入状态（id、current_page、total_pages 等）
python novel_injector.py status /path/to/project/module.py

# 完成后移除所有注释（提交代码前请务必执行）
python novel_injector.py strip /path/to/project/module.py


