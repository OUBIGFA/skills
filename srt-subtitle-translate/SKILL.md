---
name: srt-subtitle-translate
description: Translate non-Chinese subtitle files into concise, publication-grade Simplified Chinese while preserving cue order and timing structure as faithfully as possible. Use when Codex needs to translate or polish subtitle files such as `.srt`, `.txt`, `.vtt`, `.ass`, `.ssa`, `.sub`, subtitle blocks, or transcript-like timed captions into Chinese with filler-word cleanup, terminology preservation, symbol normalization, subtitle-safe formatting, and optional local re-segmentation with sequential renumbering.
---

# SRT Subtitle Translate

Translate subtitle content into concise Simplified Chinese while preserving subtitle timing structure as faithfully as possible. Preserve cue order and reading flow, and when source segmentation is clearly unsuitable for Chinese translation, allow preprocessing to re-segment neighboring subtitle blocks, redistribute timestamps to match the corrected sentence boundaries, and then renumber the rebuilt cues sequentially from top to bottom.

## Highest-Priority Rule

- Highest priority: once the user starts an end-to-end subtitle task, you must continue all the way to the final delivered subtitle file without stopping for procedural questions, permission checks, preview pauses, sample-only output, or intermediate confirmation requests. You must run the whole workflow through preprocessing, translation, validation, merge, final review, final polish, and final file write unless a concrete blocker makes completion impossible.
- Highest priority: for an end-to-end subtitle request, not producing the final output file counts as task failure unless a concrete blocker prevents completion.
- Highest priority: do not ask the user whether to continue with preprocessing, chunking, translating, merge, review, polish, cleanup, overwrite, or final delivery. If the task is executable, finish it.
- Highest priority: if chunking or subagents are used, that does not create a stopping point. You must still drive the task through merge, master-pass review, and final output delivery in the same execution flow.
- Highest priority: subtitle translation itself must be performed by the language model running this task. Do not search for, probe for, install, call, or switch to any external translator, translation website, translation API, browser translation flow, or third-party translation library in place of doing the translation directly.
- Highest priority: never start a subtitle task by checking whether a separate translator exists. Do not run dependency discovery, package probing, `pip show`, `pip install`, `importlib` checks, browser lookups, or local-tool scouting for translators. Start the actual subtitle workflow instead.

## Execution Boundary

- Prefer translation inside the current Codex conversation when the file is small enough to finish safely in one pass.
- Prefer one-pass full-file translation when the subtitle corresponds to a short video, especially when the full runtime is within about 30 minutes and the file can be handled safely in one conversation without truncation.
- If the subtitle file is large, keep working inside the current execution boundary by chunking and translating sequentially unless an already-permitted parallel path exists in the current environment.
- If subagents are used, treat their chunk outputs as draft translations that require a final master-pass review against the original source before delivery.
- Do not proactively search for, probe for, install, or switch to external translation services, online translation APIs, third-party translation websites, or ad hoc translation libraries just because a subtitle translation task has started.
- Do not present external translation services as a fallback, suggestion, unblocker, or user choice. The correct behavior is to have the model itself perform the translation and use local scripts only for preprocessing, splitting, validation, merge, and file orchestration.
- Local helper scripts may preprocess, split, validate, and merge subtitle files. The lack of a separate translation library is not a blocker because the model itself is the translator.

## Hard Constraints

- The `Highest-Priority Rule` overrides every lower-priority workflow preference in this skill.
- Treat a subtitle translation request as an end-to-end execution task, not as a checkpointed drafting task.
- Once processing starts, continue until the final translated subtitle file has been written successfully, or until a real blocker prevents further progress.
- Do not reframe the task as blocked merely because the helper scripts do not themselves translate text.
- Do not treat the absence of an automatic translation script or translation package as a reason to go hunting for external translators. The model itself must do the translation work.
- Do not execute translator-discovery commands. Examples of forbidden behavior include checking translation packages, attempting translator installs, or scanning the machine for translation-specific tools before translating.
- Do not pause mid-work to ask whether you should continue chunking, continue translating, merge the chunks, or finish the file.
- Do not stop merely to report progress when untranslated chunks still remain and no blocker exists.
- Do not ask for confirmation between preprocessing, chunking, translating, validation, merge, cleanup, or final file write.
- The default completion condition is: all chunks translated, validated, merged, and the final sibling `-CN` subtitle file written.
- Do not stop at preview slices, sample output, partial subtitle ranges, or style-check excerpts unless the user explicitly asks for a preview-only run.
- Only interrupt this flow when blocked by a concrete issue such as missing source files, write failures, malformed subtitle structure that cannot be safely repaired, or an explicit user instruction to stop or change scope.
- Never tell the user that an external translation API or service is needed when the request is otherwise executable with this skill.
- Never replace model translation with an external translator when the task is otherwise executable with this skill.

