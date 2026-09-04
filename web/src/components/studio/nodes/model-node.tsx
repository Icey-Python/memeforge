'use client';

// Model Connector Node: pick the LLM behind the pipeline.
//
// ONE "Model" dropdown per provider:
//  - Ollama: installed models auto-load from the daemon (parameter size +
//    quantization labels) with a Refresh models button.
//  - Cloud gateways (OpenAI / Anthropic / OpenRouter / Groq): models load
//    with the decrypted vault key (or the server .env default); a missing
//    key surfaces an inline vault action instead of discovery errors.
//  - Custom: any OpenAI-compatible endpoint, queried on demand.

import { useQuery } from '@tanstack/react-query';
import type { NodeProps } from '@xyflow/react';
import { Bot, RefreshCw } from 'lucide-react';
import { useEffect } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useDebouncedValue } from '@/hooks/use-debounced-value';
import { LLM_PROVIDERS, resolveGateway, SUGGESTED_MODELS } from '@/lib/catalog';
import { resolveLLMCredential } from '@/lib/credentials';
import { MemeforgeAPI } from '@/lib/memeforge';
import { cn } from '@/lib/utils';
import { useCredentialsStore } from '@/store/credentials';
import { usePipelineStore } from '@/store/pipeline';
import type { DiscoveredModel } from '@/types/studio';
import { NodeBadge, NodeShell, StudioSelect } from '../node-shell';
import { InlineVaultSection, LLM_FIELDS } from '../settings-drawer';

/** Dropdown label for a discovered model, e.g. "llama3.2:latest · 3.2B, Q4_K_M". */
function modelOptionLabel(model: DiscoveredModel): string {
	const meta = [model.parameter_size, model.quantization]
		.filter(Boolean)
		.join(', ');
	return meta
		? `${model.label || model.id} · ${meta}`
		: model.label || model.id;
}

/** /health capability flag for the server .env key matching a base URL. */
function serverKeyFlag(baseUrl?: string): string {
	const url = (baseUrl ?? '').toLowerCase();
	if (url.includes('openrouter')) return 'llm_openrouter';
	if (url.includes('groq')) return 'llm_groq';
	if (url.includes('anthropic')) return 'llm_anthropic';
	return 'llm_openai';
}

