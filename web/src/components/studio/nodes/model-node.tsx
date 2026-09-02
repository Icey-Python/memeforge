'use client';

// Model Connector Node: pick and configure the LLM behind the pipeline.
// Ollama / OpenAI-compatible providers support live model discovery — the
// backend queries the endpoint (Ollama /api/tags, OpenAI /v1/models) and
// the discovered models populate a dropdown next to the free-text input.

import { useQuery } from '@tanstack/react-query';
import type { NodeProps } from '@xyflow/react';
import { Bot, Loader2, PlugZap, RefreshCw } from 'lucide-react';
import { useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LLM_PROVIDERS } from '@/lib/catalog';
import { MemeforgeAPI } from '@/lib/memeforge';
import { usePipelineStore } from '@/store/pipeline';
import type { DiscoveredModel, LLMProviderId } from '@/types/studio';
import { NodeBadge, NodeShell, StudioSelect } from '../node-shell';

/** Dropdown label for a discovered model, e.g. "llama3.2:latest · 3.2B, Q4_K_M". */
function modelOptionLabel(model: DiscoveredModel): string {
	const meta = [model.parameter_size, model.quantization]
		.filter(Boolean)
		.join(', ');
	return meta
		? `${model.label || model.id} · ${meta}`
		: model.label || model.id;
}

export function ModelNode(_props: NodeProps) {
	const model = usePipelineStore((s) => s.model);
	const setModel = usePipelineStore((s) => s.setModel);

	const { data: catalog } = useQuery({
		queryKey: ['model-catalog'],
		queryFn: MemeforgeAPI.listModels,
		retry: false,
		staleTime: 60_000
	});

	const isRemote = model.provider !== 'mock';
	const preset = LLM_PROVIDERS.find((p) => p.id === model.provider);
	const entry = catalog?.find((c) => c.id === model.provider);

	// Live model discovery for the selected provider + base URL. Triggered
	// automatically when a remote provider is selected and manually via the
	// Discover button (which also picks up base URL edits).
	const discovery = useQuery({
		queryKey: ['model-discovery', model.provider, model.baseUrl ?? ''],
		queryFn: () =>
			MemeforgeAPI.discoverModels({
				provider: model.provider,
				baseUrl: model.baseUrl || undefined,
				apiKey: model.apiKey || undefined
			}),
		enabled: false,
		retry: false,
		staleTime: 30_000
	});

	// Auto-discover whenever a remote provider gets selected.
	useEffect(() => {
		if (model.provider === 'mock') return;
		void discovery.refetch();
	}, [model.provider, discovery.refetch]);

	const discovered = discovery.data?.models ?? [];
	const selectedDiscovered = discovered.some((m) => m.id === model.model);

	// Header badge reflects live availability once a discovery attempt ran.
	let badgeVariant: 'default' | 'success' | 'warn' | 'danger' = 'default';
	let badgeText = '…';
	if (isRemote && discovery.data) {
		if (!discovery.data.reachable) {
			badgeVariant = 'danger';
			badgeText = 'unreachable';
		} else if (discovered.length === 0) {
			badgeVariant = 'warn';
			badgeText = 'no models';
		} else {
			badgeVariant = 'success';
			badgeText = `${discovered.length} models`;
		}
	} else if (entry) {
		badgeVariant = entry.configured ? 'success' : 'warn';
		badgeText = entry.configured ? 'ready' : 'needs config';
	}

	return (
		<NodeShell
			icon={Bot}
			title="Model Connector"
			accent="bg-violet-500/15 text-violet-300"
			handles="source"
			badge={<NodeBadge variant={badgeVariant}>{badgeText}</NodeBadge>}
		>
			<div className="space-y-1.5">
				<Label htmlFor="model-provider">Provider</Label>
				<StudioSelect
					id="model-provider"
					value={model.provider}
					onChange={(v) => {
						const nextPreset = LLM_PROVIDERS.find((p) => p.id === v);
						setModel({
							provider: v as LLMProviderId,
							model: nextPreset?.defaultModel ?? '',
							// Pre-fill the default Ollama URL; other providers
							// fall back to the server .env when left blank.
							baseUrl: nextPreset?.defaultBaseUrl ?? '',
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
					placeholder={preset?.defaultModel}
					onChange={(e) => setModel({ model: e.target.value })}
				/>
			</div>

			{isRemote && (
				<div className="space-y-1.5">
					<Label htmlFor="model-discovered">
						Discovered models
						{discovered.length > 0 ? ` (${discovered.length})` : ''}
					</Label>
					{discovered.length > 0 ? (
						<StudioSelect
							id="model-discovered"
							value={selectedDiscovered ? model.model : ''}
							onChange={(v) => v && setModel({ model: v })}
							placeholder="— pick a discovered model —"
							options={discovered.map((m) => ({
								value: m.id,
								label: modelOptionLabel(m)
							}))}
						/>
					) : (
						<p className="text-xs text-muted-foreground">
							{discovery.isFetching
								? 'Querying the endpoint…'
								: discovery.data && !discovery.data.reachable
									? 'Endpoint unreachable — check the URL / daemon.'
									: 'Type a name or press Discover models to list what the endpoint serves.'}
						</p>
					)}
				</div>
			)}

			{isRemote && (
				<Button
					variant="outline"
					size="sm"
					className="w-full"
					onClick={() => void discovery.refetch()}
					disabled={discovery.isFetching}
				>
					{discovery.isFetching ? (
						<Loader2 className="size-3.5 animate-spin" />
					) : (
						<RefreshCw className="size-3.5" />
					)}
					{discovery.isFetching ? 'Discovering…' : 'Discover models'}
				</Button>
			)}

			{isRemote && (
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

			{model.provider === 'openai' && (
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

			{discovery.isError && (
				<p className="text-xs text-red-400" role="alert">
					Model discovery request failed — is the memeforge server running?
				</p>
			)}
			{discovery.data && !discovery.data.reachable && (
				<p
					className="text-xs text-red-400"
					role="alert"
					data-testid="discovery-error"
				>
					{discovery.data.error ?? 'Endpoint unreachable.'}
				</p>
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