## Workflow

1. Detect whether the input is standard SRT or SRT-like subtitle blocks.
2. If the file extension is `.txt` or another generic text format, inspect the content and treat it as subtitles when it follows numbered timed blocks.
3. Decide whether the subtitle boundaries are already translation-friendly. If not, preprocess first by merging or splitting neighboring cues into more natural sentence units.
4. After that decision, enter the translation workflow immediately. Do not insert any translator-discovery phase, dependency-check phase, package-check phase, or external-tool scouting phase.
5. Before translating, pre-read the full subtitle file once to identify recurring names, product names, plugin names, UI labels, abbreviations, and other terms that must stay consistent across the whole job.
6. If useful, generate a temporary consistency glossary that records candidate terms, intended Chinese renderings, and any rules such as “keep in English” or “translate only on first mention”.
7. When preprocessing changes boundaries, redistribute timestamps proportionally so the new timing matches the new sentence segmentation and still follows playback order.
8. After preprocessing, run a whole-file boundary audit instead of trusting local fixes blindly. Scan the rebuilt subtitle for suspicious break classes such as noun-phrase splits, phrasal-verb splits, subject-modal splits, determiner-to-noun breaks, preposition-object breaks, dangling conjunction tails, and over-compressed action chains; then normalize those classes before translation.
9. Before translating, estimate whether the full subtitle file is too large for one stable pass. If the runtime is within about 30 minutes and the subtitle can be completed safely in one conversation, prefer translating the whole file directly instead of chunking. If chunking is required, prefer runtime-based chunks of about 20 minutes each.
10. When chunking is needed, continue the job by default. Do not stop just to ask whether chunk-by-chunk translation is acceptable.
11. If a permitted parallel path exists in the current environment, assign disjoint contiguous cue ranges to it in parallel. Otherwise, continue sequentially with the same chunk boundaries in the current conversation.
12. Give every chunk translator the same terminology decisions, punctuation rules, and formatting constraints before translation starts.
13. If the full translation cannot be completed safely in a single response, continue across multiple turns or responses using the same chunk manifest until every chunk has been translated and merged.
14. Track progress through the existing chunk files and `manifest.json`, and resume from the next unfinished `NNN.translated.srt` instead of restarting the whole file.
15. Translate only subtitle text.
16. Reuse the same term decisions across every chunk so names and terminology remain stable from start to finish.
17. Compress filler words, hesitations, and repetitive fragments into the shortest faithful Chinese phrasing.
18. Preserve technical terms, product names, and important English terms when forced translation would reduce accuracy.
19. Normalize symbols, units, and mixed Chinese/English spacing before returning the final subtitle text.
20. After chunked translation, validate that every translated chunk preserves the same block count, cue numbering, and timestamps as its source chunk, then merge all translated chunks back into one final subtitle file.
21. If subagents were used, the main conversation must compare the merged Chinese subtitle against the original source subtitle and run a final master-pass review before delivery.
22. The mandatory master-pass review must catch and fix terminology drift, tone drift, mistranslations caused by chunk-local context loss, awkward literal phrasing, missing text, duplicated text, formatting drift, and subtitle lines that are accurate but still not natural Chinese.
23. Merge validation alone is never sufficient when subagents were used. Completion requires both successful merge and a final master-pass polish by the main conversation.
24. After merge, run one final global consistency and polish pass locally to normalize terminology drift, punctuation differences, wording mismatches, and style inconsistencies across chunks.
25. After the final subtitle file is written successfully, clean up temporary consistency artifacts such as term lists or scratch glossary files unless the user explicitly asks to keep them.
26. Unless a real blocker occurs, do not emit a progress-only completion message before the validation, merge, final master-pass review, final polish pass, and cleanup steps are finished.

## Quick Start

