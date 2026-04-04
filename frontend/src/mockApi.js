// mockApi.js — Demo mode for Synapse. No backend required.
// Mirrors the same function signatures as api.js.

// ---------------------------------------------------------------------------
// Module-level mutable state
// ---------------------------------------------------------------------------

let state = {
  notebookStatus: "forming",
  sources: [],
  edges: [],
};

let intervalRef = null;

// ---------------------------------------------------------------------------
// Source / edge data definitions
// ---------------------------------------------------------------------------

const ALL_SOURCES = [
  {
    id: "demo-source-0",
    title: "Large Language Model",
    url: "https://en.wikipedia.org/wiki/Large_language_model",
    source_type: "seed",
    summary:
      "Wikipedia's comprehensive overview of large language models, covering architecture, training methods, capabilities, and major model families including GPT, BERT, and LLaMA.",
  },
  {
    id: "demo-source-1",
    title: "Attention Is All You Need",
    url: "https://arxiv.org/abs/1706.03762",
    source_type: "webpage",
    summary:
      "The landmark 2017 paper from Google Brain that introduced the Transformer architecture, eliminating recurrence and relying entirely on attention mechanisms for sequence modeling.",
  },
  {
    id: "demo-source-2",
    title: "The Illustrated Transformer",
    url: "https://jalammar.github.io/illustrated-transformer",
    source_type: "webpage",
    summary:
      "Jay Alammar's acclaimed visual walkthrough of the Transformer architecture, breaking down self-attention, positional encoding, and the encoder-decoder stack with clear diagrams.",
  },
  {
    id: "demo-source-3",
    title: "GPT-4 Technical Report",
    url: "https://arxiv.org/abs/2303.08774",
    source_type: "webpage",
    summary:
      "OpenAI's technical report on GPT-4, detailing its multimodal capabilities, training approach, and performance across academic benchmarks and professional exams.",
  },
  {
    id: "demo-source-4",
    title: "BERT: Pre-training of Deep Bidirectional Transformers",
    url: "https://arxiv.org/abs/1810.04805",
    source_type: "webpage",
    summary:
      "Google's 2018 paper introducing BERT, which uses masked language modeling and next sentence prediction to learn bidirectional representations from unlabeled text.",
  },
  {
    id: "demo-source-5",
    title: "Introducing Claude",
    url: "https://www.anthropic.com/news/introducing-claude",
    source_type: "webpage",
    summary:
      "Anthropic's announcement of Claude, describing its Constitutional AI training approach and focus on building AI systems that are helpful, harmless, and honest.",
  },
  {
    id: "demo-source-6",
    title: "ChatGPT: Optimizing Language Models for Dialogue",
    url: "https://openai.com/blog/chatgpt",
    source_type: "webpage",
    summary:
      "OpenAI's blog post introducing ChatGPT, explaining how reinforcement learning from human feedback (RLHF) was used to fine-tune GPT for conversational interaction.",
  },
  {
    id: "demo-source-7",
    title: "Gemini: A Family of Highly Capable Multimodal Models",
    url: "https://deepmind.google/technologies/gemini",
    source_type: "webpage",
    summary:
      "Google DeepMind's introduction of Gemini, a natively multimodal model family trained on text, images, audio, and video, with variants ranging from Ultra to Nano.",
  },
  {
    id: "demo-source-8",
    title: "What Are Large Language Models?",
    url: "https://blogs.nvidia.com/blog/what-are-large-language-models-used-for",
    source_type: "webpage",
    summary:
      "NVIDIA's accessible explainer on what LLMs are, how they work, and practical applications across industries including healthcare, finance, and software development.",
  },
  {
    id: "demo-source-9",
    title: "The Age of AI Has Begun",
    url: "https://www.gatesnotes.com/The-Age-of-AI-Has-Begun",
    source_type: "webpage",
    summary:
      "Bill Gates' essay arguing that AI is the most important technological advance since the graphical user interface, with transformative potential for global health and education.",
  },
  {
    id: "demo-source-10",
    title: "How ChatGPT Actually Works",
    url: "https://www.assemblyai.com/blog/how-chatgpt-actually-works",
    source_type: "webpage",
    summary:
      "AssemblyAI's technical deep-dive into ChatGPT's training pipeline, covering pretraining, supervised fine-tuning, reward modeling, and the RLHF process step by step.",
  },
  {
    id: "demo-source-11",
    title: "Stanford AI Index Report 2024",
    url: "https://aiindex.stanford.edu/report",
    source_type: "webpage",
    summary:
      "Stanford's annual report tracking AI progress across research, education, economy, and policy, providing data-driven analysis of the state of artificial intelligence worldwide.",
  },
];

