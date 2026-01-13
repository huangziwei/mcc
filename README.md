# Modern Chinese Common Words (2e, 2021)

Preview: http://hzwei.dev/mcc/

### Proofreading Progress

<!-- mcc:stats:start -->
- Pass 1: 100%
- Pass 2: 9,083 / 56,790 (16.0%)
<!-- mcc:stats:end -->

Current proofreading focus: add pinyin and double check selected word origin.

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
