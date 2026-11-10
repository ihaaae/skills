---
name: pdf-to-markdown
description: 把 PDF（含扫描版、公式多的书和论文）用 Datalab 官方 Marker API 转成单个给 Agent 读的 Markdown 文件，带行号目录、每页的 PDF 页码标记和 $ 公式。用户要转换、阅读、检索或引用 .pdf 内容，而 PDF 没有可靠的文字层（扫描版）或公式要还原时使用；ePub 用 epub-to-markdown。
---

# PDF → Markdown

把一个 PDF 转成**一个** Markdown 文件，目标读者是 Agent：开头是行号目录，每页前有 `<!-- PDF page N -->`，方便按章节和页码读取、回到原 PDF 核对。识别由 Datalab 的托管 API（Marker）完成，本 skill 只负责上传、等待和整理输出。

依赖：`python3`（只用标准库）、网络，以及 Datalab API key。

## Key

从环境变量 `DATALAB_API_KEY` 读取，没有时读 `~/.config/datalab/api-key`（只有一行，权限 0600，不进 Git）。都没有时，请用户自己在本机写入这个文件，不要让用户把 key 贴进对话，也不要打印它。

## 费用与隐私

- 按页计费（新账号有 \$5 免费额度）；整本书前先用 `--pages` 试几页，确认质量后再转全书，并告诉用户大概要转多少页。
- PDF 会上传到 Datalab，结果约一天后从其服务器删除。用户不愿上传的文件不要用本 skill。

## 步骤

1. 先试几页（页码从 0 起，是 PDF 物理页，不是印刷页码）：

   ```bash
   python3 <本 skill 目录>/scripts/pdf2md.py BOOK.pdf -o sample.md --pages 59-61
   ```

   可选参数：
   - `--mode accurate|balanced|fast`：默认 `accurate`，适合扫描版、公式和复杂版面；干净的文字版 PDF 可用 `balanced`，更快更便宜。
   - `--media DIR`：同时把图片写进 DIR，Markdown 里是相对输出文件的链接。默认只留占位符 `[图: 文件名]`。
2. 打开原 PDF 的同几页，和输出逐段对照，至少核对公式、上下标、标题层级和图注。结果不好时换 mode 再试，或告诉用户。
3. 质量可以接受后，去掉 `--pages` 转全书（输出文件已存在时脚本拒绝覆盖）。
4. 看 stderr 的 JSON 报告，按下面「检查」确认，再把文件交给用户。

## 输出格式

- YAML front matter：`title`、`source`、`pages`（转了几页）、`lines`（总行数）、`toc`。
- `toc` 每项是 `[行号, 标题级别, 标题]`，行号是输出文件里的绝对行号。标题来自 Marker 对版面的识别，层级可能和书不完全一致。
- 每页前一行 `<!-- PDF page N -->`，N 从 1 起，和 PDF 阅读器里的页码一致。
- 公式是 `$...$` 和 `$$...$$`。
- 页眉、页脚、页码默认去掉。

## 读取转换结果

不要整本读入。先读 front matter，在 `toc` 里找章节，或 grep `PDF page N` 找页，再按行号范围读取。引用内容时注明 PDF 页码；OCR 结果不是原文，公式和数字要回原 PDF 核对。

## 检查

- `parse_quality_score`（0–5）低于 3：换 `--mode accurate` 重试；已经是 accurate 就告诉用户。
- `failed_pages` 非空：这些页（0 起）没识别出来，告诉用户。
- `pages` 和请求的页数不符：有页丢失，告诉用户。
- `headings` 为 0 或极少：目录不可用，改用 `PDF page` 标记和 grep 定位。
- 书里有公式而 `math_spans` 为 0：公式没被识别，不要自己编造公式。
- `cost` 是这次请求的费用明细。
