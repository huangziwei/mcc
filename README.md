# Modern Chinese Common Words / 现代汉语常用词表 (2e, 2021)

WIP.

### Proofreading Progress

<!-- mcc:stats:start -->
- Rows proofread: 16,542 / 56,982 (29.0%)
- Columns proofread: 363 / 1,245 (29.2%)
- Passes: pass 1: 363 cols / 16,542 rows
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
