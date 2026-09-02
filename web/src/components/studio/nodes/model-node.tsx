'use client';

// Model Connector Node: pick and configure the LLM behind the pipeline.

import { useQuery } from '@tanstack/react-query';
import type { NodeProps } from '@xyflow/react';
import { Bot, PlugZap } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LLM_PROVIDERS } from '@/lib/catalog';
import { MemeforgeAPI } from '@/lib/memeforge';
import { usePipelineStore } from '@/store/pipeline';
import type { LLMProviderId } from '@/types/studio';
import { NodeBadge, NodeShell, StudioSelect } from '../node-shell';

export function ModelNode(_props: NodeProps) {
	const model = usePipelineStore((s) => s.model);
	const setModel = usePipelineStore((s) => s.setModel);

	const { data: catalog } = useQuery({
		queryKey: ['model-catalog'],
		queryFn: MemeforgeAPI.listModels,
		retry: false,
		staleTime: 60_000
	});

	const entry = catalog?.find((c) => c.id === model.provider);
	const showUrl = model.provider !== 'mock';
	const showKey = model.provider === 'openai';

	return (
		<NodeShell
			icon={Bot}
			title="Model Connector"
			accent="bg-violet-500/15 text-violet-300"
			handles="source"
			badge={
				<NodeBadge
					variant={entry ? (entry.configured ? 'success' : 'warn') : 'default'}
				>
					{entry ? (entry.configured ? 'ready' : 'needs config') : '…'}
				</NodeBadge>
			}
		>
			<div className="space-y-1.5">
				<Label htmlFor="model-provider">Provider</Label>
				<StudioSelect
					id="model-provider"
					value={model.provider}
					onChange={(v) => {
						const preset = LLM_PROVIDERS.find((p) => p.id === v);
						setModel({
							provider: v as LLMProviderId,
							model: preset?.defaultModel ?? '',
							baseUrl: '',
							apiKey: ''
						});
					}}
					options={LLM_PROVIDERS.map((p) => ({
						value: p.id,
						label: `${p.label} — ${p.hint}`
					}))}
				/>
			</div>

			<div className="space-y-1.5">
				<Label htmlFor="model-name">Model</Label>
				<Input
					id="model-name"
					value={model.model}
					placeholder={
						LLM_PROVIDERS.find((p) => p.id === model.provider)?.defaultModel
					}
					onChange={(e) => setModel({ model: e.target.value })}
				/>
			</div>

			{showUrl && (
				<div className="space-y-1.5">
					<Label htmlFor="model-url">Base URL (optional)</Label>
					<Input
						id="model-url"
						value={model.baseUrl ?? ''}
						placeholder={
							model.provider === 'ollama'
								? 'http://localhost:11434'
								: 'https://api.openai.com/v1'
						}
						onChange={(e) => setModel({ baseUrl: e.target.value })}
					/>
				</div>
			)}

			{showKey && (
				<div className="space-y-1.5">
					<Label htmlFor="model-key">API key (optional for local)</Label>
					<Input
						id="model-key"
						type="password"
						value={model.apiKey ?? ''}
						placeholder="sk-…"
						onChange={(e) => setModel({ apiKey: e.target.value })}
					/>
				</div>
			)}

			<p className="flex items-center gap-1.5 text-xs text-muted-foreground">
				<PlugZap className="size-3" />
				{model.provider === 'mock'
					? 'Mock works offline — no keys needed.'
					: 'Credentials come from the server .env when left blank.'}
			</p>
		</NodeShell>
	);
}
