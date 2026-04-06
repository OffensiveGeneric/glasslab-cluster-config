# Local Academic Research Knowledge Base: Tools, Architecture & Workflow

## Overview

Building a personal, local-first research knowledge base for academic papers — one that scans PDFs, generates intermediate markdown, maintains indexes and summaries, and enables NotebookLM-style Q&A — is now very achievable with a well-chosen open-source stack. The approach differs from the general LLM wiki workflow (as described by the context you shared) in one critical way: academic papers demand **structured extraction** (equations, tables, figures, citations, section headings) plus **provenance** (which paper said what, when, how many citations does it have). The architecture below is organized into four layers: Ingest, Index/Compile, Q&A, and Trend Tracking.

***

## Layer 1: PDF Ingest — Structured Extraction

The single most important choice is your PDF-to-Markdown converter, because everything downstream depends on extraction quality. For academic papers specifically, three tools stand out.

### Marker (datalab-to/marker)

Marker is a pipeline of deep learning models purpose-built for scientific documents. It handles:[^1]
- OCR when necessary (via Surya), plus layout detection and reading-order reconstruction
- Equation-to-LaTeX conversion (via Texify)
- Table extraction as structured Markdown/HTML
- Image saving alongside the `.md` output
- Optional LLM-boosted quality pass for ambiguous content[^2]

Install with `pip install marker-pdf`. Batch process a whole directory of PDFs from the CLI:
```bash
marker_chunk_convert /path/to/project/pdfs/ /path/to/project/md/ --workers 4
```
Benchmarks show Marker is 4× faster than the Facebook Nougat model and more accurate on non-arXiv papers. It supports GPU, CPU, and Apple MPS.[^1][^2]

### Docling (IBM / Linux Foundation)

Docling is IBM Research's open-source document parser, now under the Linux Foundation AI & Data Foundation. It auto-detects format, applies layout analysis, reconstructs tables, runs OCR, and emits clean JSON or Markdown. The `DoclingDocument` Pydantic object keeps text, images, tables, formulas, and layout metadata together — downstream RAG tools like LangChain, LlamaIndex, and Haystack can consume it directly. Docling was used internally at IBM to process 2.1 million PDFs from Common Crawl and is shipping weekly updates.[^3][^4]

```python
from docling.document_converter import DocumentConverter
converter = DocumentConverter()
result = converter.convert("paper.pdf")
print(result.document.export_to_markdown())
```

### MinerU (opendatalab)

MinerU is optimized for scientific literature with particular strength on formulas (using the UniMERNet model). It supports batch processing with significant speed improvements and offline deployment after initial model download. A good fallback for papers where Marker struggles with complex formula-dense layouts.[^5]

### Recommendation

For a Python-native, Obsidian-friendly workflow, **Marker is the primary choice** for most CS/ML papers. Use Docling when you need richer structured output (JSON with section hierarchy) or when plugging into LangChain/LlamaIndex pipelines. Keep MinerU as a fallback for heavily formula-laden content.[^6]

***

## Layer 2: Reference Management — Metadata and Citations

Before or alongside extraction, you need a metadata layer to track each paper's authorship, DOI, citation count, venue, and relationships to other papers. This is where the stack diverges most sharply from a general markdown wiki.

### Zotero + Better BibTeX + ZotLit (Obsidian)

The canonical academic workflow is:
1. **Zotero** as the reference manager — stores metadata, DOI, PDF, and your own annotations[^7]
2. **Better BibTeX** plugin in Zotero — provides stable citekeys and bibtex export[^8]
3. **ZotLit** plugin in Obsidian — bulk-exports papers from Zotero into templated Markdown notes with YAML frontmatter (title, authors, DOI, venue, year, your summary)[^9]

ZotLit accesses Zotero's database directly (blazingly fast), supports drag-and-drop annotation copying, and allows intricate Eta/Nunjucks templates so every paper note has a consistent structure. The resulting Obsidian vault contains one `.md` note per paper, with frontmatter metadata and imported highlights, linked to the actual PDF.[^9]

### Semantic Scholar API

For trend tracking and citation graph exploration, the Semantic Scholar Open Data Platform provides programmatic access to 225M+ papers, 2.8B+ citation edges, and SPECTER2 embeddings. The free API supports paper lookup by ArXiv ID, DOI, PMID, and keyword search, plus a recommendations endpoint for "papers similar to this one". PaperQA2 uses Semantic Scholar automatically to enrich paper metadata during indexing.[^10][^11][^12][^13]