- When the source subtitle file is noisy or inconsistently wrapped, run `scripts/preprocess_srt.py` first to normalize subtitle text while preserving timing structure.
- When sentence boundaries are obviously broken across neighboring cues, run `scripts/preprocess_srt.py --resegment-sentences` first to re-cut subtitle blocks and redistribute timestamps for translation-friendly reading.
- Before translating, read the full subtitle file once and decide the stable wording for recurring names, products, plugins, UI labels, and abbreviations.
- If the file is long or terminology-heavy, use `scripts/extract_subtitle_terms.py` to generate a temporary candidate-term list, then fill or refine the actual translations before chunk translation begins.
- Use the preprocessed file as the translation input when the original has excessive blank lines, repeated spaces, or broken line wrapping.
- If the subtitle is for a short video, especially within about 30 minutes, default to translating the whole file directly after preprocessing instead of splitting into chunks.
- When the subtitle file is large enough that one-pass translation could truncate, drift, or lose formatting, use `scripts/chunk_srt.py split` first.
- When chunking is required, prefer cutting by runtime into chunks of about 20 minutes each, then refine the boundary to a natural subtitle break.
- If a permitted parallel path exists in the current environment, translate the generated chunk files in parallel by assigning disjoint chunk ranges to it.
- If no permitted parallel path exists, translate the generated chunk files one by one in the current conversation.
- When chunking is required, proceed automatically. Do not pause merely to ask for permission to continue chunk by chunk.
- If the environment requires multiple replies to finish the whole subtitle, keep translating subsequent chunks in later replies until the final merge step is done.
- Do not surface external translation products or APIs as an alternative path. Finish the job with the current conversation and locally available workflow tools unless a parallel path is already permitted in the current environment.
- Resume from any already-finished translated chunks in the chunk folder instead of retranslating completed work.
- Keep the temporary consistency glossary beside the working subtitle or chunk folder while translating, and apply it to every chunk.
- Save each translated chunk into the same chunk folder using the matching `NNN.translated.srt` filename from `manifest.json`.
- After all chunks are translated, run `scripts/chunk_srt.py merge` to validate block counts and write the final merged subtitle file.
- After the final `-CN` file has been written and checked, delete temporary consistency files unless the user asked to preserve them.
- When writing the translated result to disk, save it in the same directory as the source subtitle file and append `-CN` before the original extension.
- If you need to persist the resegmented intermediate, save it beside the source file as `<original-name>.preprocessed<ext>`.
- In the normal full-translation workflow, keep only the latest final `-CN` result and clean temporary preprocessing artifacts after the final subtitle file is written.
- Example: `demo.srt` -> `demo-CN.srt`
- Example: `demo.txt` -> `demo-CN.txt`
- Read [references/terminology.md](references/terminology.md) when domain terms or fixed mappings matter.

## Output Contract

- Output only the translated subtitle blocks.
- Keep cue order identical to the input.
- After preprocessing, treat the resulting English subtitle blocks as the canonical translation units for the final Chinese output.
- By default, preserve the preprocessed cue boundaries exactly in the Chinese subtitle. Do not merge, split, or redistribute translated text across adjacent cues during Chinese translation just to improve Chinese phrasing.
- Only adjust Chinese word order, compression, or phrasing inside the current cue. Minor intra-cue rewriting for naturalness is allowed, but cue ownership must not change.
- Do not require rebuilt cue numbers to match the original cue numbers.
- After re-segmentation, renumber cues sequentially from top to bottom in the final output.
- Preserve timestamps exactly unless preprocessing is explicitly used to repair broken segmentation.
- Do not reorder or skip subtitle blocks.
- In chunked workflows, each translated chunk must preserve exactly the same subtitle blocks as its source chunk: same cue numbers, same timestamps, same cue order, and same block count. Only the subtitle text may change.
- Names, terminology, and first-chosen translations must remain consistent across the entire file, including across chunk boundaries.
- In subagent workflows, each subagent must own only its assigned contiguous chunk range and must not rewrite other chunks.
- In subagent workflows, merged output is never considered final until the main conversation has reviewed it against the source subtitle and completed a final polish pass.
- During preprocessing, adjacent blocks may be re-segmented and retimed when that produces more natural sentence boundaries for translation.
- Do not add explanations, notes, comments, or reasoning.
- Do not emit citation markers such as `[cite]`, `[]`, or Markdown quotes.
- Do not end translated subtitle lines with `。` or other sentence-final punctuation unless the source format absolutely requires it.
- Default to no Chinese sentence-final punctuation in subtitle text, including `。`, `！`, `？`, `；`, and similar closing marks.
- Minimize internal Chinese punctuation too. Use commas or pauses only when they materially improve subtitle readability or prevent ambiguity; do not punctuate Chinese subtitles as if they were written prose.
- If saving to a file, write the translated subtitle beside the source file and append `-CN` before the original extension.

