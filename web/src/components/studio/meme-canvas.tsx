'use client';

// The short-form video studio canvas: React Flow graph of pipeline
// nodes.
//
// Stepwise mode (default ON) turns the canvas into a wizard: only the
// Model + Topic nodes are shown initially; the Script node appears when
// a script is generated or pasted, Voiceover + Gameplay unlock once the
// script is confirmed, and the Preview & Export node appears when a
// background clip has been picked. "Show all" reveals the full freeform
// canvas.

import {
	addEdge,
	Background,
	BackgroundVariant,
	type Connection,
	Controls,
	type Edge,
	type EdgeTypes,
	MiniMap,
	type Node,
	type NodeTypes,
	Panel,
	ReactFlow,
	ReactFlowProvider,
	useEdgesState,
	useNodesState,
	useReactFlow
} from '@xyflow/react';
import { useCallback, useEffect, useRef } from 'react';
import '@xyflow/react/dist/style.css';
import { Plus, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuItem,
	DropdownMenuTrigger
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import { STUDIO_STEPS, studioStage, usePipelineStore } from '@/store/pipeline';
import { GameplayNode } from './nodes/gameplay-node';
import { ModelNode } from './nodes/model-node';
import { PreviewNode } from './nodes/preview-node';
import { ScriptNode } from './nodes/script-node';
import { TopicNode } from './nodes/topic-node';
import { VoiceoverNode } from './nodes/voiceover-node';

// --- Node registry ---------------------------------------------------------

export type StudioNodeType =
	| 'model'
	| 'topic'
	| 'script'
	| 'voiceover'
	| 'gameplay'
	| 'preview';

export const NODE_MENU: {
	type: StudioNodeType;
	label: string;
	color: string;
}[] = [
	{ type: 'model', label: 'Model Connector', color: '#a78bfa' },
	{ type: 'topic', label: 'Topic / Prompt', color: '#e879f9' },
	{ type: 'script', label: 'Script', color: '#fb923c' },
	{ type: 'voiceover', label: 'Voiceover / TTS', color: '#34d399' },
	{ type: 'gameplay', label: 'Gameplay / Background', color: '#38bdf8' },
	{ type: 'preview', label: 'Preview & Export', color: '#fb7185' }
];

const nodeTypes: NodeTypes = {
	model: ModelNode,
	topic: TopicNode,
	script: ScriptNode,
	voiceover: VoiceoverNode,
	gameplay: GameplayNode,
	preview: PreviewNode
};

const edgeTypes: EdgeTypes = {};

/**
 * Wizard stage at which each canonical pipeline node becomes visible.
 * User-added freeform nodes (non-canonical ids) are always visible.
 */
const NODE_STAGE: Record<string, number> = {
	model: 1,
	topic: 1,
	script: 2,
	voiceover: 3,
	gameplay: 4,
	preview: 5
};

// --- Initial graph -----------------------------------------------------------

function initialNodes(): Node[] {
	return [
		{
			id: 'model',
			type: 'model',
			position: { x: 0, y: 80 },
			data: {},
			className: 'node-reveal'
		},
		{
			id: 'topic',
			type: 'topic',
			position: { x: 400, y: 0 },
			data: {},
			className: 'node-reveal'
		},
		{
			id: 'script',
			type: 'script',
			position: { x: 800, y: 0 },
			data: {},
			className: 'node-reveal'
		},
		{
			id: 'voiceover',
			type: 'voiceover',
			position: { x: 1200, y: 0 },
			data: {},
			className: 'node-reveal'
		},
		{
			id: 'gameplay',
			type: 'gameplay',
			position: { x: 1600, y: 0 },
			data: {},
			className: 'node-reveal'
		},
		{
			id: 'preview',
			type: 'preview',
			position: { x: 2000, y: 140 },
			data: {},
			className: 'node-reveal'
		}
	];
}

function initialEdges(): Edge[] {
	return [
		{
			id: 'e-model-topic',
			source: 'model',
			target: 'topic',
			animated: true,
			className: 'edge-reveal'
		},
		{
			id: 'e-topic-script',
			source: 'topic',
			target: 'script',
			animated: true,
			className: 'edge-reveal'
		},
		{
			id: 'e-script-voiceover',
			source: 'script',
			target: 'voiceover',
			animated: true,
			className: 'edge-reveal'
		},
		{
			id: 'e-voiceover-gameplay',
			source: 'voiceover',
			target: 'gameplay',
			animated: true,
			className: 'edge-reveal'
		},
		{
			id: 'e-gameplay-preview',
			source: 'gameplay',
			target: 'preview',
			targetHandle: 'gameplay',
			animated: true,
			className: 'edge-reveal'
		}
	];
}

// --- Canvas -------------------------------------------------------------------

function Canvas() {
	const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes());
	const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges());

	const stepwise = usePipelineStore((s) => s.stepwise);
	const stage = usePipelineStore((s) => studioStage(s));

	const { fitView, getNodes } = useReactFlow();

	const onConnect = useCallback(
		(connection: Connection) =>
			setEdges((eds) =>
				addEdge(
					{ ...connection, animated: true, className: 'edge-reveal' },
					eds
				)
			),
		[setEdges]
	);

	const addNode = useCallback(
		(type: StudioNodeType) => {
			setNodes((nds) => [
				...nds,
				{
					id: `${type}-${Date.now()}`,
					type,
					position: {
						x: 400 + nds.length * 60,
						y: 420 + nds.length * 40
					},
					data: {},
					className: 'node-reveal'
				}
			]);
		},
		[setNodes]
	);

	const resetLayout = useCallback(() => {
		setNodes(initialNodes());
		setEdges(initialEdges());
	}, [setNodes, setEdges]);

	// --- Progressive reveal ---------------------------------------------------

	/** Canonical pipeline nodes stay hidden until the wizard reaches their
	 * stage; freeform user-added nodes are always visible. */
	const isNodeVisible = useCallback(
		(id: string) => !stepwise || (NODE_STAGE[id] ?? 0) <= stage,
		[stepwise, stage]
	);

	const displayedNodes = stepwise
		? nodes.filter((n) => isNodeVisible(n.id))
		: nodes;
	const displayedEdges = stepwise
		? edges.filter((e) => isNodeVisible(e.source) && isNodeVisible(e.target))
		: edges;

	// Smooth camera transition whenever the reveal set grows (or the mode
	// toggles). Waits a beat so freshly mounted nodes get measured, then
	// fits a two-column window: the newly unlocked nodes plus the previous
	// step's anchor node for context.
	const mounted = useRef(false);
	useEffect(() => {
		if (!mounted.current) {
			mounted.current = true;
			return;
		}
		const timer = setTimeout(() => {
			const ids = getNodes()
				.filter(
					(n) =>
						!stepwise ||
						(NODE_STAGE[n.id] ?? Number.POSITIVE_INFINITY) >= stage - 1
				)
				.map((n) => n.id);
			if (ids.length === 0) return;
			fitView({
				nodes: ids.map((id) => ({ id })),
				padding: 0.25,
				duration: 700
			});
		}, 120);
		return () => clearTimeout(timer);
	}, [stage, stepwise, fitView, getNodes]);

	const minimapNodeColor = useCallback((node: Node) => {
		return NODE_MENU.find((n) => n.type === node.type)?.color ?? '#71717a';
	}, []);

	return (
		<ReactFlow
			nodes={displayedNodes}
			edges={displayedEdges}
			onNodesChange={onNodesChange}
			onEdgesChange={onEdgesChange}
			onConnect={onConnect}
			nodeTypes={nodeTypes}
			edgeTypes={edgeTypes}
			colorMode="dark"
			fitView
			fitViewOptions={{ padding: 0.25 }}
			minZoom={0.3}
			maxZoom={1.75}
			className="bg-background"
			proOptions={{ hideAttribution: false }}
		>
			<Background
				variant={BackgroundVariant.Dots}
				gap={26}
				size={1.6}
				color="#3f3f46"
			/>
			<Controls className="!border !border-border/60 !bg-card/90 !fill-foreground-900 [&>button]:!border-border/60 [&>button]:!bg-transparent [&>button]:!fill-foreground [&>button]:!text-foreground" />
			<MiniMap
				nodeColor={minimapNodeColor}
				maskColor="rgba(9,9,11,0.75)"
				className="!border !border-border/60 !bg-card/90"
				style={{ width: 160, height: 100 }}
				position="bottom-right"
			/>

			{/* Toolbar */}
			<Panel position="top-right" className="flex gap-2">
				<DropdownMenu>
					<DropdownMenuTrigger asChild>
						<Button
							size="sm"
							variant="outline"
							className="gap-1.5 border-border/60 bg-card/90 backdrop-blur"
						>
							<Plus className="size-3.5" /> Add node
						</Button>
					</DropdownMenuTrigger>
					<DropdownMenuContent align="end" className="w-52">
						{NODE_MENU.map((item) => (
							<DropdownMenuItem
								key={item.type}
								onClick={() => addNode(item.type)}
								className="gap-2"
							>
								<span
									className="size-2 rounded-full"
									style={{ backgroundColor: item.color }}
								/>
								{item.label}
							</DropdownMenuItem>
						))}
					</DropdownMenuContent>
				</DropdownMenu>
				<Button
					size="sm"
					variant="outline"
					onClick={resetLayout}
					className={cn('gap-1.5 border-border/60 bg-card/90 backdrop-blur')}
					title="Restore the default pipeline layout"
				>
					<RotateCcw className="size-3.5" /> Reset
				</Button>
			</Panel>

			{/* Stepwise wizard hint */}
			{stepwise && (
				<Panel position="bottom-center">
					<div
						className="pointer-events-none rounded-full border border-border/60 bg-card/90 px-4 py-1.5 text-xs text-muted-foreground shadow-lg shadow-black/40 backdrop-blur"
						data-testid="stepwise-hint"
					>
						<span className="font-semibold text-foreground">
							Step {stage} of 5
						</span>
						<span className="mx-1.5 text-border">·</span>
						{STUDIO_STEPS[stage - 1].hint}
					</div>
				</Panel>
			)}
		</ReactFlow>
	);
}

export function MemeCanvas() {
	return (
		<ReactFlowProvider>
			<div className="h-full w-full">
				<Canvas />
			</div>
		</ReactFlowProvider>
	);
}
