# Resume / Skills Profile

## Summary

Aditya Dawadikar — Software Engineer pursuing a Master's in Computer Science, with 1+ years of experience in AI Inference and Training Infrastructure and 2+ years as an AI developer. Experienced in Python, scalable ML inference & training pipelines, RAG, agentic AI systems, and model evaluation. Based in San Jose, CA.

Contact: mail.aditya.dawadikar@gmail.com | github.com/Aditya-Dawadikar | linkedin.com/in/aditya-dawadikar

## Skills

- **Languages**: Python, TypeScript, JavaScript, Go, Java
- **ML Infrastructure**: vLLM, NCCL, Triton, GPU accelerators, CUDA, Vertex AI, AWS Bedrock, Apache Spark, model deployment, data processing, evaluation pipelines, experiment tracking, optimization
- **GenAI/ML**: LLMs, multimodal AI, LangGraph, LangChain, RAG, PyTorch, PEFT, LoRA, QLoRA, model evaluation, OpenEvals, Ragas, fine-tuning, Ollama, Hugging Face
- **Cloud/Systems**: GCP, AWS, Kubernetes, Docker, Redis, PostgreSQL, MongoDB, Pub/Sub, BigQuery, FastAPI
- **Observability**: OpenTelemetry, Grafana, Prometheus, Nsight

## Experience

### AI Research Assistant — San José State University, Dept of Computer Science (Aug 2025 – Present)
- Improved throughput by 8% using continuous batching, KV cache, prefix caching, and CUDA graph pre-computation for a Llama-80B model deployed with vLLM for synthetic dataset generation and knowledge distillation pipelines.
- Experimented with disaggregated serving (prefill & decode) and speculative decoding to understand vLLM internals.
- Deployed A100 GPU clusters with Kubernetes and NCCL; built automation scripts to deploy LLMs in DDP mode for training and TP mode for inference benchmarking.
- Applied LLM quantization, QLoRA, and ZeRO to reduce memory footprint during training, and FlashAttention for fast training/inference in resource-constrained environments.
- Implemented PyTorch probes to collect LLM internal signals (activations & gradients) for selective LoRA fine-tuning, achieving a 1.75x training wall-clock speedup and 1.2x inference speedup for DeBERTaV3 and Llama3 models.

### Applied AI Engineer — Quantiphi Analytics Solutions Pvt. Ltd., GCP Practice (Jan 2022 – Apr 2024)
- Built an event-driven OCR data ingestion pipeline (80% pass-through rate) using Vertex AI, Apache Spark, Pub/Sub, and BigQuery to digitize and backfill a five-year backlog of 50,000+ documents in under 6 hours.
- Automated dataset versioning and model retraining workflows using the Vertex AI SDK and BigQuery, implementing shadow-mode deployments and offline evaluation pipelines to validate new OCR models before production rollout.
- Engineered a 6-stage Apache Spark ETL pipeline on a distributed cluster processing ~1,200 records/minute for schema validation, data normalization, and reference-data enrichment before loading into BigQuery.
- Led development of an internal Human-in-the-Loop (HITL) platform using React, TypeScript, and Python, enabling analysts to validate low-confidence OCR extractions and continuously improve data quality.
- Designed centralized workflow tracking using outbox tables and event queues for stage-wise execution status and end-to-end traceability, exposing operational metrics through Google Cloud Logging, Prometheus, and Grafana.
- Built Git-based CI/CD pipelines to automate Docker image builds, testing, and deployments to Google Cloud Run, enforcing unit tests for Spark transformation stages and end-to-end HITL workflow validation.

### Projects
- **Advanced Math ReAct Agent** (LangGraph, OpenAI APIs, MCP tool calls, OpenEvals): Built a ReAct-based mathematical reasoning agent with a planner, MCP tool-calling, and structured JSON outputs, plus an automated evaluation framework using OpenEvals, Ragas, and PyTest across 30+ benchmarks. Improved tool-selection accuracy from 55% to 100% and achieved a 100% planner evaluation pass rate using LLM-as-a-judge.
- **Incremental RAG Optimization** (FAISS, Llama3, Apache Spark, Elasticsearch, ChromaDB, AWS, Ragas): Built a RAG system using ChromaDB, Elasticsearch, FAISS, a BGE reranker, FastAPI, and distributed Spark pipelines on AWS EC2/S3 for large-scale document chunking, embedding, and retrieval. Improved retrieval quality from 78% to 100% MRR via cross-encoder reranking and reduced hallucination by 50% (14%→7%) using hybrid semantic+BM25 retrieval.

## Education

- **San José State University** — Master of Science in Computer Science (Aug 2024 – May 2026). Relevant coursework: Artificial Intelligence, Natural Language Processing, Distributed Computing, Cloud Computing, Parallel Processing.

## Preferences

- Based any where in USA
- Target roles: AI Inference, Performance Engineer, ML infrastructure, GenAI/agentic systems, RAG systems — roles leveraging LLM inference optimization, distributed training/serving, and model evaluation.
- Strongest fit: roles emphasizing Python, vLLM/CUDA/GPU-level inference optimization, LangGraph/LangChain agentic systems, RAG pipelines, or cloud-native ML infrastructure (GCP/AWS/Kubernetes).
