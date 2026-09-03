// Desc: Script text splitting for the "Paste / Write Custom Script" flow.
// A pasted text block is split into individual timed script lines by
// paragraphs, linebreaks, sentence punctuation, and clause boundaries —
// no LLM call required. Shared by the Script node and the pipeline store.

export interface SplitScriptOptions {
	/** Hard cap on returned lines (render sanity). */
	maxLines?: number;
	/** Lines longer than this (in words) split at clause boundaries. */
	maxWordsPerLine?: number;
	/** Fragments shorter than this (in words) merge into neighbors. */
	minWordsPerLine?: number;
}

const DEFAULTS: Required<SplitScriptOptions> = {
	maxLines: 40,
	maxWordsPerLine: 16,
	minWordsPerLine: 3
};

/** ~140 wpm spoken pace — matches the backend's word_target budgets. */
export const WORDS_PER_SECOND = 2.4;

/** Estimated spoken length of a word count, in seconds. */
export function estimateSpokenSeconds(words: number): number {
	return words / WORDS_PER_SECOND;
}

function wordCount(text: string): number {
	const trimmed = text.trim();
	return trimmed ? trimmed.split(/\s+/).length : 0;
}

/** Strip markdown-ish list/bullet markers from a pasted line. */
function stripBullet(line: string): string {
	return line.replace(/^\s*(?:[-*+>•]|\d+[.)])\s+/u, '').trim();
}

/** Split one hard line into sentences, keeping terminal punctuation. */
function splitSentences(line: string): string[] {
	const sentences =
		line.match(/[^.!?…]+[.!?…]+["')\]]*|[^.!?…]+/gu)?.map((s) => s.trim()) ??
		[];
	return sentences.filter(Boolean);
}

/** Split an over-long sentence at clause boundaries (, ; : —). */
function splitClauses(sentence: string, maxWords: number): string[] {
	const parts = sentence
		.split(/(?<=[,;:—])\s+/u)
		.map((part) => part.trim())
		.filter(Boolean);
	if (parts.length <= 1) return [sentence.trim()];

	const chunks: string[] = [];
	let current = '';
	for (const part of parts) {
		const trial = current ? `${current} ${part}` : part;
		if (wordCount(trial) <= maxWords) {
			current = trial;
		} else {
			if (current) chunks.push(current);
			current = part;
		}
	}
	if (current) chunks.push(current);
	return chunks;
}

/**
 * Split a pasted script block into individual timed lines.
 *
 * Paragraph breaks (blank lines) always start new lines; single
 * linebreaks break too; sentences within a line become their own lines;
 * over-long sentences split further at clause boundaries; tiny fragments
 * merge into neighbors so every line stays speakable.
 */
export function splitScriptText(
	text: string,
	options: SplitScriptOptions = {}
): string[] {
	const { maxLines, maxWordsPerLine, minWordsPerLine } = {
		...DEFAULTS,
		...options
	};
	const paragraphs = text
		.replace(/\r\n?/g, '\n')
		.split(/\n{2,}/)
		.map((paragraph) => paragraph.trim())
		.filter(Boolean);

	const raw: { text: string; group: number }[] = [];
	let group = 0;
	for (const paragraph of paragraphs) {
		const hardLines = paragraph
			.split('\n')
			.map((line) => stripBullet(line))
			.filter(Boolean);
		for (const hardLine of hardLines) {
			for (const sentence of splitSentences(hardLine)) {
				const pieces =
					wordCount(sentence) > maxWordsPerLine
						? splitClauses(sentence, maxWordsPerLine)
						: [sentence];
				for (const piece of pieces) raw.push({ text: piece, group });
			}
			group += 1;
		}
	}

	// Merge tiny fragments (e.g. a lone "Right.") into the previous line —
	// but only within the same hard line: explicit linebreaks stay breaks.
	const merged: string[] = [];
	for (const [index, chunk] of raw.entries()) {
		const previousChunk = raw[index - 1];
		const previous = merged[merged.length - 1];
		const mergeable =
			previousChunk !== undefined &&
			previousChunk.group === chunk.group &&
			(wordCount(chunk.text) < minWordsPerLine ||
				wordCount(previousChunk.text) < minWordsPerLine);
		if (previous !== undefined && mergeable) {
			merged[merged.length - 1] = `${previous} ${chunk.text}`;
		} else {
			merged.push(chunk.text);
		}
	}

	return merged.slice(0, maxLines);
}

/** Card/short title derived from the first line of a custom script. */
export function deriveScriptTitle(lines: string[]): string {
	const first = (lines[0] ?? '').trim().replace(/[.!?…]+$/u, '');
	if (!first) return 'custom script';
	const words = first.split(/\s+/);
	return words.length > 8 ? words.slice(0, 8).join(' ') : first;
}