```python
from semanticscholar import SemanticScholar
sch = SemanticScholar()
paper = sch.get_paper("arXiv:2301.10140")
recs = sch.get_recommended_papers(paper.paperId)
```

***

## Layer 3: Q&A Engine — The NotebookLM Equivalent

Once you have a directory of PDFs and their extracted Markdown, you need a Q&A layer. There are two philosophically different approaches: **RAG-based** (vector search + generation) and **progressive-disclosure / index-based** (like napkin).

### PaperQA2 (FutureHouse/paper-qa) — Best-in-class Scientific RAG

PaperQA2 is the most purpose-built tool for this exact use case. Its three-phase agentic workflow:[^14]
1. **Paper Search** — LLM generates keyword queries, retrieves candidates from local PDFs and/or Semantic Scholar/arXiv[^10]
2. **Gather Evidence** — Chunks are embedded, ranked by cosine similarity, then *re-ranked and summarized* in the context of the query by an LLM (Retrieval-Contextual Summarization = RCS)[^14]
3. **Generate Answer** — Final answer with inline citations grounded to specific passages[^10]

Key features for an academic workflow:
- CLI (`pqa`) — point it at any directory of PDFs and ask a question[^15]
- Automatic metadata fetching from Semantic Scholar and Crossref (including citation counts and retraction checks)[^16]
- Incremental index — after first build, only new PDFs are re-indexed[^15]
- Supports any LiteLLM-compatible model: OpenAI, Anthropic, local Ollama models[^10]
- Superhuman performance benchmarks on scientific QA, summarization, and contradiction detection[^17]

```bash
cd /path/to/project/pdfs/
pqa ask "What are the main approaches to attention in transformers?"
```

For larger collections (100+ papers), register free API keys for Crossref and Semantic Scholar to avoid rate limits.[^15]

### AnythingLLM — Local, Multi-workspace RAG

AnythingLLM is a self-hosted, open-source RAG desktop/Docker app that organizes documents into **workspaces** (one per research project). It supports PDF, TXT, Markdown, DOCX, and more; uses LanceDB by default (zero external dependencies) or can connect to Qdrant/ChromaDB; and works with local Ollama models for complete offline operation. Answers include citations with clickable links to source passages. A full REST API allows automation and integration with CLI tools. This is the closest turnkey GUI alternative to NotebookLM for a local stack.[^18]

### Khoj — Obsidian-Native Semantic Search + Chat

Khoj is an open-source, offline-first AI assistant that integrates directly with Obsidian as a community plugin. It indexes Markdown, PDF, Org-mode, and Notion files; provides semantic search via natural language queries; and supports chat against your vault using local or cloud LLMs. It is self-hostable with full data privacy. The Obsidian plugin means Q&A stays inside your existing IDE without switching contexts.[^19][^20][^21][^22]

### Smart Connections (Obsidian Plugin) — Semantic Similarity Within Vault

Smart Connections provides local-embedding-based semantic search directly inside Obsidian. The Smart Lookup view lets you pose natural language questions against your vault and retrieve the most semantically relevant notes — even when your wording differs from what you originally wrote. Indexing and retrieval run on-device by default. This is more of a discovery and connection-surfacing tool than a full Q&A system, but it is deeply integrated into the Obsidian IDE.[^23][^24][^25]

***

## Recommended Architecture: Per-Project Directory Structure

Given your existing setup (Obsidian, Python/CLI fluency, WSL + macOS), the following structure fits cleanly:

```
research/
├── transformer-architectures/          # one project per research topic
│   ├── raw/                            # original PDFs (managed by Zotero or manual)
│   │   ├── attention-is-all-you-need.pdf
│   │   └── ...
│   ├── md/                             # Marker/Docling output — one .md per PDF
│   │   ├── attention-is-all-you-need.md
│   │   └── ...
│   ├── wiki/                           # LLM-compiled articles, concept notes
│   │   ├── _index.md                   # master index + brief summaries
│   │   ├── attention-mechanisms.md
│   │   ├── positional-encoding.md
│   │   └── ...
│   ├── zotero-notes/                   # ZotLit-exported per-paper literature notes
│   │   └── AttentionIsAllYouNeed2017.md
│   └── outputs/                        # Q&A answers, trend reports, slides
│       └── ...
└── diffusion-models/
    └── ...
```