// NOTE: DocumentWeb.jsx and FormationScreen.jsx both filter edges using
// e.source_a and e.source_b (not source_id / target_id).
const ALL_EDGES = [
  { id: "e1",  source_a: "demo-source-0",  source_b: "demo-source-1",  relationship: "Foundational architecture",             similarity: 0.91 },
  { id: "e2",  source_a: "demo-source-0",  source_b: "demo-source-2",  relationship: "Visual explainer of core concepts",     similarity: 0.87 },
  { id: "e3",  source_a: "demo-source-0",  source_b: "demo-source-8",  relationship: "Introductory overview",                 similarity: 0.83 },
  { id: "e4",  source_a: "demo-source-1",  source_b: "demo-source-2",  relationship: "Explains transformer in detail",        similarity: 0.85 },
  { id: "e5",  source_a: "demo-source-1",  source_b: "demo-source-4",  relationship: "Both foundational transformer papers",  similarity: 0.82 },
  { id: "e6",  source_a: "demo-source-2",  source_b: "demo-source-10", relationship: "Technical walkthrough comparison",      similarity: 0.77 },
  { id: "e7",  source_a: "demo-source-2",  source_b: "demo-source-4",  relationship: "Explains BERT's architecture",         similarity: 0.79 },
  { id: "e8",  source_a: "demo-source-3",  source_b: "demo-source-6",  relationship: "Same model family",                    similarity: 0.88 },
  { id: "e9",  source_a: "demo-source-3",  source_b: "demo-source-7",  relationship: "Frontier model comparison",            similarity: 0.75 },
  { id: "e10", source_a: "demo-source-4",  source_b: "demo-source-1",  relationship: "BERT built on transformer",            similarity: 0.82 },
  { id: "e11", source_a: "demo-source-5",  source_b: "demo-source-6",  relationship: "Competing frontier labs",              similarity: 0.72 },
  { id: "e12", source_a: "demo-source-5",  source_b: "demo-source-7",  relationship: "Competing frontier labs",              similarity: 0.70 },
  { id: "e13", source_a: "demo-source-6",  source_b: "demo-source-10", relationship: "Both explain ChatGPT internals",       similarity: 0.81 },
  { id: "e14", source_a: "demo-source-7",  source_b: "demo-source-3",  relationship: "Frontier model comparison",            similarity: 0.75 },
  { id: "e15", source_a: "demo-source-8",  source_b: "demo-source-0",  relationship: "References Wikipedia overview",        similarity: 0.80 },
  { id: "e16", source_a: "demo-source-9",  source_b: "demo-source-11", relationship: "Societal impact of AI",                similarity: 0.68 },
  { id: "e17", source_a: "demo-source-10", source_b: "demo-source-1",  relationship: "Deep dive references attention paper", similarity: 0.74 },
  { id: "e18", source_a: "demo-source-11", source_b: "demo-source-9",  relationship: "Cross-reference societal analysis",    similarity: 0.65 },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSource(def, status) {
  return { ...def, status };
}

function setSourceStatuses(ids, status) {
  state.sources = state.sources.map((s) =>
    ids.includes(s.id) ? { ...s, status } : s
  );
}

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------

function startStateMachine() {
  const startTime = Date.now();
  const transitioned = new Set();

  intervalRef = setInterval(() => {
    const elapsed = Date.now() - startTime;

    // t=2s — seed ready; add discovered sources as pending
    if (elapsed >= 2000 && !transitioned.has("t2")) {
      transitioned.add("t2");
      setSourceStatuses(["demo-source-0"], "ready");
      const discovered = ALL_SOURCES.slice(1).map((def) => makeSource(def, "pending"));
      state.sources = [state.sources[0], ...discovered];
    }

    // t=5s — sources 1-5 → crawling
    if (elapsed >= 5000 && !transitioned.has("t5")) {
      transitioned.add("t5");
      setSourceStatuses(
        ["demo-source-1", "demo-source-2", "demo-source-3", "demo-source-4", "demo-source-5"],
        "crawling"
      );
    }

    // t=8s — sources 6-11 → crawling; sources 1-3 → processing
    if (elapsed >= 8000 && !transitioned.has("t8")) {
      transitioned.add("t8");
      setSourceStatuses(
        ["demo-source-6", "demo-source-7", "demo-source-8", "demo-source-9", "demo-source-10", "demo-source-11"],
        "crawling"
      );
      setSourceStatuses(
        ["demo-source-1", "demo-source-2", "demo-source-3"],
        "processing"
      );
    }

    // t=11s — sources 1-3 → ready; sources 4-8 → processing
    if (elapsed >= 11000 && !transitioned.has("t11")) {
      transitioned.add("t11");
      setSourceStatuses(
        ["demo-source-1", "demo-source-2", "demo-source-3"],
        "ready"
      );
      setSourceStatuses(
        ["demo-source-4", "demo-source-5", "demo-source-6", "demo-source-7", "demo-source-8"],
        "processing"
      );
    }

    // t=14s — sources 4-8 → ready; sources 9-11 → processing
    if (elapsed >= 14000 && !transitioned.has("t14")) {
      transitioned.add("t14");
      setSourceStatuses(
        ["demo-source-4", "demo-source-5", "demo-source-6", "demo-source-7", "demo-source-8"],
        "ready"
      );
      setSourceStatuses(
        ["demo-source-9", "demo-source-10", "demo-source-11"],
        "processing"
      );
    }

    // t=17s — sources 9-11 → ready; inject all edges; notebook ready; stop
    if (elapsed >= 17000 && !transitioned.has("t17")) {
      transitioned.add("t17");
      setSourceStatuses(
        ["demo-source-9", "demo-source-10", "demo-source-11"],
        "ready"
      );
      state.edges = [...ALL_EDGES];
      state.notebookStatus = "ready";
      clearInterval(intervalRef);
      intervalRef = null;
    }
  }, 100);
}

// ---------------------------------------------------------------------------
// Exported API functions
// ---------------------------------------------------------------------------

export function createNotebook(_data) {
  // Clear any running interval from a previous demo session
  if (intervalRef !== null) {
    clearInterval(intervalRef);
    intervalRef = null;
  }

  // Reset state
  state = {
    notebookStatus: "forming",
    sources: [makeSource(ALL_SOURCES[0], "processing")],
    edges: [],
  };

  startStateMachine();

  return Promise.resolve({ id: "demo-notebook-1" });
}

export function getNotebook(_id) {
  return Promise.resolve({
    id: "demo-notebook-1",
    title: "How Large Language Models Work",
    status: state.notebookStatus,
    sources: [...state.sources],
    edges: [...state.edges],
  });
}

export function listSources(_notebookId) {
  return Promise.resolve([...state.sources]);
}

export function addSource(_notebookId, { url, title, sourceType = "webpage" }) {
  const newId = "demo-source-added-" + Date.now();
  const newSource = {
    id: newId,
    title: title || url,
    url,
    source_type: sourceType,
    summary:
      "A user-added source providing additional context and perspectives relevant to the notebook topic.",
    status: "pending",
  };

  state.sources = [...state.sources, newSource];

  // pending → crawling after 2s
  setTimeout(() => {
    state.sources = state.sources.map((s) =>
      s.id === newId ? { ...s, status: "crawling" } : s
    );
    // crawling → processing after 3s more
    setTimeout(() => {
      state.sources = state.sources.map((s) =>
        s.id === newId ? { ...s, status: "processing" } : s
      );
      // processing → ready after 3s more; add 2 connecting edges
      setTimeout(() => {
        state.sources = state.sources.map((s) =>
          s.id === newId ? { ...s, status: "ready" } : s
        );
        const edgeBase = Date.now();
        const newEdges = [
          {
            id: "e-added-" + edgeBase + "-a",
            source_a: newId,
            source_b: "demo-source-0",
            relationship: "Related to core topic",
            similarity: 0.70,
          },
          {
            id: "e-added-" + edgeBase + "-b",
            source_a: newId,
            source_b: "demo-source-1",
            relationship: "Shares foundational concepts",
            similarity: 0.65,
          },
        ];
        state.edges = [...state.edges, ...newEdges];
      }, 3000);
    }, 3000);
  }, 2000);

  return Promise.resolve({ id: newId });
}

export function getChatHistory(_notebookId) {
  return Promise.resolve([
    {
      role: "user",
      content: "What is this notebook about?",
    },
    {
      role: "assistant",
      content:
        "This notebook explores **Large Language Models (LLMs)** — the AI systems behind tools like ChatGPT, Claude, and Gemini. It covers the foundational Transformer architecture, key training techniques like RLHF, and perspectives from major AI labs and researchers. The 12 sources range from technical papers to accessible explainers and societal impact analysis.",
      citations: [
        { source_id: "demo-source-0" },
        { source_id: "demo-source-1" },
        { source_id: "demo-source-2" },
      ],
    },
  ]);
}

export function sendChatMessage(_notebookId, message) {
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve(buildChatResponse(message));
    }, 1200);
  });
}