## Translation Rules

### Clean for subtitles

- Remove filler words, hesitation sounds, and low-information fragments when they do not affect meaning.
- Rewrite broken speech into compact Chinese instead of translating every disfluency literally.
- Keep short acknowledgements only when they carry real semantic value.
- When the preprocessed English cue is grammatically incomplete, still translate it within that same cue instead of completing the thought by borrowing or moving text across cue boundaries.

### Repair segmentation when needed

- This section applies to source-side preprocessing, not to the final Chinese translation pass.
- Once preprocessing is finished, do not perform a second Chinese-side re-segmentation pass unless the user explicitly asks for rebuilt Chinese subtitle timing.
- If a sentence is split across adjacent cues in a way that is unsuitable for Chinese translation, merge the local text mentally, re-cut it at better sentence boundaries, and update local timestamps accordingly.
- Treat long pauses conservatively but not mechanically: if a later cue is still the missing tail of the same sentence, you may merge across a pause and redistribute the local timestamps so the sentence becomes complete.
- Prefer sentence-complete boundaries over arbitrary source cuts.
- Keep re-segmentation local. Adjust only the neighboring cues needed to fix the reading flow.
- Redistribute time in proportion to segment length unless the speech rhythm clearly suggests another split.
- After local rebuilding, assign fresh sequential cue numbers instead of trying to preserve original numbering.
- Avoid creating extremely short flashes; keep each rebuilt segment readable on screen.
- Do not create rebuilt cues that are too short to read comfortably. As a default rule, avoid emitting any local re-segmented subtitle whose on-screen duration would become a brief flash.
- Never isolate pure numbers, parameter values, short units, or similar configuration values into their own ultra-short rebuilt cue. Attach them to the surrounding phrase that gives them meaning, usually the preceding phrase.
- Do not allow rebuilt subtitles to remain overly long just because the sentence is grammatically complete.
- Prefer shorter subtitle units that are comfortable to read in one glance, even if that means splitting a long sentence into 2 nearby subtitle cues.
- If a single cue is already too long for subtitle reading, actively split it into 2 or more new cues even when the source did not provide empty neighboring cues.
- For long sentences without obvious full stops, prefer splitting at clause boundaries, scene-action transitions, condition/result turns, menu-action turns, or relative-clause boundaries such as `if`, `so`, `and`, `but`, `which`, `where`, `when`, and similar natural hinge points.
- If the source already contains clean full-sentence boundaries, prefer those sentence boundaries first and only split inside a sentence when that sentence itself is still too long for subtitle reading.
- Inside a long sentence, prefer breaking at completed subordinate-clause edges before cutting through the following main clause. In practice, if a temporal / conditional / explanatory clause has already closed cleanly, prefer splitting after that closure rather than later inside the main predicate.
- If a long sentence has no clean hinge point, still force a readable split at the least awkward phrase boundary instead of preserving one oversized cue.
- Do not end a rebuilt subtitle on obvious auxiliary tails or dangling scaffolds such as `we can`, `I will`, `to`, `which`, or bare conjunction tails. Prefer ending at an action-complete or thought-complete mini-unit.
- Keep coordinating or contrastive connectors with the clause they introduce. Prefer splitting before `but`, `and`, `or`, `so`, and similar linkers rather than ending the previous subtitle with a dangling connector.
- Do not split a subtitle inside a simple verb-object unit just to satisfy a length target. Avoid breaks such as `adjust / this shape`, `position / it`, `rotate / it`, or similar action-plus-object pairs unless the sentence is otherwise unreadably long.
- When a cue is only mildly long but still reads naturally as one compact action sentence, keep it intact instead of forcing a split.
- Protect noun phrases and prepositional phrases as complete reading units. Do not break between determiners and nouns, inside short modifier+noun groups, or between a preposition and its object, such as `our emitter`, `this shape`, `the can opener`, `my cam model`, `in our scene`, or similar compact phrase units.
- Protect common phrasal verbs and verb-particle groups too. Avoid breaks such as `dropped / in`, `go / back`, `turn / up`, `move / around`, or similar verb-plus-particle units when they function as one action.
- Do not split between a subject and its modal or auxiliary scaffold, such as `you / can see`, `we / will`, `it / is`, or similar short grammatical units that must be read together.
- Protect compact UI and tutorial action phrases as single reading units too, including compound object names, noun-plus-location tails, and click/drag commands such as `cam model`, `our emitter here`, `right click`, `loop selection tool`, and similar tightly bound phrase chunks.
- Protect `verb + to + infinitive` and similar complement structures too. Avoid breaks such as `prefer / to use`, `want / to bring`, `need / to change`, or similar predicate continuations that should be read as one unit.
- Protect copular scaffolds and complement clauses too. Do not split inside structures such as `what we need to do is ...`, `the point is ...`, `there is ...`, `what I want is ...`, or similar `be + complement` frames where the meaning is incomplete until the predicate continuation arrives.
- When preprocessing source subtitles for translation, treat roughly `<= 42` Latin characters per cue as the default comfort target, and use nearby empty cues or adjacent local cues to absorb overflow when possible.
- For Chinese output, prefer a much shorter reading load than the source: usually 1 to 2 short lines per cue, and avoid dense full-sentence blocks that would feel like paragraph text on screen.
- Repair false stops aggressively when needed: if the source inserts periods into obvious fragments such as orphan adjectives, orphan numbers, or trailing phrase tails, merge them back into the surrounding sentence before translation.
- Avoid nonessential orphan words after re-segmentation. Do not leave tails such as `Glossy.`, `40.`, or `can.` as standalone cues when they clearly belong to a neighboring phrase.
- Avoid orphan lead fragments too. Do not leave short front-loaded leftovers such as `Maybe...`, `Okay.`, `I really like...`, `What I need is...`, `For the next detail.`, or `To give...` as standalone rebuilt cues when they clearly belong to the following clause.
- Repair cue-internal false punctuation too, not only cross-cue splits. If the source contains forms such as `it.So`, `clean.And`, `Let's.Kind of`, or `a.Color`, first restore the implied word boundary, then decide whether the resulting fragments should stay split or be merged.
- Treat obvious ASR self-corrections and abandoned starts as disposable structure. For fragments such as `We can we'll adjust it`, keep the committed clause and drop the abandoned lead-in before translation.
- Merge broken UI or command-path noun phrases into complete units before translation when the source has split them unnaturally, such as `field condition`, `random effector`, `object`, `our sphere`, or similar menu / object / modifier names.
- When a short interjection such as `Let's see`, `Okay`, or `I guess` does not materially affect the instruction, compress or omit it in Chinese rather than preserving every conversational filler.
- During source preprocessing, do not insert forced line breaks inside a complete phrase or clause just to make a cue visually shorter.
- If a local segment is still long after cue-level resegmentation, keep it as one complete subtitle line rather than breaking it at an awkward internal point.

