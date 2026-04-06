# LLM-Powered Components: Key References

**Here is every reference in the provided document that directly supports implementing LLM-powered components of the local academic research knowledge base tool.**


These are filtered to only the citations tied to:
- LLM-boosted PDF extraction
- LLM-based RAG / Q&A engines (PaperQA2, AnythingLLM, Khoj, Smart Connections)
- LLM agent / compilation layer (napkin + custom LLM scripts)
- LLM-driven audio/podcast synthesis (NotebookLM-style)

I have grouped them by the exact part of the architecture they enable, with the original reference number, title/link, and why it matters for the LLM implementation.

### 1. LLM-Boosted PDF Extraction (Marker optional quality pass)
- **1 & 2**: Marker (datalab-to/marker)  
  [marker-pdf 0.3.4 - PyPI](https://pypi.org/project/marker-pdf/0.3.4/)  
  [marker-pdf - PyPI](https://pypi.org/project/marker-pdf/)  
  → Explicitly mentions “Optional LLM-boosted quality pass for ambiguous content”.

### 2. Scientific RAG Q&A Engine (PaperQA2 — the core LLM agent workflow)
- **10**: PaperQA2 GitHub (Future-House/paper-qa)  
  [GitHub - Future-House/paper-qa: High accuracy RAG for answering ...](https://github.com/future-house/paper-qa)
- **14**: PaperQA2 overview & custom RAG  
  [PaperQA2 - Custom Open-source RAG for Scientific Documents with ...](https://medevel.com/paperqa2/)
- **15**: PaperQA2 CLI & incremental indexing docs  
  [PaperQA2 | PaperQA | EdisonScientific Cookbook - GitBook](https://edisonscientific.gitbook.io/edison-cookbook/paperqa)
- **16**: PaperQA2 (mirror)  
  [PaperQA2 download | SourceForge.net](https://sourceforge.net/projects/paperqa2.mirror/)
- **17**: PaperQA2 superhuman scientific QA benchmarks  
  [PaperQA2: Superhuman scientific literature search - FutureHouse](https://www.futurehouse.org/research-announcements/wikicrow)  
  → Uses frontier LLMs (OpenAI, Anthropic, local Ollama) + Retrieval-Contextual Summarization.

(Note: Refs 11–13 are Semantic Scholar API, which PaperQA2 calls automatically for metadata; they are supporting infrastructure but not the LLM layer itself.)

### 3. Local Multi-Workspace RAG Chatbot (AnythingLLM)
- **18**: AnythingLLM private AI knowledge base  
  [Build Your Own Private AI Knowledge Base with AnythingLLM](https://www.antlatt.com/blog/anythingllm-local-knowledge-base/)  
  → Fully local, works with Ollama models, REST API for automation.

### 4. Obsidian-Native LLM Chat & Semantic Search (Khoj)
- **19**: Khoj (SourceForge mirror)  
  [Khoj download | SourceForge.net](https://sourceforge.net/projects/khoj.mirror/)
- **20**: Khoj official docs  
  [Khoj AI: Overview](https://docs.khoj.dev)
- **21**: Khoj Obsidian plugin stats  
  [Khoj - Obsidian Stats](https://www.obsidianstats.com/plugins/khoj)
- **22**: Khoj forum / Obsidian integration  
  [Khoj: An AI powered Search Assistant for you Second Brain](https://forum.obsidian.md/t/khoj-an-ai-powered-search-assistant-for-you-second-brain/53756)  
  → Supports local or cloud LLMs, runs inside Obsidian vault.

### 5. On-Device Semantic Search (Smart Connections — embedding-based LLM retrieval)
- **23**: Smart Connections semantic search  
  [Semantic search for Obsidian - Smart Connections](https://smartconnections.app/semantic-search/)
- **24**: Smart Connections local-first  
  [Smart Connections for Obsidian: Local-First Semantic Search](https://smartconnections.app/smart-connections/)
- **25**: Smart Connections + AI editing in Obsidian  
  [Adding AI to your Obsidian Notes with SmartConnections and CoPilot](https://effortlessacademic.com/adding-ai-to-your-obsidian-notes-with-smartconnections-and-copilot/)

### 6. LLM Agent Navigation & Wiki Compilation Layer (napkin)
- **28**: Building napkin (memory system for agents)  
  [Building napkin - a memory system for agents - /dev/michael](https://michaellivs.com/blog/building-napkin-memory-system-for-agents/)
- **32**: napkin GitHub  
  [GitHub - Michaelliv/napkin: Knowledge system for agents. Local-first ...](https://github.com/Michaelliv/napkin)  
  → Designed explicitly as the “agent-native knowledge layer” that LLMs navigate via taxonomy instead of vectors.

### 7. LLM Audio / Podcast Mode (NotebookLM-style synthesis)
- **29**: NotebookLM podcast from reports  
  [Sounds Authentic: How Notebook LLM turned a Report into a Podcast](https://makespaceforgrowth.com/2025/06/20/ai-notebook-llm/)
- **30**: Evaluation of NotebookLM Audio Overviews of scientific articles (PDF)  
  [[PDF] Evaluating NotebookLM's Audio Overviews of Scientific Articles](https://www.diva-portal.org/smash/get/diva2:1985496/FULLTEXT01.pdf)
- **31**: NotebookLM complete guide  
  [NotebookLM: The Complete Guide - Wonder Tools - Substack](https://wondertools.substack.com/p/notebooklm-the-complete-guide)

---

**Implementation takeaway (directly from the document):**  
The LLM-heavy parts of the tool are:
- **PaperQA2** (CLI RAG agent) + **napkin** (agent navigation) + custom Python script that calls a frontier LLM (Claude/GPT-4o) to compile the `wiki/` layer.
- Everything can run 100 % local with Ollama models.
- The recommended per-project pipeline (raw → md → zotero-notes → wiki) is explicitly driven by LLM compilation after Marker/Docling extraction.

These 18 references (1–2, 10, 14–25, 28–32) are the complete set you need to implement the LLM-powered research tool described in the file. All other references (3–9, 11–13, 26–27) are for PDF parsing, reference management, or non-LLM discovery and are not required for the LLM layer itself.