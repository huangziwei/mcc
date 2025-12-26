# Modern Chinese Common Words / 现代汉语常用词表 (2e, 2021)

WIP. Preview: http://hzwei.dev/mcc/

### Proofreading Progress

<!-- mcc:stats:start -->
- Pass 1: 36,098 / 56,897 (63.4%)
<!-- mcc:stats:end -->

### Usage

```bash
uv sync

# tools for preprocessing raw data
mcc render # extract all pages
mcc segment # split each page by column
mcc ocr # ocr each page and save as csv to post/csv

# tools for proofreading and releasing
mcc proofread # launch the proofreading web app
mcc dx [index | duplicates] # diagnostics 
mcc merge # create or update the complete word list
```

### Source Material

- 李行健、苏新春（主编）. 《现代汉语常用词表（第2版）》. 北京：商务印书馆, 2021. ISBN 978-7-100-20011-0.
