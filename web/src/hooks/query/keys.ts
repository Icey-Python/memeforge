/** Centralised React Query key factory */
export const queryKeys = {
	health: ['health'] as const,
	models: ['model-catalog'] as const,
	voices: (provider: string) => ['voices', provider] as const,
	gameplays: ['gameplays'] as const,
	render: {
		job: (jobId: string) => ['render', 'job', jobId] as const
	}
};