The **ingest pipeline** (run once per batch of new papers):
1. Drop PDFs into `raw/`
2. Run `marker_chunk_convert raw/ md/` to generate structured Markdown
3. ZotLit + Zotero sync populates `zotero-notes/` with metadata and annotations
4. LLM agent reads `md/` + `zotero-notes/` and compiles/updates `wiki/` articles and `_index.md`

***

## Layer 4: Trend Tracking

Tracking how a research area evolves over time requires more than static Q&A — it requires knowing what's new.

### arXiv + Semantic Scholar API as Alerting Systems

The Semantic Scholar API's **recommendations endpoint** returns papers similar to any seed paper, making it easy to build a weekly "what's new and relevant" script. Combined with arXiv's RSS feeds or the arXiv API (which exposes full abstracts, submission dates, and categories), you can automate new-paper discovery for any topic.[^12][^26]

A minimal trend-tracking script:
```python
from semanticscholar import SemanticScholar
sch = SemanticScholar()
# Get papers citing a key paper in your project
new_citing = sch.get_paper_citations("arXiv:1706.03762", fields=["title","year","abstract"])
# Filter for last 30 days, append to wiki/_new_papers.md
```

### ResearchRabbit + Zotero

ResearchRabbit acts as a "Spotify for research papers" — given a collection in your Zotero library, it maps the citation graph and surfaces related work you haven't seen. It is the most user-friendly tool for discovery and is free. Sync your Zotero library to ResearchRabbit and review its weekly email digests; import any new relevant papers back to Zotero, which then propagates to Obsidian via ZotLit.[^27]

### PaperQA2 Trend Queries

Because PaperQA2 re-indexes incrementally when new PDFs are added, a weekly workflow like "add new arXiv papers → run `pqa ask 'What new methods have emerged for X in 2026?'` → file the answer into `wiki/trends/`" creates a self-updating research diary.[^15]

***

## Tool Comparison

| Tool | Role | Local/Private | Obsidian Integration | Best For |
|---|---|---|---|---|
| **Marker** | PDF → Markdown | ✅ Fully local | Via output files | Scientific PDF extraction (equations, tables) |
| **Docling** | PDF → JSON/Markdown | ✅ Fully local | Via output files | Structured extraction for RAG pipelines |
| **Zotero + ZotLit** | Reference management | ✅ Local sync | ✅ Native plugin | Citation metadata, annotation import |
| **PaperQA2** | Scientific RAG Q&A | ✅ + API keys | Via CLI outputs | High-accuracy Q&A with citations on PDFs |
| **AnythingLLM** | Multi-doc RAG chatbot | ✅ Self-hosted | Via REST API | GUI-based NotebookLM replacement |
| **Khoj** | Semantic search + chat | ✅ Self-hostable | ✅ Native plugin | In-Obsidian Q&A across vault |
| **Smart Connections** | Semantic similarity | ✅ On-device | ✅ Native plugin | Note discovery and connection surfacing |
| **Semantic Scholar API** | Paper metadata + discovery | Cloud API (free) | Via scripts | Citation counts, recommendations, trend tracking |
| **ResearchRabbit** | Citation graph discovery | Cloud (free) | Via Zotero | Finding related papers you missed |

***

## LLM Compilation Step: Building the Wiki

The `wiki/` layer — where an LLM reads extracted Markdown and produces concept articles, `_index.md`, cross-links, and summaries — is the highest-leverage part of the workflow. Given your CLI-fluency, the recommended approach is a short Python script (or Claude Code session) that:

1. Reads `wiki/_index.md` (the running index of all processed papers)
2. Reads any new `.md` files in `md/` not yet listed in the index
3. Calls a frontier LLM (Claude or GPT-4o) with a prompt like: *"Given the following new paper markdown and the existing index, (a) update the index with a 3-sentence summary, (b) identify which existing wiki articles need updating, (c) suggest any new concept articles warranted."*
4. Writes outputs back to `wiki/`

Because PaperQA2 and Smart Connections both work best when the index is fresh, the LLM-compiled `_index.md` also serves as a high-quality, human-readable entry point for the RAG system. At ~100 articles, a frontier LLM can read the entire index in one context window — removing the need for complex RAG at discovery time, exactly as described in the context.[^28]

***

## Audio / Podcast Mode

