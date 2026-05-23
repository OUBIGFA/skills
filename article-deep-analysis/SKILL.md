---
name: article-deep-analysis
description: Use when the user asks to deeply analyze an article, essay, post, speech, report, or long-form content; requests a professional content analyst; asks for analysis by layers such as core content, background context, critical review, value extraction, or writing techniques; or provides a prompt asking to analyze an article according to a structured framework.
---

# Article Deep Analysis

Use this skill to produce a rigorous, structured analysis of an article or similar text. The goal is to explain what the piece says, why it was written, where its reasoning is strong or weak, and what readers can reuse from it.

## Inputs

The user may provide:

- The full article text.
- A link or source reference.
- A title plus excerpt.
- A target audience or reader role.
- A custom analysis framework.

If the article text is missing and the user only provides a link or source, retrieve or inspect the source when tools are available. If the source cannot be accessed, ask the user for the article text.

If target reader roles are written as placeholders such as `[目标读者角色1]` and `[目标读者角色2]`, infer useful roles from the article when possible and state the inference. If no reliable inference can be made, use:

- 普通读者
- 内容创作者或研究者

## Output Language

Unless the user asks otherwise, answer in Simplified Chinese.

## Analysis Framework

Follow the user's custom framework when one is provided. If the user asks for deep article analysis without a custom framework, use this structure.

### 一、核心内容（搞清楚“是什么”）

1. 文章的核心论点是什么？用一句话概括。
2. 作者用了哪些关键概念？这些概念是怎么定义的？
3. 文章的结构是什么？论证是怎么展开的？
4. 有哪些具体案例或证据支撑观点？

### 二、背景语境（理解“为什么”）

1. 作者是谁？他的背景、身份、立场是什么？
2. 这篇文章是在什么背景下写的？在回应什么现象或争论？
3. 作者想解决什么问题？想影响谁？
4. 作者的底层假设是什么？有哪些没说出来的前提？

### 三、批判性审视

1. 有人会怎么反驳这个观点？主要的反对意见可能是什么？
2. 作者的论证有没有漏洞、跳跃或偏颇之处？
3. 这个观点在什么情况下成立？什么情况下不成立？边界在哪里？
4. 作者有没有刻意回避或淡化什么问题？

### 四、价值提取

1. 作者提出了什么可复用的思考框架或方法论？
2. 对于目标读者角色 1，能从中学到什么？
3. 对于目标读者角色 2，能从中学到什么？
4. 这篇文章可能改变读者的什么认知？

### 五、写作技巧分析（可选）

Include this section when the user asks for it, when the article is clearly persuasive or literary, or when writing craft is relevant.

1. 文章的标题、开头、结尾是怎么设计的？
2. 作者用了什么技巧让文章有说服力？
3. 这篇文章的写法有什么值得学习的地方？

## Quality Rules

- Be specific and evidence-based. Avoid generic praise or vague summaries.
- Distinguish between what the article explicitly says, what can be reasonably inferred, and what is unknown.
- If information is insufficient for a question, say so clearly and explain what is missing.
- Do not invent the author's identity, background, publication context, or external facts.
- When using external facts, cite the source or explain that it is an inference from the article.
- Preserve the framework's numbered structure so the user can scan the answer easily.
- Keep the analysis balanced: explain the author's strongest case before criticizing it.
- Prefer clear, plain language over academic jargon.

## Workflow

1. Identify the article, source, author, date, and target audience if available.
2. Read for the thesis, key concepts, structure, evidence, and implied assumptions.
3. Separate direct evidence from interpretation.
4. Analyze likely counterarguments and boundary conditions.
5. Extract reusable methods, reader-specific lessons, and potential shifts in understanding.
6. If writing analysis is included, examine the title, opening, ending, narrative structure, examples, contrast, pacing, and rhetorical choices.
7. Produce the final answer in the requested framework.

