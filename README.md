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

## Motivation

### Main Quest

Ultimately, the goal of this project is to quantify what percentage of common words are of foreign origin by cross-referencing the common word list (first step) with some authoritative dictionaries (second step).

### Side Quest

I used `tesseract` for OCR, and it yielded only 71.54% agreement with the first-pass proofread list (that is, about 16k rows across 1245 files to fix during proodreading). I've heard `deepseek-ocr` can yield better results, but in general it is slow to run locally (roughly 1.5 minutes per column on my outdated Intel MacBook Pro). It also surely won't hit 100% accuracy and still requires a separate proofreading step, but I am curious about how much better it can get.

So far I tested about 20 pages and got ~96-98% agreement. When it works, it works great and mostly tripped over fine details due to lossy scans, such as 入/人, 耍/要, 未/末, etc. But when it failed, it failed completely (no meaningful output but gibberish). Modifying the prompt might fix it for some pages, but it fails others; in short, it's not very deterministic. There's hope that one day local LLMs can replace traditional methods, but we are not there yet.

## Installation (macOS via Homebrew)

### Tesseract (for `mcc ocr`)

```bash
brew install tesseract
# If chi_sim is missing, install language packs.
brew install tesseract-lang
tesseract --list-langs
```

### Ollama (for `mcc ollama-ocr`)

```bash
brew install ollama
ollama serve # keep this running in another terminal
ollama pull deepseek-ocr
```

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