The Lex Fridman use case (loading a focused mini-KB into voice mode for long runs) has a natural analog for lecture prep or commuting: after PaperQA2 or your LLM agent generates a Markdown synthesis document, feed it to NotebookLM's Audio Overview feature or to a TTS system with a structured script. A study evaluating NotebookLM's podcast generation found median scores of 4/5 across comprehensiveness, factual integrity, and utility from paper authors, though the conversational format occasionally loses nuance. For a more controlled, local version, a synthesis Markdown → structured Q&A script → ElevenLabs/OpenAI TTS pipeline gives the same effect with better accuracy.[^29][^30][^31]

***

## Napkin: The Agent-Native Knowledge Layer

The **napkin** library (michaelliv/napkin) referenced in the original context is worth integrating as the agent interface layer. It provides a file-based, progressively-disclosed knowledge system designed specifically for LLM agents — `napkin overview` returns a taxonomy and keyword map of the entire vault; `napkin search` narrows by TF-IDF weighted keywords (headings get 3× weight); `napkin read` returns full file content. Crucially, it replaces cosine-similarity vector search with LLM-navigated taxonomy — the model sees the structure of the corpus and decides where to look. Install globally with `npm install -g napkin-ai` and point it at your `wiki/` directory, giving any CLI-driven LLM agent (Claude Code, your own scripts) a structured navigation interface to the knowledge base.[^32][^28]

***

## Conclusion

The full stack for a local academic research knowledge base combines: **Marker** (PDF extraction) + **Zotero/ZotLit** (metadata + Obsidian sync) + **PaperQA2** (scientific Q&A via CLI) + **Khoj or Smart Connections** (in-Obsidian semantic search) + **Semantic Scholar API + ResearchRabbit** (trend discovery) + **napkin** (agent navigation layer), all organized in a per-project directory structure viewable in Obsidian. This gives you the core capabilities of NotebookLM (Q&A with citations, summaries, discovery) while keeping data local, supporting batch CLI workflows, and integrating naturally with the LLM-compiled wiki pattern you already use.

---

## References