### Preserve meaning in technical contexts

- Preserve software names, algorithm names, abbreviations, UI labels, and branded terms in English when that is the clearest form.
- Prefer `中文（English）` on first mention only when the bilingual form materially improves clarity.
- If a recurring technical term appears many times, decide its stable translation before chunk translation starts and keep that choice everywhere unless later context proves it wrong.

### Maintain cross-file consistency

- Treat consistency as a full-file requirement, not a per-chunk requirement.
- Pre-read the whole subtitle or generate a temporary term-candidate list before translating large files.
- Prioritize consistency for person names, channel names, plugin names, product names, UI labels, menu commands, render-engine names, and repeated technical nouns.
- If a term is ambiguous, use the earliest clear context in the full subtitle to decide it before translating later chunks.
- If the best translation changes after reading more context, normalize the earlier translated chunks to the final decision before merge.
- Do not allow the same source term to drift between transliteration, free translation, and English retention unless the context truly demands a difference.

### Normalize symbols and units

- Prefer symbols over verbose wording where it improves subtitle readability.
- Use forms such as `-50`, `360°`, `20%`, `10×10`, `10~20`, `±5`.
- Keep SI unit symbols in standard form, such as `kg`, `m`, `V`, `Hz`.
- Do not translate units into long Chinese names unless the context clearly requires it.