// ---------------------------------------------------------------------------
// Chat response logic
// ---------------------------------------------------------------------------

function buildChatResponse(message) {
  const lc = message.toLowerCase();

  if (/summarize|overview|about/.test(lc)) {
    return {
      role: "assistant",
      content:
        "This notebook covers the landscape of Large Language Models, from the foundational Transformer architecture to real-world deployments by OpenAI, Anthropic, and Google. Key themes include attention mechanisms, RLHF training, and the societal implications of increasingly capable AI systems.",
      citations: [
        { source_id: "demo-source-0" },
        { source_id: "demo-source-1" },
        { source_id: "demo-source-2" },
        { source_id: "demo-source-8" },
      ],
    };
  }

  if (/transformer|attention/.test(lc)) {
    return {
      role: "assistant",
      content:
        "The Transformer architecture, introduced in 'Attention Is All You Need' (2017), replaced recurrent networks with self-attention mechanisms. This allowed massively parallel training and became the foundation for every major LLM including GPT-4, BERT, Claude, and Gemini.",
      citations: [
        { source_id: "demo-source-1" },
        { source_id: "demo-source-2" },
      ],
    };
  }

  if (/train|learn|how does it work/.test(lc)) {
    return {
      role: "assistant",
      content:
        "LLMs are trained in stages: first on vast text corpora via next-token prediction (pretraining), then fine-tuned on curated examples (SFT), and finally aligned with human preferences using reinforcement learning from human feedback (RLHF). GPT-4 and ChatGPT both follow this pipeline.",
      citations: [
        { source_id: "demo-source-3" },
        { source_id: "demo-source-4" },
        { source_id: "demo-source-6" },
      ],
    };
  }

  if (/compan|who makes|openai|google|anthropic/.test(lc)) {
    return {
      role: "assistant",
      content:
        "The leading LLM developers are OpenAI (GPT-4, ChatGPT), Anthropic (Claude), and Google DeepMind (Gemini). Each takes a somewhat different approach: OpenAI pioneered RLHF-based alignment, Anthropic developed Constitutional AI, and Google leverages its multimodal research heritage.",
      citations: [
        { source_id: "demo-source-5" },
        { source_id: "demo-source-6" },
        { source_id: "demo-source-7" },
      ],
    };
  }

  if (/future|risk|impact|society/.test(lc)) {
    return {
      role: "assistant",
      content:
        "AI researchers and public intellectuals broadly agree that LLMs represent a transformative moment. The Stanford AI Index and Bill Gates both highlight rapid capability growth, while raising questions about access, misinformation, labor displacement, and the need for governance frameworks.",
      citations: [
        { source_id: "demo-source-9" },
        { source_id: "demo-source-11" },
      ],
    };
  }

  // Fallback — pick up to 3 random ready sources for citations
  const readySources = state.sources.filter((s) => s.status === "ready");
  const shuffled = [...readySources].sort(() => Math.random() - 0.5);
  const citationSources = shuffled.slice(0, 3);

  return {
    role: "assistant",
    content:
      "Based on the sources in this notebook, LLMs are complex systems that combine scale, architecture innovation, and alignment techniques. Is there a specific aspect — architecture, training, companies, or societal impact — you'd like to explore further?",
    citations: citationSources.map((s) => ({ source_id: s.id })),
  };
}