1. [marker-pdf 0.3.4 - PyPI](https://pypi.org/project/marker-pdf/0.3.4/) - Marker converts PDF to markdown quickly and accurately. Supports a wide range of documents (optimize...

2. [marker-pdf - PyPI](https://pypi.org/project/marker-pdf/) - Marker. Marker converts documents to markdown, JSON, chunks, and HTML quickly and accurately. Conver...

3. [A new tool to unlock data from enterprise documents for generative AI](https://research.ibm.com/blog/docling-generative-AI) - Docling is designed to unlock data buried in PDFs and reports for generative AI applications.

4. [Docling: The Document Alchemist | Towards Data Science](https://towardsdatascience.com/docling-the-document-alchemist/) - Effortless extraction ... The PDF is converted again using Docling's DocumentConverter function, pro...

5. [GitHub - opendatalab/MinerU: Transforms complex documents like ...](https://github.com/opendatalab/mineru) - MinerU is a document parsing tool that converts PDF , image, and DOCX inputs into machine-readable f...

6. [Best Open Source PDF to Markdown Tools (2026): Marker vs …](https://jimmysong.io/blog/pdf-to-markdown-open-source-deep-dive/) - A practical comparison of open source PDF to Markdown tools in 2026, including Marker, MinerU, Dolph...

7. [How to Connect Zotero and Obsidian for the Ultimate PhD Workflow](https://girlinbluemusic.com/how-to-connect-zotero-and-obsidian-for-the-ultimate-phd-workflow/) - How to connect Zotero and Obsidian: a full walkthrough of my workflow, including a free template you...

8. [Step-by-step: How to Integrate Zotero + Obsidian for ...](https://www.linkedin.com/pulse/step-by-step-how-integrate-zotero-obsidian-seamless-sofie-peters-gfngf) - 🌟 A complete step-by-step guide for researchers, students, and anyone managing lots of reading and n...

9. [Connecting Zotero and Obsidian with the ZotLit Plugin + Templates](https://effortlessacademic.com/connecting-zotero-and-obsidian-with-the-zotlit-plugin-templates/) - Obsidian is on its way to becoming the most commonly used academic note-taking tool, due to its open...

10. [GitHub - Future-House/paper-qa: High accuracy RAG for answering ...](https://github.com/future-house/paper-qa) - PaperQA2 is a package for doing high-accuracy retrieval augmented generation (RAG) on PDFs, text fil...

11. [The Semantic Scholar Open Data Platform - arXiv](https://arxiv.org/html/2301.10140v2)

12. [Semantic Scholar Academic Graph API](https://www.semanticscholar.org/product/api) - Build projects that accelerate scientific progress with the Semantic Scholar Academic Graph API

13. [[2301.10140] The Semantic Scholar Open Data Platform - arXiv](https://arxiv.org/abs/2301.10140) - The volume of scientific output is creating an urgent need for automated tools to help scientists ke...

14. [PaperQA2 - Custom Open-source RAG for Scientific Documents with ...](https://medevel.com/paperqa2/) - PaperQA2 is a package for doing high-accuracy retrieval augmented generation (RAG) on PDFs or text f...

15. [PaperQA2 | PaperQA | EdisonScientific Cookbook - GitBook](https://edisonscientific.gitbook.io/edison-cookbook/paperqa)

16. [PaperQA2 download | SourceForge.net](https://sourceforge.net/projects/paperqa2.mirror/) - PaperQA2 is a package for doing high-accuracy retrieval augmented generation (RAG) on PDFs or text f...

17. [PaperQA2: Superhuman scientific literature search - FutureHouse](https://www.futurehouse.org/research-announcements/wikicrow) - PaperQA2 has access to a variety of tools that allow it to find papers, extract useful information f...

18. [Build Your Own Private AI Knowledge Base with AnythingLLM](https://www.antlatt.com/blog/anythingllm-local-knowledge-base/) - Turn your documents into a private, intelligent chatbot that runs entirely on your homelab. Learn ho...

19. [Khoj download | SourceForge.net](https://sourceforge.net/projects/khoj.mirror/) - Khoj is a desktop application to search and chat with your notes, documents, and images. It is an of...

20. [Khoj AI: Overview](https://docs.khoj.dev) - Khoj is an open source, personal AI · You can chat with it about anything. · Quickly find relevant n...

21. [Khoj - Obsidian Stats](https://www.obsidianstats.com/plugins/khoj) - Khoj supports various formats including Markdown, PDF, and Notion files, offering versatility in man...

22. [Khoj: An AI powered Search Assistant for you Second Brain](https://forum.obsidian.md/t/khoj-an-ai-powered-search-assistant-for-you-second-brain/53756) - Overview: Khoj is a fast, private, AI powered search assistant for Obsidian. Background: The Khoj Ob...

23. [Semantic search for Obsidian - Smart Connections](https://smartconnections.app/semantic-search/) - Smart Lookup gives you semantic search inside Obsidian so your vault can answer questions even when ...

24. [Smart Connections for Obsidian: Local-First Semantic Search](https://smartconnections.app/smart-connections/) - Step 1. Install. Install Smart Connections from Obsidian Community Plugins. · Step 2. Open Connectio...

25. [Adding AI to your Obsidian Notes with SmartConnections and CoPilot](https://effortlessacademic.com/adding-ai-to-your-obsidian-notes-with-smartconnections-and-copilot/) - These tools leverage semantic search and AI-assisted editing to help you quickly find, manage, and r...

26. [Arxiv Semantic Search - Apify](https://apify.com/draouadmohamed/arxiv-semantic-search) - Scrape arXiv papers by category and find relevant research using AI-powered semantic search. Get pap...

27. [How To Use Zotero In Obsidian To Simplify Research + ... - YouTube](https://www.youtube.com/watch?v=ScXGpZRZ7Ck) - ... research papers, helping you make connections, find similar work, and generally speed up & deepe...

28. [Building napkin - a memory system for agents - /dev/michael](https://michaellivs.com/blog/building-napkin-memory-system-for-agents/) - napkin takes a different approach entirely, instead of vector similarity, give the big model a map o...

29. [Sounds Authentic: How Notebook LLM turned a Report into a Podcast](https://makespaceforgrowth.com/2025/06/20/ai-notebook-llm/) - Sara Vicente Barreto used Notebook LLM to convert a dense NGO report into a conversational podcast—n...

30. [[PDF] Evaluating NotebookLM's Audio Overviews of Scientific Articles](https://www.diva-portal.org/smash/get/diva2:1985496/FULLTEXT01.pdf) - This study explores how well these. AI-generated podcasts represent academic research based on feedb...

31. [NotebookLM: The Complete Guide - Wonder Tools - Substack](https://wondertools.substack.com/p/notebooklm-the-complete-guide) - NotebookLM is the most useful free AI tool of 2025. It has twin superpowers. You can use it to find,...

32. [GitHub - Michaelliv/napkin: Knowledge system for agents. Local-first ...](https://github.com/Michaelliv/napkin) - Knowledge system for agents. Local-first, file-based, progressively disclosed. Every great idea star...

