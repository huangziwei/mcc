# Modern Chinese Common Words (2e, 2021)

## TL;DR

- [Download](https://raw.githubusercontent.com/huangziwei/mcc/refs/heads/main/post/merged/modern-chinese-common-words.csv) (CSV)
- [Preview](https://hzwei.dev/mcc)

## Proofreading Progress

<!-- mcc:stats:start -->
- Pass 1: 100%
- Pass 2: 9,129 / 56,790 (16.1%)
<!-- mcc:stats:end -->

Current proofreading focus: add pinyin and double check selected word origin.

## Usage

```bash
uv sync

# core tools for preprocessing raw data
mcc render # extract all pages
mcc segment # split each page by column
mcc ocr # OCR each page and save as csv to post/csv

# side quest
mcc ollama-ocr # use deepseek-ocr via ollama for OCR
mcc diff-ocr # quantify the difference between tessarat and deepseek-ocr

# tools for proofreading and releasing
mcc proofread # launch the proofreading web app
mcc dx [index | duplicates] # diagnostics 
mcc merge # create or update the complete word list
```

## Source Material

- 李行健、苏新春（主编）. 《现代汉语常用词表（第2版）》. 北京：商务印书馆, 2021. ISBN 978-7-100-20011-0.
