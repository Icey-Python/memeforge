'use client';

// Model Connector Node: pick and configure the LLM behind the pipeline.
//
// ONE clean "Model" dropdown, populated conditionally:
// - Ollama (local): installed models are auto-fetched from the daemon
//   (http://localhost:11434 default) with a Refresh button.
// - OpenAI / Anthropic / Groq / OpenRouter / custom: an API key input
//   (password-masked, saved to the encrypted browser vault) and — for
//   custom endpoints — a Base URL. The model list loads once the key
//   is saved; until then (or when offline) the dropdown shows the
//   provider's standard catalog defaults, so nothing blocks the flow.
// No API calls fire on keystrokes: keys commit via "Save Key", URL
// edits commit on blur, and discovery auto-runs once per config.

import { useQuery } from '@tanstack/react-query';
import type { NodeProps } from '@xyflow/react';
import { Bot, Loader2, PlugZap, RefreshCw } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { backendLLMProvider, LLM_PROVIDERS, llmBaseUrl } from '@/lib/catalog';
import { MemeforgeAPI } from '@/lib/memeforge';
import { usePipelineStore } from '@/store/pipeline';
import { vaultSecret } from '@/store/vault';
import type { DiscoveredModel, LLMProviderId } from '@/types/studio';
import { NodeBadge, NodeShell, StudioSelect } from '../node-shell';
import { VaultKeyInput } from '../vault-key-input';

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

	const preset = LLM_PROVIDERS.find((p) => p.id === model.provider);
	const backend = backendLLMProvider(model.provider);
	const baseUrl = llmBaseUrl(model);
	const isLocal = backend === 'ollama';
	const isCustom = model.provider === 'custom';
	/** Base URL field shown only for editable presets (ollama / custom). */
	const showsBaseUrl = preset?.baseUrlEditable ?? false;
	/** API key field: keyed clouds always; custom optionally. */
	const showsApiKey = Boolean(preset?.requiresApiKey) || isCustom;

	// Server-side catalog: which connectors have .env keys configured.
	const { data: catalog } = useQuery({
		queryKey: ['model-catalog'],
		queryFn: MemeforgeAPI.listModels,
		retry: false,
		staleTime: 60_000
	});
	const serverConfigured = Boolean(
		catalog?.find((c) => c.id === backend)?.configured
	);

	const hasApiKey = Boolean(model.apiKey);

	// Live model discovery. Enabled:false — triggered manually (Refresh)
	// or auto ONCE per config change (provider / URL / key availability),
	// never on keystrokes.
	const discovery = useQuery({
		queryKey: ['model-discovery', backend, baseUrl, hasApiKey],
		queryFn: () =>
			MemeforgeAPI.discoverModels({
				provider: backend,
				baseUrl: baseUrl || undefined,
				apiKey: model.apiKey || undefined
			}),
		enabled: false,
		retry: false,
		staleTime: 30_000
	});

	// Auto-discovery eligibility: the preset must support discovery
	// (anthropic uses its curated catalog); then ollama/custom need a
	// URL and keyed clouds need a key (vault key or a server .env key).
	const discoverable = Boolean(preset?.discoverable) && backend !== 'mock';
	const canAutoDiscover =
		discoverable &&
		(isLocal || isCustom ? baseUrl !== '' : hasApiKey || serverConfigured);

	// Fire discovery once per distinct config (config -> one fetch).
	const configKey = `${backend}|${baseUrl}|${hasApiKey}`;
	const lastAutoKey = useRef('');
	useEffect(() => {
		if (!canAutoDiscover) return;
		if (lastAutoKey.current === configKey) return;
		lastAutoKey.current = configKey;
		void discovery.refetch();
	}, [configKey, canAutoDiscover, discovery.refetch]);

	const discovered = discovery.data?.models ?? [];
	const liveOptions = discovered.map((m) => ({
		value: m.id,
		label: modelOptionLabel(m)
	}));
	// Standard catalog defaults keep the dropdown usable before
	// discovery (or when the endpoint is unreachable).
	const fallbackOptions = (preset?.models ?? []).map((m) => ({
		value: m,
		label: m
	}));
	const options = liveOptions.length > 0 ? liveOptions : fallbackOptions;
	const selectionValid = options.some((o) => o.value === model.model);
	const showDropdown =
		options.length > 0 ||
		(isLocal && (discovery.isFetching || Boolean(discovery.data)));

	// Header badge reflects live availability.
	let badgeVariant: 'default' | 'success' | 'warn' | 'danger' = 'default';
	let badgeText = '…';
	if (backend === 'mock') {
		badgeVariant = 'default';
		badgeText = 'offline';
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
	} else if (preset?.requiresApiKey && !hasApiKey && !serverConfigured) {
		badgeVariant = 'warn';
		badgeText = 'needs API key';
	} else if (hasApiKey) {
		badgeVariant = 'success';
		badgeText = 'key saved';
	} else if (serverConfigured) {
		badgeVariant = 'success';
		badgeText = 'server key';
	}

	const switchProvider = (v: string) => {
		const next = LLM_PROVIDERS.find((p) => p.id === v);
		if (!next) return;
		setModel({
			provider: v as LLMProviderId,
			model: next.defaultModel,
			// Editable presets pre-fill their default URL; cloud presets
			// keep a fixed URL (llmBaseUrl()) and don't need the field.
			baseUrl: next.baseUrlEditable ? next.defaultBaseUrl : '',
			// Re-hydrate the key this preset has in the encrypted vault.
			apiKey: vaultSecret(`llm.${v}.apiKey`)
		});
	};

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
					onChange={switchProvider}
					options={LLM_PROVIDERS.map((p) => ({
						value: p.id,
						label: `${p.label} — ${p.hint}`
					}))}
				/>
			</div>

			{showsApiKey && (
				<VaultKeyInput
					id="model-key"
					vaultKey={`llm.${model.provider}.apiKey`}
					label={preset?.requiresApiKey ? 'API key' : 'API key (optional)'}
					placeholder={
						model.provider === 'anthropic'
							? 'sk-ant-…'
							: isCustom
								? 'key (leave empty for keyless local servers)'
								: 'sk-…'
					}
					onSaved={(secret) => setModel({ apiKey: secret })}
					onDeleted={() => setModel({ apiKey: undefined })}
				/>
			)}

			{showsBaseUrl && (
				<div className="space-y-1.5">
					<Label htmlFor="model-url">Base URL</Label>
					<Input
						id="model-url"
						value={model.baseUrl ?? ''}
						placeholder={
							isLocal ? 'http://localhost:11434' : 'http://localhost:1234/v1'
						}
						onChange={(e) => setModel({ baseUrl: e.target.value })}
						onBlur={(e) => {
							// Commit trimmed URLs (triggers one discovery).
							const trimmed = e.target.value.trim();
							if (trimmed !== e.target.value) setModel({ baseUrl: trimmed });
						}}
					/>
				</div>
			)}

			<div className="space-y-1.5">
				<Label
					htmlFor="model-name"
					className="flex items-center justify-between"
				>
					Model
					{discoverable && (
						<button
							type="button"
							onClick={() => void discovery.refetch()}
							disabled={discovery.isFetching}
							className="flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
							title="Re-fetch the model list from the endpoint"
							data-testid="refresh-models"
						>
							{discovery.isFetching ? (
								<Loader2 className="size-3 animate-spin" />
							) : (
								<RefreshCw className="size-3" />
							)}
							Refresh models
						</button>
					)}
				</Label>
				{showDropdown ? (
					<StudioSelect
						id="model-name"
						value={selectionValid ? model.model : ''}
						onChange={(v) => v && setModel({ model: v })}
						placeholder="— select a model —"
						options={options}
					/>
				) : (
					<p className="text-xs text-muted-foreground" data-testid="model-hint">
						{isCustom
							? 'Enter your endpoint URL above to load its models.'
							: 'Model list loads once the required fields are filled.'}
					</p>
				)}
			</div>

			{discovery.isFetching && (
				<p className="text-xs text-muted-foreground">Querying the endpoint…</p>
			)}
			{discoverable && discovery.isError && (
				<p className="text-xs text-red-400" role="alert">
					Model discovery request failed — is the memeforge server running?
				</p>
			)}
			{discoverable && discovery.data && !discovery.data.reachable && (
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
				{backend === 'mock'
					? 'Mock works offline — no keys needed.'
					: preset?.requiresApiKey && !hasApiKey && !serverConfigured
						? 'Save an API key (encrypted in your browser) or set it in server .env.'
						: 'Keys are encrypted in the browser vault and sent with each request.'}
			</p>
		</NodeShell>
	);
}
