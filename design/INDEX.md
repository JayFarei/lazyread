# Lazyread — Design Index

Lazyread is a Mac-first, local listening library in which an agent skill performs document-aware orchestration and a UVX-distributed runtime provides deterministic installation, narration, storage, serving, and lifecycle management.

---

## The plan

**[lazyread-system-plan.md](lazyread-system-plan.md)** — The implementation-facing system plan. Start here.

The plan replaces one generated application per article with one managed runtime and a durable article library. It preserves the skill as a first-class product layer: the skill understands and enriches documents, while the runtime makes those decisions reproducible and operationally safe.

---

## Materials

| Document | What you will learn |
|---|---|
| **[production-run-2026-07-14.md](materials/production-run-2026-07-14.md)** | What the 108-minute arXiv paper taught us about throughput, memory, disk use, progress, scientific content, alignment recovery, mobile rendering, and full-track preloading. |
| **[design-decisions-log.md](materials/design-decisions-log.md)** | The decisions that now define the product: skill/runtime ownership, UVX packaging, one shared library, two-tier process lifecycle, single-job narration, validation gates, and Apple Silicon scope. |
| **[requirements-evolution.md](materials/requirements-evolution.md)** | How the request evolved from a one-off listening page into a portable local product, and which requirements came from hands-on use rather than initial speculation. |

---

## Quick reference

**“Why is the skill still necessary if there is a CLI?”** — See [Skill and runtime are complementary](lazyread-system-plan.md#skill-and-runtime-are-complementary).

**“What does the user install?”** — See [Distribution and installation](lazyread-system-plan.md#distribution-and-installation).

**“Who installs and unloads the local models?”** — See [Two-tier lifecycle](lazyread-system-plan.md#two-tier-lifecycle).

**“How are Defuddle and scientific-paper cleanup handled?”** — See [Document pipeline](lazyread-system-plan.md#document-pipeline).

**“How does progress survive a refresh or agent handoff?”** — See [Persisted jobs and progress](lazyread-system-plan.md#persisted-jobs-and-progress).

**“How much time, memory, and disk does a long paper need?”** — See [production-run-2026-07-14.md](materials/production-run-2026-07-14.md).

**“What happens when alignment or validation fails?”** — See [Validation and repair](lazyread-system-plan.md#validation-and-repair).

**“How do we migrate the readers already generated?”** — See [Implementation sequence](lazyread-system-plan.md#implementation-sequence).

**“Which choices remain open?”** — See [Open decisions](lazyread-system-plan.md#open-decisions).