### Apply mixed-script spacing

- Insert one half-width space between Chinese and adjacent English words or Arabic numerals.
- Do not insert spaces between numbers and unit symbols, such as `50kg` or `220V`.

## Structural Error Handling

- If the source contains obvious ASR mistakes or broken phrases, infer the intended meaning from local context and translate the corrected meaning into the same subtitle block.
- Never repair structural issues by moving text across cue boundaries.
- If the source sentence is incomplete, produce the most faithful concise translation possible within that cue.
- If preprocessing is enabled, you may move text across adjacent cue boundaries only during the preprocessing stage to repair broken English sentence segmentation and retime those adjacent cues accordingly.
- After preprocessing has produced the canonical cue list, do not move translated Chinese text across adjacent cue boundaries unless the user explicitly requests another retiming/resegmentation pass.

## Chunking Policy

- Default to one-pass translation only for short subtitle files that comfortably fit in a single stable model response.
- As a rule of thumb, subtitle files for videos within about 30 minutes should stay in the one-pass path unless there is a concrete context-window or stability risk.
- If the subtitle file is long, split it before translation rather than risking truncated or malformed output.
- Prefer chunking when the file has hundreds of cues, very long transcript text, or when the execution environment has response-length limits.
- Before chunk translation begins, finish one consistency pass over the whole file and establish the glossary decisions that the chunks must follow.
- Chunk boundaries must preserve original subtitle block order.
- When chunking is necessary, prefer runtime-based chunks first. A good default target is about 20 minutes of subtitle time per chunk, then adjust within that window to land on a natural subtitle boundary.
- Each chunk should be large enough to preserve local context but small enough to translate safely in one pass.
- If a permitted parallel path exists in the current environment, prefer translating independent chunks in parallel.
- If no permitted parallel path exists, translate chunks sequentially in the current conversation.
- Subagent ownership must be disjoint: each subagent receives a clear contiguous chunk range and only writes the matching `NNN.translated.srt` outputs for that range.
- Inside each `NNN.translated.srt`, do not renumber cues, do not retime cues, and do not merge or split cues. Chunk translation is text-only.
- The main conversation remains responsible for chunk planning, manifest inspection, final merge, source-vs-output review, and the last consistency / polish sweep.
- Once chunking starts, treat completion of all chunks plus final merge as the default end-to-end task. Do not stop solely to ask whether to continue.
- Once chunking starts, do not stop after a partial set of translated chunks just to summarize status or wait for another user message.
- If response-length limits prevent finishing in one reply, continue chunk translation over as many replies as needed and merge at the end.
- Do not treat sequential chunk translation in the current conversation as a degraded fallback. It is a first-class completion path.
- On resumed work, inspect the chunk directory and continue from the first missing `NNN.translated.srt`.
- On resumed work, also reload the temporary glossary or term list before continuing, so the remaining chunks use the same terminology decisions.
- After chunk translation, merge only after validating that every translated chunk matches the source chunk's cue numbers, timestamps, cue order, and block count.
- If any chunk fails validation, retranslate only that chunk instead of restarting the entire file.
- Before final delivery, review the merged output against the source subtitle, then do one consistency and polish sweep over repeated names, terminology, tone, subtitle naturalness, and cross-chunk coherence, and only then delete the temporary glossary artifacts if they are no longer needed.

## Consistency Pass

- The consistency pass is an internal working step and should normally happen before the first translated chunk is written.
- Acceptable consistency artifacts include a scratch glossary, a term-decision JSON file, or a short working note beside the subtitle file or chunk folder.
- The consistency artifact should track:
- Source term
- Chosen Chinese translation or “keep English”
- Optional note about first mention or contextual restrictions
- Optional cue references for the first clear occurrences
- If the artifact becomes stale after later context, update it and normalize any earlier translated chunks to match.
- Unless the user explicitly wants the artifact preserved, delete it after the final subtitle file is complete and verified.

## Reference Files

- Read [references/terminology.md](references/terminology.md) for fixed term mappings, non-translatable terms, and subtitle-specific style constraints.

## Scripts

