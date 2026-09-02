'use client';

// The meme generation canvas: React Flow graph of pipeline nodes.

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
	useNodesState
} from '@xyflow/react';
import { useCallback } from 'react';
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

// --- Initial graph -----------------------------------------------------------

function initialNodes(): Node[] {
	return [
		{ id: 'model', type: 'model', position: { x: 0, y: 80 }, data: {} },
		{ id: 'topic', type: 'topic', position: { x: 400, y: 0 }, data: {} },
		{ id: 'script', type: 'script', position: { x: 800, y: 0 }, data: {} },
		{
			id: 'voiceover',
			type: 'voiceover',
			position: { x: 1200, y: 0 },
			data: {}
		},
		{
			id: 'gameplay',
			type: 'gameplay',
			position: { x: 800, y: 460 },
			data: {}
		},
		{ id: 'preview', type: 'preview', position: { x: 1600, y: 140 }, data: {} }
	];
}

function initialEdges(): Edge[] {
	return [
		{
			id: 'e-model-topic',
			source: 'model',
			target: 'topic',
			animated: true
		},
		{
			id: 'e-topic-script',
			source: 'topic',
			target: 'script',
			animated: true
		},
		{
			id: 'e-script-voiceover',
			source: 'script',
			target: 'voiceover',
			animated: true
		},
		{
			id: 'e-voiceover-preview',
			source: 'voiceover',
			target: 'preview',
			animated: true
		},
		{
			id: 'e-gameplay-preview',
			source: 'gameplay',
			target: 'preview',
			targetHandle: 'gameplay',
			animated: true
		}
	];
}

// --- Canvas -------------------------------------------------------------------

function Canvas() {
	const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes());
	const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges());

	const onConnect = useCallback(
		(connection: Connection) =>
			setEdges((eds) => addEdge({ ...connection, animated: true }, eds)),
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
					data: {}
				}
			]);
		},
		[setNodes]
	);

	const resetLayout = useCallback(() => {
		setNodes(initialNodes());
		setEdges(initialEdges());
	}, [setNodes, setEdges]);

	const minimapNodeColor = useCallback((node: Node) => {
		return NODE_MENU.find((n) => n.type === node.type)?.color ?? '#71717a';
	}, []);

	return (
		<ReactFlow
			nodes={nodes}
			edges={edges}
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