export function ModelNode(_props: NodeProps) {
	const model = usePipelineStore((s) => s.model);
	const setModel = usePipelineStore((s) => s.setModel);

	// Decrypted vault keys (memory-only while unlocked) + save revision.
	const vaultKeys = useCredentialsStore((s) => s.keys);
	const vaultRevision = useCredentialsStore((s) => s.revision);

	// Server .env key presence (query cache shared with the settings
	// drawer's "Using Server Default" pills).
	const { data: health } = useQuery({
		queryKey: ['health'],
		queryFn: MemeforgeAPI.health,
		retry: false,
		refetchInterval: 30_000
	});

	// Effective credentials: inline node values > vault key > server .env.
	const creds = resolveLLMCredential(model, vaultKeys);
	const gateway = resolveGateway(model, creds.baseUrl);
	const isMock = model.provider === 'mock';

	// Cloud endpoints need auth (vault key or a server default); custom
	// endpoints just need a URL (local servers are often keyless).
	const hasKey = Boolean(creds.apiKey);
	const serverFlag = serverKeyFlag(creds.baseUrl);
	const serverDefault = Boolean(health?.capabilities?.[serverFlag]);
	const canDiscover =
		gateway.id === 'ollama'
			? true
			: gateway.id === 'custom'
				? Boolean(creds.baseUrl)
				: hasKey || serverDefault;

	// Ollama and preset gateways auto-discover (the debounced base URL and
	// the vault revision re-run it when the endpoint/keys change). Custom
	// endpoints are queried on demand so typing never fires requests.
	const debouncedBaseUrl = useDebouncedValue(creds.baseUrl ?? '', 400);
	const discovery = useQuery({
		queryKey: [
			'model-discovery',
			model.provider,
			gateway.id,
			debouncedBaseUrl,
			vaultRevision
		],
		queryFn: () =>
			MemeforgeAPI.discoverModels({
				provider: model.provider,
				baseUrl: debouncedBaseUrl || undefined,
				apiKey: creds.apiKey
			}),
		enabled: canDiscover && gateway.id !== 'custom',
		retry: false,
		staleTime: 30_000
	});

	const discovered = discovery.data?.models ?? [];
	const discoveryOk =
		Boolean(discovery.data?.reachable) && discovered.length > 0;

	// Ollama keeps the selection valid: snap to the first installed model
	// when the daemon does not actually serve the current one.
	useEffect(() => {
		if (model.provider !== 'ollama' || !discoveryOk) return;
		if (discovered.some((m) => m.id === model.model)) return;
		setModel({ model: discovered[0].id });
	}, [model.provider, model.model, discoveryOk, discovered, setModel]);

	// Dropdown options: live discovery first; suggested ids only while no
	// live list exists. The current selection always stays visible.
	const options = [
		...discovered.map((m) => ({ value: m.id, label: modelOptionLabel(m) })),
		...(discoveryOk || discovery.isFetching
			? []
			: (SUGGESTED_MODELS[gateway.id] ?? []).map((id) => ({
					value: id,
					label: `${id} · suggested`
				})))
	];
	if (model.model && !options.some((o) => o.value === model.model)) {
		options.push({ value: model.model, label: `${model.model} · current` });
	}

	const placeholder = discovery.isFetching
		? 'Loading models'
		: !canDiscover
			? gateway.id === 'custom'
				? 'Enter a base URL first'
				: 'Add a key to load models'
			: gateway.id === 'custom' && !discovery.data
				? 'Refresh to load models'
				: options.length === 0
					? 'No models found'
					: 'Pick a model';

	// Header badge reflects live endpoint availability.
	let badgeVariant: 'default' | 'success' | 'warn' | 'danger' = 'default';
	let badgeText = 'checking';
	if (isMock) {
		badgeVariant = 'success';
		badgeText = 'ready';
	} else if (!canDiscover) {
		badgeVariant = 'warn';
		badgeText = gateway.id === 'custom' ? 'needs URL' : 'needs key';
	} else if (discovery.isFetching) {
		badgeText = 'checking';
	} else if (discovery.data) {
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
	} else {
		badgeText = 'not checked';
	}

	// Named gateway with no key anywhere: inline vault action (unlock
	// prompt / key input) instead of a dead dropdown.
	const needsVaultKey = Boolean(gateway.vaultKey) && !hasKey && !serverDefault;
	const keyField = LLM_FIELDS.find((f) => f.serverFlag === serverFlag);

	return (
		<NodeShell
			icon={Bot}
			title="Model"
			handles="source"
			badge={<NodeBadge variant={badgeVariant}>{badgeText}</NodeBadge>}
		>
			<div className="space-y-1.5">
				<Label htmlFor="model-provider">Provider</Label>
				<StudioSelect
					id="model-provider"
					value={gateway.id}
					onChange={(v) => {
						const next = LLM_PROVIDERS.find((p) => p.id === v);
						if (!next) return;
						setModel({
							provider: next.backend,
							gateway: next.id,
							model: next.defaultModel,
							// Preset base URL (Ollama daemon / gateway API);
							// blank falls back to the server .env default.
							baseUrl: next.baseUrl,
							apiKey: ''
						});
					}}
					options={LLM_PROVIDERS.map((p) => ({
						value: p.id,
						label: p.label
					}))}
				/>
			</div>

			{!isMock && (
				<div className="space-y-1.5">
					<div className="flex items-center justify-between gap-2">
						<Label htmlFor="model-name">Model</Label>
						<button
							type="button"
							onClick={() => void discovery.refetch()}
							disabled={!canDiscover || discovery.isFetching}
							className="flex items-center gap-1 text-[11px] font-medium text-zinc-500 transition-colors hover:text-zinc-200 disabled:cursor-not-allowed disabled:opacity-50"
							data-testid="refresh-models"
						>
							<RefreshCw
								className={cn('size-3', discovery.isFetching && 'animate-spin')}
							/>
							Refresh models
						</button>
					</div>
					<StudioSelect
						id="model-name"
						value={model.model}
						onChange={(v) => setModel({ model: v })}
						options={options}
						placeholder={placeholder}
					/>
					{discovery.isError && (
						<p className="text-xs text-red-400" role="alert">
							Model discovery failed. Is the memeforge server running?
						</p>
					)}
					{discovery.data && !discovery.data.reachable && (
						<p
							className="text-xs text-red-400"
							role="alert"
							data-testid="discovery-error"
						>
							{discovery.data.error ??
								'Endpoint unreachable. Check the URL / daemon.'}
						</p>
					)}
					{discovery.data?.reachable && discovered.length === 0 && (
						<p className="text-xs text-zinc-500">
							No models found at this endpoint.
						</p>
					)}
				</div>
			)}

			{needsVaultKey && keyField && (
				<InlineVaultSection title={keyField.label} fields={[keyField]} />
			)}

			{(gateway.id === 'ollama' || gateway.id === 'custom') && (
				<div className="space-y-1.5">
					<Label htmlFor="model-url">Base URL</Label>
					<Input
						id="model-url"
						value={model.baseUrl ?? ''}
						placeholder={
							gateway.id === 'ollama'
								? 'http://localhost:11434'
								: 'http://localhost:1234/v1'
						}
						onChange={(e) => setModel({ baseUrl: e.target.value })}
					/>
				</div>
			)}

			{gateway.id === 'custom' && (
				<div className="space-y-1.5">
					<Label htmlFor="model-key">API key (optional)</Label>
					<Input
						id="model-key"
						type="password"
						value={model.apiKey ?? ''}
						placeholder="blank for local servers"
						onChange={(e) => setModel({ apiKey: e.target.value })}
					/>
				</div>
			)}
		</NodeShell>
	);
}
