# 转换样例

`progit.md` 是 `scripts/epub2md.py` 在 `books/progit.epub` 上的输出（pandoc 3.1.3），内容许可同原书：[CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/)，作者 Scott Chacon、Ben Straub 及 progit2-zh 译者。

重新生成：

```bash
python3 ../../skills/epub-to-markdown/scripts/epub2md.py books/progit.epub -o samples/progit.md
```

`bench/regress.sh` 通过时，它与 `bench/golden.tsv` 里 progit / 3.1.3 的哈希一致。
