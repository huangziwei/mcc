# Modern Chinese Common Words / 现代汉语常用词表 (2e, 2021)

WIP.

### Proofreading Progress

<!-- mcc:stats:start -->
- Rows proofread: 3,380 / 57,068 (5.9%)
- Columns proofread: 75 / 1,245 (6.0%)
- Passes: pass 1: 75 cols / 3,380 rows
<!-- mcc:stats:end -->

### Usage

```bash
uv sync

mcc render # extract all pages
mcc segment # split each page by column
mcc ocr # ocr each page and save as csv to post/csv
mcc proofread # launch the proofreading web app
mcc merge # create or update the complete word list
```

### Source Material

- 李行健、苏新春（主编）. 《现代汉语常用词表（第2版）》. 北京：商务印书馆, 2021. ISBN 978-7-100-20011-0.