- `scripts/preprocess_srt.py <input-subtitle-file> [output-file]`
- `scripts/preprocess_srt.py <input-subtitle-file> [output-file] [--resegment-sentences]`
- `scripts/preprocess_srt.py <input-subtitle-file> [output-file] [--resegment-sentences] [--max-chars N]`
- `scripts/extract_subtitle_terms.py <input-subtitle-file> [output-file]`
- `scripts/chunk_srt.py split <input-subtitle-file> [output-dir]`
- `scripts/chunk_srt.py split <input-subtitle-file> [output-dir] [--target-minutes N]`
- `scripts/chunk_srt.py merge <manifest-json> [output-file]`
- `scripts/subtitle_pipeline.py prepare <input-subtitle-file>`
- `scripts/subtitle_pipeline.py prepare <input-subtitle-file> [--force-chunk]`
- `scripts/subtitle_pipeline.py finalize <pipeline-json> --reviewed`
- `scripts/subtitle_pipeline.py clean <input-subtitle-file>`
- `scripts/subtitle_pipeline.py status <pipeline-json>`
- The script preserves cue order and rewrites cue numbering sequentially in the output.
- The script accepts subtitle files with common text-based extensions such as `.srt`, `.txt`, `.vtt`, `.ass`, `.ssa`, and `.sub` as long as the content is SRT-like numbered timed blocks.
- It trims surrounding whitespace, removes empty text lines inside cues, collapses repeated internal whitespace, and joins wrapped subtitle text into a single line per cue.
- With `--resegment-sentences`, the script can rebuild sentence boundaries across adjacent cues and redistribute timestamps proportionally inside each repaired local run.
- It can also split overlong subtitle text into shorter nearby cues for better readability, typically by using the current cue plus following empty cues in the same local run.
- `--max-chars` controls the default readability target per cue during preprocessing. The default is `42` for source subtitles.
- `extract_subtitle_terms.py` scans the full subtitle and writes a temporary JSON list of recurring candidate names and terms to help maintain translation consistency across chunks.
- `chunk_srt.py split` writes a chunk folder with `manifest.json`, `NNN.source.srt`, and reserved `NNN.translated.srt` output names.
- `chunk_srt.py split` uses runtime-based chunking and targets about `20` minutes per chunk by default.
- `chunk_srt.py merge` validates translated chunk cue numbers, timestamps, cue order, and block counts before merging and writes the final merged subtitle beside the original source by default.
- `subtitle_pipeline.py prepare` runs preprocessing, extracts recurring terms, and only creates chunks when runtime or stability requires it. Subtitles within about `30` minutes stay on the direct full-file path by default unless `--force-chunk` is used.
- `subtitle_pipeline.py finalize` merges translated chunks into the final subtitle file only after the mandatory master-pass review has been completed and acknowledged with `--reviewed`.
- `subtitle_pipeline.py clean` deletes the default intermediate resources for a source subtitle.
- `subtitle_pipeline.py status` prints the pipeline JSON for inspection or recovery.
- If `output-file` is omitted, the script writes beside the source file and appends `-CN` before the original extension.
- If you explicitly create an intermediate preprocessing file, prefer the sibling naming form `<stem>.preprocessed<suffix>`.
- In the normal full workflow, delete preprocessing intermediates after the final `-CN` file has been written successfully.
- Example: `scripts/preprocess_srt.py "D:\Data\Desktop\demo.srt"` -> `D:\Data\Desktop\demo-CN.srt`
- Example: `scripts/preprocess_srt.py "D:\Data\Desktop\demo.txt"` -> `D:\Data\Desktop\demo-CN.txt`
- Example: `scripts/preprocess_srt.py "D:\Data\Desktop\demo.srt" --resegment-sentences`
- Example: `scripts/extract_subtitle_terms.py "D:\Data\Desktop\demo.srt"`
- Example: `scripts/chunk_srt.py split "D:\Data\Desktop\demo.srt"`
- Example: `scripts/chunk_srt.py merge "D:\Data\Desktop\demo.chunks\manifest.json"`
- Example: `scripts/subtitle_pipeline.py prepare "D:\Data\Desktop\demo.srt" --resegment-sentences`
- Example: `scripts/subtitle_pipeline.py finalize "D:\Data\Desktop\demo.pipeline.json"`
- Use `--keep-line-breaks` if the existing line breaks are semantically important.

