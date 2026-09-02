// Description: This file contains utility functions that are used throughout the app

import { type ClassValue, clsx } from 'clsx';
import { format, formatDistanceToNow } from 'date-fns';
import { toast } from 'sonner';
import { twMerge } from 'tailwind-merge';

/**
 * Combine multiple classes together
 * @param inputs - The classes to combine
 * @returns The combined classes
 * @example cn('text-center font-medium', {"w-5 py-2":isLoading})
 * */
export function cn(...inputs: ClassValue[]): string {
	return twMerge(clsx(inputs));
}

/**
 * Copy text to clipboard with fallback for older browsers.
 * Includes toast notifications
 * @param text - The text to copy
 * @returns void
 * */
export function copyToClipboard(text: string): void {
	if (navigator.clipboard && window.isSecureContext) {
		// navigator.clipboard is available
		navigator.clipboard.writeText(text).then(
			() => {
				toast.success('Text copied to clipboard successfully!');
			},
			(err) => {
				console.error('Failed to copy text to clipboard:', err);
				toast.error('Failed to copy text to clipboard');
			}
		);
	} else {
		// fallback method for older browsers
		const textArea = document.createElement('textarea');
		textArea.value = text;

		// Avoid scrolling to bottom
		textArea.style.position = 'absolute';
		textArea.style.opacity = '0';
		textArea.style.left = '-9999px';

		document.body.appendChild(textArea);
		textArea.focus();
		textArea.select();

		try {
			const successful = document.execCommand('copy');
			const msg = successful
				? 'Text copied to clipboard successfully!'
				: 'Failed to copy text to clipboard';
			toast[successful ? 'success' : 'error'](msg);
		} catch (err) {
			console.error('Failed to copy text to clipboard:', err);
			toast.error('Failed to copy text to clipboard');
		}

		document.body.removeChild(textArea);
	}
}

/**
 * Format date to MMMM dd, yyyy at hh:mm a
 * @param date - The date to format
 * @param formatLayout - The format layout (date-fns formats)
 * @returns The formatted date
 * e.g. January 01, 2023 at 12:34 PM
 * */
export function formatDate(
	date: string,
	formatLayout: string = "MMMM dd, yyyy 'at' hh:mm a"
): string {
	const createdAtDate = new Date(date);

	if (Number.isNaN(createdAtDate.getTime())) {
		return '----';
	}

	return format(createdAtDate, formatLayout);
}

/**
 * Format date to hh:mm a MM/dd/yyyy
 * @param date - The date to format
 * @returns The formatted date
 * e.g. 12:34 PM 01/01/2023
 * */
export function formatMessageDate(date: string): string {
	const createdAtDate = new Date(date);

	if (Number.isNaN(createdAtDate.getTime())) {
		return '----';
	}

	return format(createdAtDate, 'hh:mm a MM/dd/yyyy');
}

/**
 * Format date to distance from now
 * @param date - The date to format
 * @returns The distance from now
 * e.g. 2 days ago
 * */
export function dateDistance(date: string): string {
	const createdAtDate = new Date(date);

	const result = formatDistanceToNow(createdAtDate, { addSuffix: true });

	// Check if it says 2023 years ago
	if (result.includes('over 2023 years ago')) {
		return 'Never';
	}

	return result;
}

/**
 * Convert days to months
 * @param days - The number of days
 * @returns The number of months and remaining days
 * e.g. 32 days to 1 month 2 days
 * */
export function daysToMonths(days: number): string {
	if (days < 30) {
		return `${days} days`;
	}

	const months = Math.floor(days / 30);
	const remainingDays = days % 30;

	return `${months} months ${remainingDays} days`;
}
